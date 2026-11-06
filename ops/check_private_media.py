"""Verify private media through a temporary localhost Caddy in Docker Desktop."""

import argparse
import hashlib
import json
import os
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = "caddy:2.10.2"

# Runs inside the existing local web container; no database rows are needed.
MEDIA_FILES = r"""
import hashlib, json, os
from pathlib import Path
from uuid import UUID
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
payload = json.load(__import__('sys').stdin)
run = UUID(payload['run'])
root = Path(settings.MEDIA_ROOT).resolve(strict=True)
if settings.MEDIA_URL != '/media/':
    raise RuntimeError('Unexpected MEDIA_URL')
paths = {
    'income': f'bewerbungen/{run.hex}/einkommen/{run.hex}',
    'identity': f'bewerbungen/{run.hex}/identitaet/{run.hex}',
    'credit_report': f'bewerbungen/{run.hex}/bonitaet/{run.hex}',
    'handover_photo': f'u/{run.hex}/{run.hex}/{run.hex}',
    'apartment_photo': f'apartments/{run}/{run.hex}.jpg',
    'pdf': f'private/handovers/{run}/{run.hex}/protokoll.pdf',
    'tenant_signature': f'private/handovers/{run}/{run.hex}/mieter.png',
    'employee_signature': f'private/handovers/{run}/{run.hex}/mitarbeiter.png',
}
def content(kind):
    return f'STEImmo issue 140 synthetic media probe {run} {kind}\n'.encode()
def target(relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise RuntimeError('Probe path escaped MEDIA_ROOT')
    return path
def remove(path):
    parts = path.relative_to(root).parts
    boundary_index = next(i for i, part in enumerate(parts) if part in (run.hex, str(run)))
    boundary = root.joinpath(*parts[:boundary_index + 1])
    path.unlink()
    parent = path.parent
    while parent.is_relative_to(boundary):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
action = payload['action']
if action not in ('create', 'verify', 'cleanup'):
    raise RuntimeError('Unknown action')
if action == 'create':
    if any(target(relative).exists() for relative in paths.values()):
        raise RuntimeError('Probe file already exists; refusing to overwrite')
    created = []
    try:
        for kind, relative in paths.items():
            path = target(relative)
            directory = root
            for part in path.relative_to(root).parts[:-1]:
                directory /= part
                directory.mkdir(mode=0o700, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(content(kind))
    except BaseException:
        for path in reversed(created):
            remove(path)
        raise
if action == 'cleanup':
    # Check all ownership markers before deleting even one file.
    for kind, relative in paths.items():
        path = target(relative)
        if path.exists() and path.read_bytes() != content(kind):
            raise RuntimeError('Probe content changed; refusing to delete')
    for relative in reversed(list(paths.values())):
        path = target(relative)
        if path.exists():
            remove(path)
    print(json.dumps({'removed': not any(target(p).exists() for p in paths.values())}))
else:
    result = []
    for kind, relative in paths.items():
        data = target(relative).read_bytes()
        if data != content(kind):
            raise RuntimeError('Probe file read-back failed')
        result.append({'kind': kind, 'path': '/media/' + relative,
                       'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    print(json.dumps(result))
"""


