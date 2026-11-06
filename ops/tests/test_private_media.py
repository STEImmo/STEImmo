"""Prevent false-green localhost proxy reports and remote Docker execution."""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from ops import check_private_media as probe


class PrivateMediaVerifierTests(unittest.TestCase):
    def setUp(self):
        self.marker = b"STEImmo issue 140 synthetic media probe test income\n"
        self.digest = hashlib.sha256(self.marker).hexdigest()

    def test_only_expected_404_is_accepted_as_private_media_denial(self):
        for status in (200, 301, 302, 403, 500):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                probe.verify_denied(status, {"Server": "Caddy"}, b"", self.digest, canonical=True)
        probe.verify_denied(404, {"Server": "Caddy"}, b"", self.digest, canonical=True)

    def test_django_404_does_not_count_as_direct_caddy_denial(self):
        with self.assertRaises(RuntimeError):
            probe.verify_denied(
                404, {"Server": "gunicorn"}, b"not found", self.digest, canonical=True
            )

    def test_a_probe_returned_inside_an_error_page_is_still_a_disclosure(self):
        for body in (self.marker, b"<html>" + self.marker + b"</html>"):
            with self.subTest(body=body), self.assertRaises(RuntimeError):
                probe.verify_denied(404, {"Server": "Caddy"}, body, self.digest, canonical=False)

    def test_local_config_preserves_the_media_rule_and_only_adapts_local_routing(self):
        source = (probe.ROOT / "ops/caddy-steimmo.caddy").read_text(encoding="utf-8")
        adapted = probe.local_config(source)
        self.assertIn("handle /media/* {\n\t\trespond 404", adapted)
        restored = adapted.replace(
            "localhost {\n\ttls internal", "steimmo-projekt-page.justus.software {"
        )
        restored = restored.replace(
            "reverse_proxy host.docker.internal:8000", "reverse_proxy 172.17.0.1:8010"
        )
        self.assertEqual(restored, source)
        with self.assertRaises(RuntimeError):
            probe.local_config(source.replace("172.17.0.1:8010", "elsewhere:9999"))

    def test_remote_docker_endpoint_is_rejected_before_any_docker_call(self):
        with (
            patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote.example.test:2376"}),
            patch.object(probe, "docker") as docker,
            self.assertRaisesRegex(RuntimeError, "local Docker"),
        ):
            probe.run("web")
        docker.assert_not_called()


class MediaProbeOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.run_id = UUID("9a7981fb-a2e8-458a-bcbc-cc76058af832")

    def media(self, action):
        fake_settings = SimpleNamespace(MEDIA_ROOT=self.root, MEDIA_URL="/media/")
        with (
            patch.dict(
                sys.modules,
                {
                    "django": SimpleNamespace(setup=lambda: None),
                    "django.conf": SimpleNamespace(settings=fake_settings),
                },
            ),
            patch.dict(os.environ),
            patch.object(
                sys, "stdin", io.StringIO(json.dumps({"run": str(self.run_id), "action": action}))
            ),
            patch.object(sys, "stdout", io.StringIO()) as output,
        ):
            exec(probe.MEDIA_FILES, {})
        return json.loads(output.getvalue())

    def test_cleanup_removes_only_probe_subtrees_and_preserves_shared_directories(self):
        shared = [
            self.root / name for name in ("bewerbungen", "u", "apartments", "private/handovers")
        ]
        for path in shared:
            path.mkdir(parents=True)
        manifest = self.media("create")
        self.assertEqual(len(manifest), 8)
        self.assertEqual(self.media("verify"), manifest)
        self.assertEqual(self.media("cleanup"), {"removed": True})
        self.assertTrue(all(path.is_dir() for path in shared))
        self.assertFalse([path for path in self.root.rglob("*") if path.is_file()])

    def test_existing_file_is_never_overwritten_or_removed_by_create(self):
        path = self.root / f"bewerbungen/{self.run_id.hex}/einkommen/{self.run_id.hex}"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"unrelated file")
        with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
            self.media("create")
        self.assertEqual(path.read_bytes(), b"unrelated file")
        self.assertEqual([p for p in self.root.rglob("*") if p.is_file()], [path])

    def test_changed_marker_prevents_cleanup_of_all_files(self):
        manifest = self.media("create")
        path = self.root / manifest[0]["path"].removeprefix("/media/")
        path.write_bytes(b"changed by another process")
        with self.assertRaisesRegex(RuntimeError, "refusing to delete"):
            self.media("cleanup")
        self.assertEqual(path.read_bytes(), b"changed by another process")
        self.assertEqual(len([p for p in self.root.rglob("*") if p.is_file()]), 8)

    def test_an_additional_public_upstream_binding_is_rejected_before_file_creation(self):
        def docker(*args, **kwargs):
            if args[0] == "info":
                return "Docker Desktop"
            if args[0] == "inspect":
                return json.dumps(
                    [
                        {
                            "NetworkSettings": {
                                "Ports": {
                                    "8000/tcp": [
                                        {"HostIp": "127.0.0.1", "HostPort": "8000"},
                                        {"HostIp": "0.0.0.0", "HostPort": "8000"},
                                    ]
                                }
                            }
                        }
                    ]
                )
            raise AssertionError("Probe files must not be created with unexpected bindings")

        with (
            patch.dict(os.environ, {"DOCKER_HOST": "npipe:////./pipe/test"}),
            patch.object(probe, "docker", side_effect=docker),
            self.assertRaisesRegex(RuntimeError, "localhost"),
        ):
            probe.run("web")
