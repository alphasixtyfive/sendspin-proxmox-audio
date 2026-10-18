"""Topology validation and staging boundaries; no network, services or hardware."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("configure", ROOT / "scripts/configure.py")
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self.c = configure.load(ROOT / "examples/audio.toml")

    def invalid(self, change):
        change(self.c)
        with self.assertRaises(ValueError):
            configure.render(self.c)

    def test_example_has_exact_seven_routes_and_no_pairing_state(self):
        files = configure.render(self.c)
        self.assertEqual(len(files), 16)
        routes = files["ct/etc/pipewire/pipewire.conf.d/60-zones.conf"]
        self.assertEqual(routes.count('"libpipewire-module-loopback"'), 7)
        self.assertEqual(routes.count('node.dont-fallback = true'), 7)
        self.assertEqual(routes.count('stream.dont-remix = true'), 14)
        self.assertIn('audio.position = [ FC LFE ]', routes)
        self.assertFalse(any("state" in p or "key" in p for p in files))
        target = files["ct/user/sendspin-zones.target"]
        for key in self.c["zones"]:
            self.assertIn("sendspin-zone@" + key + ".service", target)
        self.assertIn("allow-unpaired = false", files["ct/etc/sendspin-zones/study.conf"])

    def test_rename_and_move_preserve_state_and_service_key(self):
        old = configure.render(self.c)
        self.c["zones"]["study"].update(name="Office", device="b", output="side")
        new = configure.render(self.c)
        self.assertEqual(set(old), set(new))
        self.assertEqual(old["ct/user/sendspin-zones.target"], new["ct/user/sendspin-zones.target"])
        self.assertIn("name = Office", new["ct/etc/sendspin-zones/study.conf"])
        self.assertIn("output = pipewire:sendspin_study", new["ct/etc/sendspin-zones/study.conf"])

    def test_disabled_zone_emits_no_player_route_or_target(self):
        self.c["zones"]["study"]["enabled"] = False
        # A disabled saved definition does not reserve its port/socket.
        self.c["zones"]["guest-room"].update(output="front", port=8931)
        files = configure.render(self.c)
        self.assertNotIn("ct/etc/sendspin-zones/study.conf", files)
        self.assertNotIn("sendspin-zone@study.service", files["ct/user/sendspin-zones.target"])
        self.assertNotIn('"sendspin_study"', files["ct/etc/pipewire/pipewire.conf.d/60-zones.conf"])

    def test_rejects_conflicts_and_invalid_input(self):
        cases = [
            lambda c: c.update(typo=True),
            lambda c: c.update(version=True),
            lambda c: c.update(server="http://ma.example.invalid/sendspin"),
            lambda c: c.update(server="ws://user:secret@ma.example.invalid/sendspin"),
            lambda c: c.update(server="ws://ma.example.invalid:70000/sendspin"),
            lambda c: c.update(server="ws://ma.example.invalid/sendspin?token=secret"),
            lambda c: c["zones"]["study"].update(name="Study\nallow-unpaired = true"),
            lambda c: c["zones"]["study"].update(port=True),
            lambda c: c["zones"]["study"].update(port=80),
            lambda c: c["zones"]["study"].update(device="missing"),
            lambda c: c["zones"]["study"].update(output="headphone"),
            lambda c: c["zones"]["study"].update(enabled="false"),
            lambda c: c["zones"]["guest-room"].update(output="front"),
            lambda c: c["zones"]["guest-room"].update(port=8931),
            lambda c: c["zones"].update({"../escape": c["zones"].pop("study")}),
            lambda c: c["devices"]["a"].update(profile="stereo"),
            lambda c: c["devices"]["a"].update(alsa_id="CARD_B"),
            lambda c: c["devices"]["a"].update(node="sendspin_study"),
            lambda c: c["devices"]["a"].update(clock="api.alsa.ca7_b"),
            lambda c: c["layout"].update(routing_file="../outside.conf"),
            lambda c: c["layout"].update(routing_file="61-ca7-physical.conf"),
            lambda c: [z.update(enabled=False) for z in c["zones"].values()],
        ]
        for change in cases:
            with self.subTest(case=cases.index(change)):
                self.c = configure.load(ROOT / "examples/audio.toml")
                self.invalid(change)

    def host_config(self):
        self.c["host"] = {"ctid": 123, "user": "sendspin-cli", "uid": 999}
        self.c["devices"]["a"].update(usb_port="1-2.3", slots=["dev0", "dev1"])
        self.c["devices"]["b"].update(usb_port="1-2.4", slots=["dev2", "dev3"])

    def test_host_map_matches_existing_recovery_schema(self):
        self.host_config()
        host = json.loads(configure.render(self.c)["host/etc/sendspin-usb-recovery.json"])
        self.assertEqual(set(host), {"ctid", "user", "uid", "routing_file", "cards"})
        self.assertEqual(host["routing_file"], "/etc/pipewire/pipewire.conf.d/60-zones.conf")
        self.assertEqual(host["cards"][0], {"usb_port": "1-2.3", "slots": ["dev0", "dev1"],
                         "vendor": "0bda", "product": "4f25", "alsa_id": "CARD_A", "node": "ca7_card_a"})

    def test_host_requires_reviewed_two_card_scope(self):
        self.host_config()
        original = copy.deepcopy(self.c)
        cases = [lambda c: c["devices"]["b"].update(slots=["dev1", "dev2"]),
                 lambda c: c["devices"]["b"].update(usb_port="1-2.3"),
                 lambda c: c["devices"]["b"].pop("slots"),
                 lambda c: c["host"].update(uid=0),
                 lambda c: c["host"].update(user="root"),
                 lambda c: c["host"].update(user="root;command"),
                 lambda c: c["devices"].update(c={"profile": "ca7", "alsa_id": "CARD_C"})]
        for change in cases:
            self.c = copy.deepcopy(original)
            with self.subTest(case=cases.index(change)):
                self.invalid(change)

    def test_stage_is_repeatable_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "stage"
            manifest = configure.stage(self.c, output)
            self.assertEqual(manifest, configure.stage(self.c, Path(td) / "second"))
            self.assertEqual(manifest, json.loads((output / "manifest.json").read_text()))
            (output / "sentinel").write_text("keep")
            with self.assertRaises(FileExistsError):
                configure.stage(self.c, output)
            self.assertEqual((output / "sentinel").read_text(), "keep")

    def test_verify_is_read_only_and_matches_every_staged_file(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "stage"
            manifest = configure.stage(self.c, stage)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in stage.rglob("*") if p.is_file()}
            self.assertEqual(configure.verify(self.c, stage), manifest)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_verify_rejects_stale_partial_extra_and_tampered_stages(self):
        with tempfile.TemporaryDirectory() as td:
            for case in ["missing", "extra", "content", "manifest", "configuration"]:
                with self.subTest(case=case):
                    stage = Path(td) / case
                    configure.stage(self.c, stage)
                    player = stage / "ct/etc/sendspin-zones/study.conf"
                    config = copy.deepcopy(self.c)
                    if case == "missing": player.unlink()
                    elif case == "extra": (stage / "unreviewed.conf").write_text("extra")
                    elif case == "content": player.write_text("changed")
                    elif case == "manifest": (stage / "manifest.json").write_text("{}")
                    else: config["zones"]["study"]["name"] = "Office"
                    with self.assertRaises(ValueError):
                        configure.verify(config, stage)

    def test_interrupted_stage_cannot_pass_verification(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "stage"
            real_open = Path.open
            def failing_open(path, *args, **kwargs):
                if path == stage / "ct/etc/sendspin-zones/study.conf":
                    raise OSError("simulated disk failure")
                return real_open(path, *args, **kwargs)
            with patch.object(Path, "open", new=failing_open):
                with self.assertRaises(OSError): configure.stage(self.c, stage)
            self.assertTrue(stage.is_dir())
            self.assertFalse((stage / "manifest.json").exists())
            with self.assertRaises(ValueError): configure.verify(self.c, stage)

    def test_unicode_labels_are_utf8_in_native_and_player_files(self):
        self.c["zones"]["study"]["name"] = "Büro 🎵"
        files = configure.render(self.c)
        self.assertIn('node.description = "Büro 🎵"', files["ct/etc/pipewire/pipewire.conf.d/60-zones.conf"])
        self.assertIn("name = Büro 🎵", files["ct/etc/sendspin-zones/study.conf"])

    @unittest.skipIf(sys.platform == "win32", "unprivileged symlinks not always available")
    def test_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "link"
            link.symlink_to(Path(td) / "missing", target_is_directory=True)
            with self.assertRaises(FileExistsError):
                configure.stage(self.c, link)
            with self.assertRaises(ValueError):
                configure.verify(self.c, link)

    @unittest.skipIf(sys.platform == "win32", "unprivileged symlinks not always available")
    def test_verify_rejects_symlinked_file_and_directory(self):
        with tempfile.TemporaryDirectory() as td:
            for directory in [False, True]:
                stage = Path(td) / str(directory)
                configure.stage(self.c, stage)
                target = stage / ("ct/user" if directory else "ct/etc/sendspin-zones/study.conf")
                moved = Path(td) / ("original-" + str(directory))
                target.rename(moved)
                target.symlink_to(moved, target_is_directory=directory)
                with self.assertRaises(ValueError): configure.verify(self.c, stage)

    def test_cli_rejects_duplicate_toml_keys_without_echoing_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "bad.toml"
            source.write_text('server="SECRET"\nserver="SECRET"\n')
            result = subprocess.run([sys.executable, str(ROOT / "scripts/configure.py"), "check", str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("SECRET", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_rejects_invalid_url_without_echoing_its_port(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "bad.toml"
            source.write_text('version=1\nserver="ws://ma.example.invalid:PRIVATE_VALUE/sendspin"\n'
                              '[devices.a]\nprofile="ca7"\nalsa_id="CARD_A"\n'
                              '[zones.study]\nname="Study"\ndevice="a"\noutput="front"\nport=8931\n')
            result = subprocess.run([sys.executable, str(ROOT / "scripts/configure.py"), "check", str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("PRIVATE_VALUE", result.stderr)
            self.assertIn("invalid server URL", result.stderr)


if __name__ == "__main__":
    unittest.main()
