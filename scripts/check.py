#!/usr/bin/env python3
"""Read-only public example/provenance checks; no hardware or network access."""

import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
example = root / "examples/two-ca7-seven-zones"
pins = json.loads((root / "upstream-pins.json").read_text())
assert not pins["source_patches"]
assert pins["sendspin_cli"]["version"] == "0.4.0"
installer = (root / "scripts/install-official.sh").read_text()
assert pins["sendspin_cli"]["sha256"] in installer
assert pins["sendspin_cli"]["binary_sha256"] in installer

ports = set()
targets = set()
for number in range(1, 8):
    zone = f"zone-{number}"
    entries = {}
    for line in (example / f"sendspin-zones/{zone}.conf.template").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = (part.strip() for part in line.split("=", 1))
            assert key not in entries, (zone, "duplicate option", key)
            entries[key] = value
    assert entries["server"] == "@SENDSPIN_SERVER_URL@"
    assert entries["allow-unpaired"] == "false"
    assert set(entries) == {"name", "output", "port", "server", "log-level", "allow-unpaired"}
    assert entries["port"] not in ports
    ports.add(entries["port"])
    assert entries["output"] == f"pipewire:sendspin_{zone}"
    targets.add(f"sendspin_{zone}")

routing = (example / "pipewire.conf.d/60-zones.conf").read_text()
names = re.findall(r'node\.name\s*=\s*"([^"]+)"', routing)
assert len(names) == len(set(names)) == 14
assert targets <= set(names)
assert routing.count("libpipewire-module-loopback") == 7
assert routing.count("node.dont-fallback = true") == 7
assert routing.count("node.dont-move = true") == 7
assert routing.count("stream.dont-remix = true") == 14
assert routing.count("node.linger = true") == 7
client = (example / "client.conf.d/55-sendspin-room-targets.conf").read_text()
assert "sendspin_(zone-1|zone-2|zone-3|zone-4|zone-5|zone-6|zone-7)$" in client
assert "node.dont-fallback = true" in client and "node.dont-move = true" in client
hardware = (example / "pipewire.conf.d/61-ca7-physical.conf.template").read_text()
assert hardware.count("@CARD_A_ALSA_ID@") == hardware.count("@CARD_B_ALSA_ID@") == 1
assert hardware.count("factory.name = api.alsa.pcm.sink") == 2
assert hardware.count("flags = [ nofail ]") == 2
assert hardware.count('audio.format = "S16LE"') == 2
assert hardware.count("audio.channels = 8") == 2
assert hardware.count("audio.rate = 48000") == 2
assert hardware.count("audio.position = [ FL FR FC LFE RL RR SL SR ]") == 2
assert hardware.count("position = preserve") == 2
assert "resample.disable" not in hardware
clocks = re.findall(r'clock\.name\s*=\s*"([^"]+)"', hardware)
assert len(clocks) == len(set(clocks)) == 2
physical = set(re.findall(r'node\.name\s*=\s*(ca7_card_[ab])', hardware))
assert physical == {"ca7_card_a", "ca7_card_b"}
assert set(re.findall(r'target\.object\s*=\s*"(ca7_card_[ab])"', routing)) == physical
monitor = (example / "wireplumber.conf.d/51-manual-ca7.conf").read_text()
assert "main = { monitor.alsa = disabled }" in monitor
assert not (example / "wireplumber.conf.d/51-ca7.conf.template").exists()
unit = (root / "systemd/sendspin-zone@.service").read_text()
assert "%S/sendspin-zones/%i" in unit and "%t/sendspin-zones/%i/control.sock" in unit
assert "User=root" not in unit and "Restart=on-failure" in unit

for path in root.rglob("*"):
    if not path.is_file() or ".git" in path.relative_to(root).parts:
        continue
    assert path.suffix not in {".patch", ".key", ".pem", ".log", ".sock", ".deb", ".gz"}, path
    if path.suffix == ".py" or path.name == ".gitignore":
        continue
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w.])(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![\w.])", text), path
    assert "blob-keypair=" not in text and "blob-pairing_psk=" not in text, path
    if path.suffix == ".md":
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if "://" not in link and not link.startswith("#"):
                assert (path.parent / link.split("#")[0]).exists(), (path, link)

print("PASS: official pins, seven isolated examples, fail-closed configuration inventory, local links and public-file hygiene")
