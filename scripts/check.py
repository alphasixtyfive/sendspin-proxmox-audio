#!/usr/bin/env python3
"""Read-only public example/provenance checks; no hardware or network access."""

import ast
import json
import re
from pathlib import Path
from configure import load, render

root = Path(__file__).resolve().parent.parent
config = load(root / "examples/audio.toml")
generated = render(config)
pins = json.loads((root / "upstream-pins.json").read_text())
assert not pins["source_patches"]
assert pins["sendspin_cli"]["version"] == "0.4.0"
installer = (root / "scripts/install-official.sh").read_text()
assert pins["sendspin_cli"]["sha256"] in installer
assert pins["sendspin_cli"]["binary_sha256"] in installer

ports = set()
targets = set()
for zone in config["zones"]:
    entries = {}
    for line in generated[f"ct/etc/sendspin-zones/{zone}.conf"].splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = (part.strip() for part in line.split("=", 1))
            assert key not in entries, (zone, "duplicate option", key)
            entries[key] = value
    assert entries["server"] == config["server"]
    assert entries["allow-unpaired"] == "false"
    assert set(entries) == {"name", "output", "port", "server", "log-level", "allow-unpaired"}
    assert entries["port"] not in ports
    ports.add(entries["port"])
    assert entries["output"] == f"pipewire:sendspin_{zone}"
    targets.add(f"sendspin_{zone}")

assert len(targets) == 7
routing = generated["ct/etc/pipewire/pipewire.conf.d/60-zones.conf"]
names = re.findall(r'node\.name\s*=\s*"([^"]+)"', routing)
assert len(names) == len(set(names)) == 14
assert targets <= set(names)
assert routing.count("libpipewire-module-loopback") == 7
assert routing.count("node.dont-fallback = true") == 7
assert routing.count("node.dont-move = true") == 7
assert routing.count("stream.dont-remix = true") == 14
assert routing.count("node.linger = true") == 7
client = generated["ct/etc/pipewire/client.conf.d/55-sendspin-room-targets.conf"]
assert "sendspin_(" + "|".join(config["zones"]) + ")$" in client
assert "node.dont-fallback = true" in client and "node.dont-move = true" in client
hardware = generated["ct/etc/pipewire/pipewire.conf.d/61-ca7-physical.conf"]
assert hardware.count('api.alsa.path = "hw:CARD_A,0"') == hardware.count('api.alsa.path = "hw:CARD_B,0"') == 1
assert hardware.count('factory.name = "api.alsa.pcm.sink"') == 2
assert hardware.count("flags = [ nofail ]") == 2
assert hardware.count('audio.format = "S16LE"') == 2
assert hardware.count("audio.channels = 8") == 2
assert hardware.count("audio.rate = 48000") == 2
assert hardware.count("audio.position = [ FL FR FC LFE RL RR SL SR ]") == 2
assert hardware.count('position = "preserve"') == 2
assert "resample.disable" not in hardware
clocks = re.findall(r'clock\.name\s*=\s*"([^"]+)"', hardware)
assert len(clocks) == len(set(clocks)) == 2
physical = set(re.findall(r'node\.name\s*=\s*"(ca7_card_[ab])"', hardware))
assert physical == {"ca7_card_a", "ca7_card_b"}
assert set(re.findall(r'target\.object\s*=\s*"(ca7_card_[ab])"', routing)) == physical
monitor = generated["ct/etc/wireplumber/wireplumber.conf.d/51-manual-ca7.conf"]
assert "main = { monitor.alsa = disabled }" in monitor
unit = (root / "systemd/sendspin-zone@.service").read_text()
assert "%S/sendspin-zones/%i" in unit and "%t/sendspin-zones/%i/control.sock" in unit
assert "User=root" not in unit and "Restart=always" in unit and "Type=exec" in unit
assert "PartOf=sendspin-zones.target pipewire.service wireplumber.service" in unit

for daemon in ["pipewire", "wireplumber"]:
    dropin = root / f"systemd/{daemon}.service.d/50-direct-restart.conf"
    assert dropin.read_text() == "[Service]\nRestartMode=direct\n"

for path in root.rglob("*"):
    parts = path.relative_to(root).parts
    if parts[0] in {".git", "local", "backups", "downloads", "build"} or "__pycache__" in parts:
        continue
    if not path.is_file():
        continue
    assert not path.is_symlink(), path
    assert path.suffix not in {".patch", ".key", ".pem", ".log", ".sock", ".deb", ".gz"}, path
    # This checker contains the forbidden marker strings it searches for below.
    if path.resolve() == Path(__file__).resolve() or path.name == ".gitignore":
        continue
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        ast.parse(text, filename=str(path))
    assert not re.search(r"(?<![\w.])(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![\w.])", text), path
    assert "blob-keypair=" not in text and "blob-pairing_psk=" not in text, path
    if path.suffix == ".md":
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if "://" not in link and not link.startswith("#"):
                assert (path.parent / link.split("#")[0]).exists(), (path, link)

print("PASS: official pins, seven generated rooms, fail-closed configuration inventory, local links and public-file hygiene")
