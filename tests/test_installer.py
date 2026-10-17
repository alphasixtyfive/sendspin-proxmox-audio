"""Exercise the real installer in a temporary Linux filesystem, without services/network.

Run: python3 -m unittest discover -s tests -v
The shell, tar, checksums, install and rename operations are real. Only machine
identity, package/network commands and systemctl are substituted. Absolute
installer paths and the two release checksums are redirected to test fixtures.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "sendspin-cli-0.4.0-linux-x86_64.tar.gz"
PREFIX = "sendspin-cli-0.4.0-linux-x86_64"
ARCHIVE_SHA = "40efcab39ef303d026d8880ad1ada7b53b29e806114ae3744f9ed33daee0c5d9"
BINARY_SHA = "350b891ed3f11b73cf428cb7dc8bc8a9dd809892515c69fb2bca6724867cda7b"
BINARY = b"#!/bin/sh\nprintf 'sendspin-cli 0.4.0 test fixture\\n'\n"
OLD_BINARY = b"#!/bin/sh\nprintf 'previous binary\\n'\n"
BUILD_INFO = b"Version: 0.4.0\nFixture, not an upstream release\n"
PATH_PREFIXES = (
    "/etc/os-release",
    "/var/cache/sendspin-cli",
    "/usr/local/bin",
    "/var/lib/sendspin-cli",
    "/proc",
)


FAKE_COMMAND = r'''
import hashlib, json, os, pathlib, shutil, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["INSTALL_TEST_ROOT"])
state = json.loads((root / "state.json").read_text())
event = {"command": name, "args": args}
if name == "mv":
    src, dest = pathlib.Path(args[-2]), pathlib.Path(args[-1])
    assert src.is_relative_to(root) and dest.is_relative_to(root)
    event.update(source=str(src), destination=str(dest),
                 old_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()
                 if dest.exists() else None,
                 source_sha256=hashlib.sha256(src.read_bytes()).hexdigest())
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps(event) + "\n")
if name == "id":
    if args == ["-u"]: print("0")
    elif args == ["-u", "sendspin-cli"]: print(state.get("account_uid", 999))
    elif args == ["-nG", "sendspin-cli"]:
        print("sendspin-cli audio" if state.get("audio", True) else "sendspin-cli")
    else: raise AssertionError(args)
elif name == "hostname":
    assert not args
    print("test-sendspin-ct")
elif name == "getent":
    assert args == ["passwd", "sendspin-cli"]
    print("sendspin-cli:x:999:999:Test:" + str(root / "var/lib/sendspin-cli")
          + ":/usr/sbin/nologin")
elif name == "dpkg":
    assert args == ["--print-architecture"]
    print("amd64")
elif name == "systemd-detect-virt":
    assert args == ["--container"]
    print("lxc")
elif name == "apt-get":
    assert args == ["update"] or args[:1] == ["install"]
elif name == "systemctl":
    if args == ["is-active", "--quiet", "sendspin-cli.service"]:
        sys.exit(0 if state.get("active", False) else 3)
    elif args == ["is-enabled", "sendspin-cli.service"]:
        status = state.get("enabled", "disabled")
        print(status)
        sys.exit(0 if status in ("enabled", "enabled-runtime") else 1)
    elif args == ["mask", "sendspin-cli.service"]:
        (root / "single-player-masked").touch()
    elif args != ["daemon-reload"]:
        raise AssertionError("Unexpected service mutation: " + repr(args))
elif name == "curl":
    expected = ["--fail", "--location", "--proto", "=https", "--tlsv1.2",
                "https://github.com/Sendspin/sendspin-cpp-cli/releases/download/v0.4.0/"
                + os.environ["INSTALL_TEST_ARCHIVE"], "--output",
                str(root / "var/cache/sendspin-cli/v0.4.0" /
                    os.environ["INSTALL_TEST_ARCHIVE"])]
    assert args == expected, (args, expected)
    shutil.copyfile(root / "download-fixture.tar.gz", args[-1])
elif name == "mv":
    sys.exit(subprocess.run([os.environ["INSTALL_TEST_REAL_MV"], *args]).returncode)
else:
    raise AssertionError("Unexpected fake command: " + name)
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "requires real Linux /bin/sh and GNU tools")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        for command in ("tar", "sha256sum", "install", "mv", "mktemp"):
            self.assertIsNotNone(shutil.which(command), command)
        self.temp = tempfile.TemporaryDirectory(prefix="sendspin-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.fake_bin = self.root / "fake-bin"
        self.fake_bin.mkdir()
        for prefix in PATH_PREFIXES:
            path = self.root / prefix.lstrip("/")
            (path.parent if prefix == "/etc/os-release" else path).mkdir(parents=True, exist_ok=True)
        (self.root / "etc/os-release").write_text("ID=debian\nVERSION_ID=13\n")
        self.destination = self.root / "usr/local/bin/sendspin-cli"
        self.destination.write_bytes(OLD_BINARY)
        self.destination.chmod(0o755)
        dispatcher = self.fake_bin / "dispatch.py"
        dispatcher.write_text("#!" + sys.executable + "\n" + FAKE_COMMAND)
        dispatcher.chmod(0o755)
        for name in ("id", "hostname", "getent", "dpkg", "systemd-detect-virt",
                     "apt-get", "systemctl", "curl", "mv"):
            (self.fake_bin / name).symlink_to(dispatcher.name)
        self.state = {}
        self.archive = self.make_archive()

    @staticmethod
    def make_archive(binary=BINARY):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            entries = {
                f"{PREFIX}/usr/local/bin/sendspin-cli": binary,
                f"{PREFIX}/BUILD-INFO.txt": BUILD_INFO,
                f"{PREFIX}/usr/local/lib/systemd/system/sendspin-cli.service": b"UNWANTED UNIT\n",
                f"{PREFIX}/usr/local/lib/sysusers.d/sendspin-cli.conf": b"UNWANTED SYSUSERS\n",
            }
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith("/sendspin-cli") else 0o644
                archive.addfile(info, io.BytesIO(data))
        return output.getvalue()

    def run_installer(self, *, archive=None, expected_archive=None, download=False):
        archive = self.archive if archive is None else archive
        expected_archive = self.archive if expected_archive is None else expected_archive
        source = (ROOT / "scripts/install-official.sh").read_text()
        self.assertEqual(source.count(ARCHIVE_SHA), 1)
        self.assertEqual(source.count(BINARY_SHA), 1)
        # Refuse to run the former root-wide extractor in this ordinary-user sandbox.
        self.assertNotRegex(source, r"-C\s+/(?:\s|$)")
        self.assertNotIn("systemd-sysusers", source)
        for prefix in PATH_PREFIXES:
            source = re.sub(r"(?<![\w./-])" + re.escape(prefix),
                            lambda _match: str(self.root / prefix.lstrip("/")), source)
        self.assertIn(f"{PREFIX}/usr/local/bin/sendspin-cli", source)
        source = source.replace(ARCHIVE_SHA, hashlib.sha256(expected_archive).hexdigest())
        source = source.replace(BINARY_SHA, hashlib.sha256(BINARY).hexdigest())
        script = self.scripts / "install-official.sh"
        script.write_text(source)
        if download:
            (self.root / "download-fixture.tar.gz").write_bytes(archive)
        else:
            (self.scripts / ARCHIVE).write_bytes(archive)
        (self.root / "state.json").write_text(json.dumps(self.state))
        env = os.environ.copy()
        env.update(PATH=str(self.fake_bin) + os.pathsep + env["PATH"],
                   INSTALL_TEST_ROOT=str(self.root), INSTALL_TEST_ARCHIVE=ARCHIVE,
                   INSTALL_TEST_REAL_MV=shutil.which("mv"))
        return subprocess.run(["/bin/sh", str(script), "test-sendspin-ct"], env=env,
                              text=True, capture_output=True, timeout=20)

    def events(self):
        log = self.root / "commands.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def assert_unchanged(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.destination.read_bytes(), OLD_BINARY)
        self.assertFalse(any(e["command"] == "mv" for e in self.events()))

    def assert_no_package_changes(self):
        self.assertFalse(any(e["command"] == "apt-get" for e in self.events()))

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.destination.read_bytes(), BINARY)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o755)
        cache = self.root / "var/cache/sendspin-cli/v0.4.0"
        self.assertEqual((cache / "BUILD-INFO.txt").read_bytes(), BUILD_INFO)
        self.assertTrue((self.root / "single-player-masked").exists())
        self.assertFalse((self.root / "usr/local/lib").exists())
        self.assertEqual(list(cache.glob("install.*")), [])
        self.assertEqual(list(self.destination.parent.glob(".sendspin-cli.*")), [])
        moves = [e for e in self.events() if e["command"] == "mv"]
        self.assertEqual(len(moves), 1)
        self.assertEqual(Path(moves[0]["source"]).parent, self.destination.parent)
        self.assertEqual(Path(moves[0]["destination"]), self.destination)
        self.assertEqual(moves[0]["old_sha256"], hashlib.sha256(OLD_BINARY).hexdigest())
        self.assertEqual(moves[0]["source_sha256"], hashlib.sha256(BINARY).hexdigest())
        service_calls = [e["args"] for e in self.events() if e["command"] == "systemctl"]
        self.assertEqual(service_calls, [["is-active", "--quiet", "sendspin-cli.service"],
                                        ["is-enabled", "sendspin-cli.service"],
                                        ["mask", "sendspin-cli.service"], ["daemon-reload"]])
        self.assertIn("0.4.0 test fixture", result.stdout)

    def test_active_single_player_refused_before_packages(self):
        self.state["active"] = True
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_enabled_inactive_single_player_refused_before_packages(self):
        self.state["enabled"] = "enabled"
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_runtime_enabled_single_player_refused_before_packages(self):
        self.state["enabled"] = "enabled-runtime"
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_missing_audio_membership_refused_before_packages(self):
        self.state["audio"] = False
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_root_alias_account_refused_before_packages(self):
        self.state["account_uid"] = 0
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_running_cli_refused_before_packages(self):
        process = self.root / "proc/123"
        process.mkdir()
        (process / "comm").write_text("sendspin-cli\n")
        self.assert_unchanged(self.run_installer())
        self.assert_no_package_changes()

    def test_archive_checksum_failure_preserves_existing_binary(self):
        self.assert_unchanged(self.run_installer(archive=self.archive + b"corruption"))
        self.assertFalse((self.root / "single-player-masked").exists())

    def test_invalid_tar_preserves_existing_binary(self):
        invalid = b"not a gzip or tar archive"
        self.assert_unchanged(self.run_installer(archive=invalid, expected_archive=invalid))
        self.assertFalse((self.root / "single-player-masked").exists())

    def test_binary_checksum_failure_preserves_existing_binary(self):
        wrong = self.make_archive(binary=b"wrong executable")
        self.assert_unchanged(self.run_installer(archive=wrong, expected_archive=wrong))
        self.assertFalse((self.root / "single-player-masked").exists())

    def test_local_success_selective_atomic_install_without_start(self):
        self.assert_success(self.run_installer())
        self.assertFalse(any(e["command"] == "curl" for e in self.events()))

    def test_download_success_validates_real_shell_continuations(self):
        self.assert_success(self.run_installer(download=True))
        self.assertEqual(sum(e["command"] == "curl" for e in self.events()), 1)

    def test_masked_system_unit_allows_safe_reinstall(self):
        self.state["enabled"] = "masked"
        self.assert_success(self.run_installer())


if __name__ == "__main__":
    unittest.main()