def docker(*args, stdin=None):
    return subprocess.run(
        ["docker", *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def response(opener, base, path, method="GET"):
    request = urllib.request.Request(
        base + path,
        method=method,
        headers={"User-Agent": "STEImmo-Issue-140-local-media-check", "Cache-Control": "no-cache"},
    )
    try:
        result = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        result = error
    with result:
        return result.status, result.headers, result.read(1024 * 1024)


def verify_denied(status, headers, body, expected_hash, *, canonical):
    if status != 404:
        raise RuntimeError(f"Private media returned HTTP {status}, expected 404")
    if (
        hashlib.sha256(body).hexdigest() == expected_hash
        or b"STEImmo issue 140 synthetic media probe " in body
    ):
        raise RuntimeError("Private media content was disclosed in an error response")
    if canonical and (headers.get("Server") != "Caddy" or body):
        raise RuntimeError("Canonical media request was not rejected directly by Caddy")


def local_config(source):
    site = "steimmo-projekt-page.justus.software {"
    upstream = "reverse_proxy 172.17.0.1:8010"
    if source.count(site) != 1 or source.count(upstream) != 1:
        raise RuntimeError("Site snippet changed; review the localhost substitutions")
    return source.replace(site, "localhost {\n\ttls internal").replace(
        upstream, "reverse_proxy host.docker.internal:8000"
    )


def run(web_container):
    # Refuse remote Docker endpoints; the task is explicitly localhost-only.
    endpoint = os.environ.get("DOCKER_HOST") or docker(
        "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
    )
    if not endpoint.startswith(("npipe://", "unix://")):
        raise RuntimeError("Only a local Docker endpoint is permitted")
    if "Docker Desktop" not in docker("info", "--format", "{{.OperatingSystem}}"):
        raise RuntimeError("This localhost runner requires Docker Desktop")
    info = json.loads(docker("inspect", web_container))[0]
    ports = info["NetworkSettings"]["Ports"].get("8000/tcp") or []
    if ports != [{"HostIp": "127.0.0.1", "HostPort": "8000"}]:
        raise RuntimeError("Web container must publish only the expected localhost upstream")
    source = (ROOT / "ops/caddy-steimmo.caddy").read_text(encoding="utf-8")
    config = local_config(source)
    run_id = str(uuid4())
    name = f"steimmo-140-media-{run_id}"
    report = {"run": run_id, "scope": "localhost", "requests": []}
    created = False
    files_created = False

    def media(action):
        return json.loads(
            docker(
                "exec",
                "-i",
                web_container,
                "python",
                "-c",
                MEDIA_FILES,
                stdin=json.dumps({"run": run_id, "action": action}),
            )
        )

    try:
        manifest = media("create")
        files_created = True
        report["files"] = manifest
        with tempfile.TemporaryDirectory(prefix="steimmo-140-caddy-") as directory:
            path = Path(directory, "Caddyfile")
            path.write_text(config, encoding="utf-8")
            docker(
                "create",
                "--name",
                name,
                "--label",
                f"steimmo.issue-140.run={run_id}",
                "--publish",
                "127.0.0.1::443",
                "--mount",
                f"type=bind,source={ROOT / 'static'},target=/srv/steimmo/public/current,readonly",
                CADDY_IMAGE,
            )
            created = True
            docker("cp", str(path), f"{name}:/etc/caddy/Caddyfile")
            docker("start", name)
            certificate = None
            for _attempt in range(20):
                try:
                    certificate = docker(
                        "exec", name, "cat", "/data/caddy/pki/authorities/local/root.crt"
                    )
                    break
                except subprocess.CalledProcessError:
                    time.sleep(0.25)
            if not certificate:
                raise RuntimeError("Local Caddy CA was not ready")
            port = docker(
                "inspect",
                "--format",
                '{{(index (index .NetworkSettings.Ports "443/tcp") 0).HostPort}}',
                name,
            )
            base = f"https://localhost:{int(port)}"
            report["origin"] = base
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context(cadata=certificate)),
            )
            status, _headers, body = response(opener, base, "/health/")
            if status != 200 or json.loads(body) != {"service": "steimmo", "status": "ok"}:
                raise RuntimeError("Django upstream positive control failed")
            status, headers, body = response(opener, base, "/static/css/app.css")
            css = (ROOT / "static/css/app.css").read_bytes()
            if status != 200 or headers.get("Server") != "Caddy" or body != css:
                raise RuntimeError("Caddy static positive control failed")
            report["positive_controls"] = {"health": 200, "static_css": 200}
            for item in manifest:
                canonical = item["path"]
                variants = (
                    canonical,
                    canonical + "?issue140=" + run_id,
                    canonical.replace("/media/", "/%6dedia/", 1),
                    canonical.replace("/media/", "/static/../media/", 1),
                )
                for path in variants:
                    for method in ("GET", "HEAD"):
                        status, headers, body = response(opener, base, path, method)
                        verify_denied(
                            status, headers, body, item["sha256"], canonical=path == canonical
                        )
                        report["requests"].append(
                            {"kind": item["kind"], "path": path, "method": method, "status": status}
                        )
            if media("verify") != manifest:
                raise RuntimeError("Private probe files changed during HTTP checks")
            mounts = json.loads(docker("inspect", "--format", "{{json .Mounts}}", name))
            binds = [mount for mount in mounts if mount["Type"] == "bind"]
            if (
                len(binds) != 1
                or binds[0]["RW"]
                or binds[0]["Destination"] != "/srv/steimmo/public/current"
            ):
                raise RuntimeError("Unexpected Caddy bind mounts")
            report["caddy"] = {
                "image": CADDY_IMAGE,
                "config_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "static_read_only": True,
                "media_mounted": False,
                "tls_verified": True,
            }
    finally:
        try:
            if files_created:
                report["files_cleaned"] = media("cleanup")["removed"]
        finally:
            if created:
                label = docker(
                    "inspect", "--format", '{{index .Config.Labels "steimmo.issue-140.run"}}', name
                )
                if label != run_id:
                    raise RuntimeError("Container ownership label changed; refusing removal")
                docker("rm", "--force", "--volumes", name)
                report["proxy_cleaned"] = True
    if not report.get("files_cleaned") or not report.get("proxy_cleaned"):
        raise RuntimeError("Probe cleanup was not confirmed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-container", default="docker-web-1")
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.web_container), indent=2))
