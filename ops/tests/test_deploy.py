"""Run the real release script against controlled Docker/HTTPS failures on Linux."""

import fcntl
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
IMAGE = "ghcr.io/steimmo/steimmo@sha256:" + "b" * 64
RELEASE = COMMIT + "-123-1"

DOCKER = r"""#!/usr/bin/env python3
import io, json, os, sys, tarfile
a = sys.argv[1:]
scenario = os.environ.get("SCENARIO", "success")
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(a) + "\n")
if a[:2] == ["image", "inspect"]:
    print("arm64" if "Architecture" in a[-1] else os.environ["TEST_COMMIT"])
elif a[:1] == ["inspect"]:
    print("production-data" if scenario == "demo-volume-mismatch" else "steimmo-demo-postgres-data")
elif "pull" in a and scenario == "pull-failure":
    sys.exit(1)
elif "check" in a and scenario == "settings-failure":
    sys.exit(1)
elif "ps" in a:
    print("existing-postgres")
elif "deployment_preflight" in a:
    sys.exit(1 if scenario == "preflight-failure" else
             3 if scenario in {"migration-failure", "changed-schema-health-failure"} else 0)
elif "pg_dump" in " ".join(a):
    if scenario == "backup-failure": sys.exit(1)
    sys.stdout.buffer.write(b"test database dump")
elif "tar" in a:
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
        item = tarfile.TarInfo("example.txt")
        item.size = 6
        archive.addfile(item, io.BytesIO(b"upload"))
elif "migrate" in a and scenario == "migration-failure":
    sys.exit(1)
elif "up" in a and "web" in a and "old" not in " ".join(a) and scenario in {
    "health-failure", "changed-schema-health-failure"
}:
    sys.exit(1)
elif a[:1] == ["run"] and "json.load" in a[-1]:
    sys.exit(json.load(sys.stdin) != {"service": "steimmo", "status": "ok"})
"""

