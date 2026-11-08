"""Topology validation and staging boundaries; no network, services or hardware."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shlex
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
        self.c["host"] = {"ctid": 123, "user": "sendspin-cli", "uid": 999,
                          "calibration_file": "/etc/sendspin-alsa.state"}
        self.c["devices"]["a"].update(usb_port="1-2.3", slots=["dev0", "dev1"])
        self.c["devices"]["b"].update(usb_port="1-2.4", slots=["dev2", "dev3"])

    def test_host_map_matches_existing_recovery_schema(self):
        self.host_config()
        host = json.loads(configure.render(self.c)["host/etc/sendspin-usb-recovery.json"])
        self.assertEqual(set(host), {"ctid", "user", "uid", "routing_file", "cards", "calibration_file"})
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

    def test_idle_gains_derive_pairs_and_preserve_distinct_calibrated_channels(self):
        self.host_config()
        saved = {'source_file': '/etc/sendspin-alsa.state', 'state_sha256': 'a' * 64, 'cards': {'CARD_A': [60, 61, 62, 63, 64, 65, 66, 67]}}
        for key in ['study', 'guest-room', 'kids-room', 'bedroom']:
            self.c['zones'][key]['idle_gain'] = 0
        files = configure.render(self.c, saved)
        for key, offset in [('study', 0), ('bedroom', 2), ('guest-room', 4), ('kids-room', 6)]:
            unit = files[f'ct/user/sendspin-zone@{key}.service.d/60-idle-gain.conf']
            self.assertIn(f'Environment=AUDIO_ACTIVE_LEFT={60 + offset}\n', unit)
            self.assertIn(f'Environment=AUDIO_ACTIVE_RIGHT={61 + offset}\n', unit)
            self.assertIn('sendspin-hardware-CARD_A.lock', unit)
            self.assertIn('"' + ',' * offset + '${AUDIO_IDLE_GAIN},${AUDIO_IDLE_GAIN}"', unit)
            self.assertIn('hook-start = /usr/bin/flock', files[f'ct/etc/sendspin-zones/{key}.conf'])
        host = json.loads(files['host/etc/sendspin-usb-recovery.json'])
        self.assertEqual({p['offset'] for p in host['idle_gains']}, {0, 2, 4, 6})
        self.assertNotIn('ct/user/sendspin-zone@lounge.service.d/60-idle-gain.conf', files)
        for key in ['study', 'guest-room', 'kids-room', 'bedroom']:
            del self.c['zones'][key]['idle_gain']
        self.assertFalse(any('idle-gain' in p for p in configure.render(self.c)))

    def test_idle_policy_requires_calibration_and_rejects_invalid_or_louder_gains(self):
        self.host_config()
        self.c['zones']['study']['idle_gain'] = 0
        with self.assertRaises(ValueError): configure.render(self.c)
        valid = {'source_file': '/etc/sendspin-alsa.state', 'state_sha256': 'b' * 64, 'cards': {'CARD_A': [66] * 8}}
        for value in [True, -1, 88, '0']:
            self.c['zones']['study']['idle_gain'] = value
            with self.assertRaises(ValueError): configure.render(self.c, valid)
        self.c['zones']['study']['idle_gain'] = 67
        with self.assertRaises(ValueError): configure.render(self.c, valid)
        with self.assertRaises(ValueError): configure.render(self.c, {**valid, 'source_file': '/var/lib/alsa/asound.state'})

        self.c['zones']['study']['idle_gain'] = 0
        for saved in [{**valid, 'state_sha256': 'invalid'}, {**valid, 'cards': {}},
                      {**valid, 'cards': {'CARD_A': [66] * 7}},
                      {**valid, 'cards': {'CARD_A': [True] * 8}}]:
            with self.assertRaises(ValueError): configure.render(self.c, saved)
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / 'stage'
            configure.stage(self.c, staged, valid)
            configure.verify(self.c, staged, valid)
            changed = copy.deepcopy(valid); changed['cards']['CARD_A'][0] = 65
            with self.assertRaises(ValueError): configure.verify(self.c, staged, changed)
        self.c.pop('host')
        with self.assertRaises(ValueError): configure.render(self.c, valid)

    def test_one_shared_gain_controls_selected_rooms_and_rejects_duplicate_owners(self):
        self.host_config()
        self.c['idle_gain'] = {'raw': 0, 'zones': ['study', 'guest-room', 'bedroom', 'kids-room']}
        saved = {'source_file': '/etc/sendspin-alsa.state', 'state_sha256': 'a' * 64, 'cards': {'CARD_A': [66] * 8}}
        first = configure.render(self.c, saved)
        self.c['idle_gain']['raw'] = 10
        second = configure.render(self.c, saved)
        for zone in self.c['idle_gain']['zones']:
            key = f'ct/user/sendspin-zone@{zone}.service.d/60-idle-gain.conf'
            self.assertIn('Environment=AUDIO_IDLE_GAIN=0\n', first[key])
            self.assertIn('Environment=AUDIO_IDLE_GAIN=10\n', second[key])
        self.assertEqual(first['ct/etc/sendspin-zones/lounge.conf'], second['ct/etc/sendspin-zones/lounge.conf'])
        for change in [lambda c: c['zones']['study'].update(idle_gain=0),
                       lambda c: c['idle_gain'].update(zones=['unknown']),
                       lambda c: c['idle_gain'].update(zones=['study', 'study'])]:
            candidate = copy.deepcopy(self.c); change(candidate)
            with self.assertRaises(ValueError): configure.render(candidate, saved)

    def test_disabled_shared_members_do_not_emit_hooks_or_require_gain_export(self):
        self.host_config()
        self.c['idle_gain'] = {'raw': 0, 'zones': ['study', 'guest-room']}
        for key in self.c['idle_gain']['zones']:
            self.c['zones'][key]['enabled'] = False
        files = configure.render(self.c)
        self.assertFalse(any('idle-gain' in path for path in files))
        self.assertFalse(any('hook-start' in content for content in files.values()))
        self.assertNotIn('idle_gains', json.loads(files['host/etc/sendspin-usb-recovery.json']))
        self.assertIn('ct/etc/sendspin-zones/lounge.conf', files)

    @unittest.skipIf(sys.platform == 'win32', 'native Linux shell hook execution')
    def test_hook_survives_stock_reserved_environment_filter_and_missing_gain_fails(self):
        self.host_config()
        self.c['zones']['guest-room']['idle_gain'] = 0
        saved = {'source_file': '/etc/sendspin-alsa.state', 'state_sha256': 'a' * 64, 'cards': {'CARD_A': [60, 61, 62, 63, 64, 65, 66, 67]}}
        files = configure.render(self.c, saved)
        hook = next(line.split(' = ', 1)[1] for line in files['ct/etc/sendspin-zones/guest-room.conf'].splitlines()
                    if line.startswith('hook-start = '))
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td); capture = folder / 'args'; mixer = folder / 'amixer'
            mixer.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n'); mixer.chmod(0o755)
            hook = hook.replace('/usr/bin/amixer', shlex.quote(str(mixer))).replace(
                '/run/user/999/sendspin-hardware-CARD_A.lock', shlex.quote(str(folder / 'lock')))
            env = {**os.environ, 'AUDIO_ACTIVE_LEFT': '64', 'AUDIO_ACTIVE_RIGHT': '65',
                   'SENDSPIN_DISCARDED': 'not inherited', 'CAPTURE': str(capture)}
            env = {k: v for k, v in env.items() if not k.startswith('SENDSPIN_')}
            p = subprocess.run(['/bin/sh', '-c', hook], env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(capture.read_text().splitlines()[-1], ',,,,64,65')
            # A busy recovery operation must delay a transition, not discard it.
            import fcntl
            import time
            capture.unlink()
            with (folder / 'lock').open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                pending = subprocess.Popen(['/bin/sh', '-c', hook], env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    time.sleep(2.2)
                    self.assertIsNone(pending.poll(), 'gain transition was lost during lock contention')
                    self.assertFalse(capture.exists())
                finally:
                    fcntl.flock(held, fcntl.LOCK_UN)
                _, err = pending.communicate(timeout=3)
                self.assertEqual(pending.returncode, 0, err)
            self.assertEqual(capture.read_text().splitlines()[-1], ',,,,64,65')
            capture.unlink(); env.pop('AUDIO_ACTIVE_LEFT')
            p = subprocess.run(['/bin/sh', '-c', hook], env=env, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(capture.exists())

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
