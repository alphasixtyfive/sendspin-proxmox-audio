"""Exercise the editor with the public example and a disposable loopback server."""

import importlib.util
from http.client import HTTPConnection
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sendspin_web", ROOT / "settings/sendspin_web.py")
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / "sendspin.toml"
        self.original = (ROOT / "examples/audio.toml").read_bytes()
        self.path.write_bytes(self.original)

    def serve(self, *, managed=False):
        args = SimpleNamespace(
            config=self.path,
            project=ROOT,
            stages=self.folder / "stages",
            calibration=None,
            bind=IPv4Address("127.0.0.1"),
            client=None,
            port=0,
        )
        environment = {"INVOCATION_ID": "fixture" if managed else "", "CREDENTIALS_DIRECTORY": ""}
        with patch.dict(os.environ, environment):
            self.server = editor.SettingsServer(args)
        self.worker = Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        self.worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.worker.join, 2)
        self.addCleanup(self.server.shutdown)

    def request(self, path, data=None, **headers):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            body = None
            if data is not None:
                body = json.dumps(data)
                headers.setdefault("Content-Type", "application/json")
                headers.setdefault("Origin", self.server.origin)
            connection.request("GET" if data is None else "POST", path, body, headers)
            response = connection.getresponse()
            return response.status, json.load(response)
        finally:
            connection.close()

    def workshop(self, **values):
        return {
            "revision": editor.revision(self.path.read_bytes()),
            "name": "Workshop",
            "socket": "b/side",
            "enabled": True,
            **values,
        }

    def test_add_and_remove_prepare_the_saved_revision(self):
        self.serve()
        status, initial = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(len(initial["zones"]), 7)
        self.assertFalse(initial["restart"])

        draft = self.workshop(player_name="Workshop speakers")
        status, saved = self.request("/api/zone", draft)
        self.assertEqual(status, 200)
        self.assertEqual(saved["saved"], "workshop")
        new_player = Path(saved["installation"]) / "ct/etc/sendspin-zones/workshop.conf"
        self.assertIn("name = Workshop speakers\n", new_player.read_text())
        self.assertEqual(self.request("/api/zone", draft)[0], 409)

        status, removed = self.request(
            "/api/zone/remove", {"room": "workshop", "revision": saved["revision"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(removed["installation"], initial["installation"])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_conflict_and_failed_verification_leave_the_saved_settings(self):
        self.serve()
        _, initial = self.request("/api/config")
        self.assertEqual(self.request("/api/zone", self.workshop(socket="a/front"))[0], 400)

        def fail_verification(*args):
            raise ValueError("Could not verify.")

        with patch.dict(self.server.renderer, verify=fail_verification):
            self.assertEqual(self.request("/api/zone", self.workshop())[0], 400)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.request("/api/config")[1]["installation"], initial["installation"])
        self.assertEqual(list(self.server.stages.iterdir()), [Path(initial["installation"])])

    def test_no_change_save_repairs_a_damaged_installation(self):
        self.serve()
        _, initial = self.request("/api/config")
        stage = Path(initial["installation"])
        player = stage / "ct/etc/sendspin-zones/study.conf"
        player.unlink()
        self.assertTrue((stage / "manifest.json").is_file())

        status, saved = self.request(
            "/api/zone", self.workshop(room="study", name="Study", socket="a/front"),
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["installation"], str(stage))
        self.assertTrue(player.is_file())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_requests_require_the_expected_client_host_and_origin(self):
        self.serve()
        self.assertEqual(self.request("/api/config", Host="foreign.example.invalid")[0], 403)
        self.assertEqual(
            self.request("/api/zone", self.workshop(), Origin="http://foreign.example.invalid")[0],
            403,
        )
        self.assertEqual(self.request("/api/restart", {})[0], 409)
        self.assertEqual(self.request("/api/config")[0], 200)
        self.server.clients.clear()
        self.assertEqual(self.request("/api/config")[0], 403)

    def test_managed_restart_stops_the_listener_cleanly(self):
        self.serve(managed=True)
        self.assertTrue(self.request("/api/config")[1]["restart"])
        self.assertEqual(self.request("/api/restart", {})[0], 202)
        self.worker.join(2)
        self.assertFalse(self.worker.is_alive())
        self.assertEqual(self.path.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