CURL = r"""#!/usr/bin/env python3
import json, os, sys
if os.environ.get("SCENARIO") == "https-failure": sys.exit(22)
if "--write-out" in sys.argv:
    print("302" if os.environ.get("SCENARIO") == "https-redirect" else "200", end="")
else:
    print(json.dumps({"service": "steimmo", "status": "ok"}))
"""


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="steimmo-deploy-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("shared", "incoming", "releases", "bin"):
            (self.root / name).mkdir()
        self.env_file = self.root / "shared/.env"
        self.env_file.write_text("TEST_ONLY=1\n")
        self.env_file.chmod(0o600)
        self.old = self.root / "releases/old"
        self.old.mkdir()
        (self.old / "success").write_text("previous success")
        (self.old / "image.txt").write_text(IMAGE)
        (self.old / "compose.prod.yaml").write_text("test")
        (self.root / "current").symlink_to(self.old)
        self.public = self.root / "public"
        (self.public / "releases/old").mkdir(parents=True)
        (self.public / "current").symlink_to("releases/old")
        incoming = self.root / "incoming" / RELEASE
        incoming.mkdir()
        (incoming / "compose.prod.yaml").write_text("test")
        for name, contents in {
            "docker": DOCKER,
            "curl": CURL,
            "uname": "#!/bin/sh\necho aarch64\n",
        }.items():
            path = self.root / "bin" / name
            path.write_text(contents)
            path.chmod(0o755)
        self.environment = os.environ | {
            "PATH": str(self.root / "bin") + ":" + os.environ["PATH"],
            "CALL_LOG": str(self.root / "calls.jsonl"),
            "TEST_COMMIT": COMMIT,
        }

    def deploy(self, scenario="success", image=IMAGE, mode=None):
        arguments = ["bash", str(PROJECT / "ops/deploy.sh"), str(self.root), RELEASE, image, COMMIT]
        if mode is not None:
            arguments.append(mode)
        result = subprocess.run(
            arguments,
            env=self.environment | {"SCENARIO": scenario},
            capture_output=True,
            text=True,
            timeout=20,
        )
        log = self.root / "calls.jsonl"
        self.calls = (
            [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        )
        return result

    def old_was_restarted(self):
        return any(
            "up" in call and str(self.old / "compose.prod.yaml") in call for call in self.calls
        )

    def test_success_records_digest_and_preserves_backup(self):
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "current").resolve().name, RELEASE)
        self.assertEqual((self.public / "current").resolve(), self.public / "releases" / RELEASE)
        metadata = json.loads((self.root / "current/release.json").read_text())
        self.assertEqual(metadata["image"], IMAGE)
        self.assertTrue((self.root / "backups" / RELEASE / "complete").exists())
        self.assertFalse(self.old_was_restarted())

    def test_demo_deploy_records_mode_and_seeds_after_migration(self):
        (self.old / "mode.txt").write_text("demo\n")
        result = self.deploy(mode="demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads((self.root / "current/release.json").read_text())
        self.assertEqual(metadata["mode"], "demo")
        commands = [call for call in self.calls if "migrate" in call or "setup_demo" in call]
        self.assertEqual(len(commands), 2)
        self.assertIn("migrate", commands[0])
        self.assertIn("setup_demo", commands[1])
        self.assertIn(["volume", "create", "steimmo-demo-postgres-data"], self.calls)
        self.assertIn(["volume", "create", "steimmo-demo-media-data"], self.calls)

    def test_demo_cannot_replace_a_production_release(self):
        result = self.deploy(mode="demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls)
        self.assertEqual((self.root / "current").resolve(), self.old)

    def test_demo_cannot_reuse_a_production_database_container(self):
        (self.old / "mode.txt").write_text("demo\n")
        result = self.deploy("demo-volume-mismatch", mode="demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("migrate" in call or "stop" in call for call in self.calls))

    def test_pull_or_preflight_failure_keeps_running_release(self):
        for scenario in ("pull-failure", "preflight-failure"):
            # Each attempt gets a separate release directory.
            with self.subTest(scenario=scenario):
                result = self.deploy(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.root / "current").resolve(), self.old)
                self.assertFalse(any("stop" in call for call in self.calls))
                # Re-stage the input for the second independent attempt.
                if scenario == "pull-failure":
                    staged = self.root / "incoming" / RELEASE
                    (self.root / "releases" / RELEASE).rename(staged)

    def test_backup_failure_restores_previous_without_migrating(self):
        result = self.deploy("backup-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old_was_restarted())
        self.assertFalse(any("migrate" in call for call in self.calls))

    def test_invalid_settings_do_not_initialize_a_database(self):
        result = self.deploy("settings-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("up" in call or "stop" in call for call in self.calls))

    def test_migration_failure_does_not_start_old_code(self):
        result = self.deploy("migration-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.old_was_restarted())
        self.assertEqual((self.root / "current").resolve(), self.old)

    def test_unhealthy_release_with_same_schema_rolls_back(self):
        result = self.deploy("health-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old_was_restarted())
        self.assertEqual((self.root / "current").resolve(), self.old)

    def test_unhealthy_release_after_schema_change_stays_stopped(self):
        result = self.deploy("changed-schema-health-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.old_was_restarted())

    def test_public_failure_restores_static_and_previous_image(self):
        result = self.deploy("https-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "current").resolve(), self.old)
        self.assertEqual((self.public / "current").resolve(), self.public / "releases/old")
        self.assertTrue(self.old_was_restarted())

    def test_first_release_public_failure_removes_current_links(self):
        (self.root / "current").unlink()
        (self.public / "current").unlink()
        result = self.deploy("https-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "current").is_symlink())
        self.assertFalse((self.public / "current").is_symlink())
        self.assertFalse(self.old_was_restarted())

    def test_redirect_is_not_a_successful_smoke_check(self):
        result = self.deploy("https-redirect")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.old_was_restarted())

    def test_mutable_tag_is_rejected_before_docker_runs(self):
        result = self.deploy(image="ghcr.io/steimmo/steimmo:latest")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls, [])

    def test_server_lock_blocks_concurrent_deployment(self):
        with (self.root / "deploy.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls, [])


class ShippingTests(unittest.TestCase):
    def test_password_uses_askpass_and_is_not_logged_or_passed_as_an_argument(self):
        with tempfile.TemporaryDirectory(prefix="steimmo-ship-") as temporary:
            directory = Path(temporary)
            executable = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
assert "StrictHostKeyChecking=yes" in sys.argv
assert os.environ["SSH_ASKPASS_REQUIRE"] == "force"
assert subprocess.check_output([os.environ["SSH_ASKPASS"]], text=True).strip() == "test-password"
assert "test-password" not in open(os.environ["SSH_ASKPASS"]).read()
"""
            for name in ("ssh", "scp"):
                path = directory / name
                path.write_text(executable)
                path.chmod(0o755)
            environment = os.environ | {
                "PATH": str(directory) + ":" + os.environ["PATH"],
                "CALL_LOG": str(directory / "calls.jsonl"),
                "DEPLOY_HOST": "178.104.51.71",
                "DEPLOY_SSH_PASSWORD": "test-password",
                "DEPLOY_KNOWN_HOSTS": "test-only-host-key",
                "STEIMMO_IMAGE": IMAGE,
                "GITHUB_SHA": COMMIT,
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1",
            }
            result = subprocess.run(
                ["bash", str(PROJECT / "ops/ship.sh")],
                env=environment,
                cwd=PROJECT,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (directory / "calls.jsonl").read_text()
            self.assertEqual(len(calls.splitlines()), 3)
            self.assertNotIn("test-password", calls + result.stdout + result.stderr)


class EntryPointTests(unittest.TestCase):
    def run_entrypoint(self, bootstrap):
        with tempfile.TemporaryDirectory(prefix="steimmo-entrypoint-") as temporary:
            directory = Path(temporary)
            executable = directory / "python"
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n')
            executable.chmod(0o755)
            environment = os.environ | {
                "PATH": str(directory) + ":" + os.environ["PATH"],
                "CALL_LOG": str(directory / "calls"),
                "DJANGO_BOOTSTRAP_ON_START": bootstrap,
                "DJANGO_CREATE_DEVELOPMENT_EMPLOYEE": "0",
            }
            result = subprocess.run(
                ["sh", str(PROJECT / "docker/entrypoint.sh"), "printf", "ready"],
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ready")
            log = directory / "calls"
            return log.read_text() if log.exists() else ""

    def test_production_restart_runs_no_migrations_or_collectstatic(self):
        self.assertEqual(self.run_entrypoint("0"), "")

    def test_local_bootstrap_preserves_migrate_and_collectstatic(self):
        self.assertEqual(
            self.run_entrypoint("1").splitlines(),
            ["manage.py migrate --noinput", "manage.py collectstatic --noinput"],
        )
