#!/usr/bin/env python3
"""Validate one topology and stage native files. Never install or restart anything."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = {"front": ["FL", "FR"], "surround": ["RL", "RR"],
           "side": ["SL", "SR"], "center_sub": ["FC", "LFE"]}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def table(value, allowed, required, where):
    require(type(value) is dict, where + " must be a table")
    require(not (value.keys() - allowed), where + ": unknown keys")
    require(not (required - value.keys()), where + ": missing keys")


def text(value, pattern, where):
    require(type(value) is str and re.fullmatch(pattern, value) is not None, "invalid " + where)
    return value


def label(value, where):
    require(type(value) is str and 1 <= len(value) <= 128 and value == value.strip()
            and all(c.isprintable() and c not in "#;=" for c in value), "invalid " + where)
    return value


def number(value, low, high, where):
    require(type(value) is int and low <= value <= high, "invalid " + where)
    return value


def unique(values, where):
    require(len(values) == len(set(values)), "duplicate " + where)


def load(path):
    with Path(path).open("rb") as stream:
        config = tomllib.load(stream)
    return validate(config)


def validate(c):
    table(c, {"version", "server", "layout", "devices", "zones", "host"},
          {"version", "server", "devices", "zones"}, "configuration")
    number(c["version"], 1, 1, "version")
    server = c["server"]
    require(type(server) is str and server.isascii() and not any(x.isspace() for x in server)
            and "\\" not in server and all(ord(x) >= 32 and ord(x) != 127 for x in server), "invalid server")
    try:
        url = urlsplit(server)
        port = url.port
    except ValueError:
        raise ValueError("invalid server URL") from None
    require(url.scheme in {"ws", "wss"} and url.hostname and port != 0
            and not url.username and not url.password and not url.query and not url.fragment
            and re.fullmatch(r"[A-Za-z0-9.:[\]-]+", url.netloc) is not None, "invalid server URL")
    layout = c.get("layout", {})
    table(layout, {"sink_prefix", "routing_file", "wireplumber_file"}, set(), "layout")
    layout = {"sink_prefix": "sendspin_", "routing_file": "60-zones.conf",
              "wireplumber_file": "51-manual-ca7.conf", **layout}
    text(layout["sink_prefix"], r"[A-Za-z][A-Za-z0-9_-]{0,63}", "sink prefix")
    for key in ["routing_file", "wireplumber_file"]:
        text(layout[key], r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\.conf", key)
    require(layout["routing_file"] not in {"20-fixed-rate.conf", "61-ca7-physical.conf"},
            "routing filename collides with a generated file")
    c = {**c, "layout": layout}
    devices = c["devices"]
    require(type(devices) is dict and 1 <= len(devices) <= 16, "need 1–16 devices")
    normalized = {}
    for key, d in devices.items():
        text(key, r"[a-z][a-z0-9-]{0,47}", "device key")
        table(d, {"profile", "alsa_id", "node", "clock", "description", "usb_port", "slots"},
              {"profile", "alsa_id"}, "device " + key)
        require(d["profile"] == "ca7", "only the reviewed ca7 profile is supported")
        text(d["alsa_id"], r"[A-Za-z][A-Za-z0-9_]{0,14}", "ALSA ID")
        d = {"node": "ca7_card_" + key, "clock": "api.alsa.ca7_" + key,
             "description": "CUBILUX CA7 card " + key.upper() + " eight-channel output", **d}
        for field in ["node", "clock"]:
            text(d[field], r"[A-Za-z][A-Za-z0-9_.-]{1,127}", field)
        label(d["description"], "device description")
        normalized[key] = d
    c["devices"] = normalized
    for field in ["alsa_id", "node", "clock"]:
        unique([d[field] for d in normalized.values()], field)
    zones = c["zones"]
    require(type(zones) is dict and 1 <= len(zones) <= 64, "need 1–64 zones")
    active, sockets, ports, nodes = [], [], [], []
    for key, z in zones.items():
        text(key, r"[a-z][a-z0-9-]{0,47}", "zone key")
        table(z, {"name", "player_name", "device", "output", "port", "enabled"},
              {"name", "device", "output", "port"}, "zone " + key)
        label(z["name"], "zone name")
        label(z.get("player_name", z["name"]), "player name")
        require(type(z.get("enabled", True)) is bool, "enabled must be boolean")
        require(type(z["device"]) is str and z["device"] in normalized, "unknown zone device")
        require(type(z["output"]) is str and z["output"] in OUTPUTS, "unknown stereo output")
        number(z["port"], 1024, 65535, "player port")
        if z.get("enabled", True):
            active.append(key)
            sockets.append((z["device"], z["output"]))
            ports.append(z["port"])
            nodes.extend([layout["sink_prefix"] + key, "playback." + layout["sink_prefix"] + key])
    require(active, "at least one enabled zone required")
    unique(sockets, "enabled device/output allocation")
    unique(ports, "enabled player port")
    unique(nodes + [d["node"] for d in normalized.values()], "PipeWire node")
    if "host" in c:
        host = c["host"]
        table(host, {"ctid", "user", "uid"}, {"ctid", "user", "uid"}, "host")
        number(host["ctid"], 100, 999999999, "CT ID")
        number(host["uid"], 1, 65533, "audio UID")
        text(host["user"], r"[a-z_][a-z0-9_-]{0,31}", "audio user")
        require(host["user"] != "root", "audio account must be unprivileged")
        require(len(normalized) == 2, "host recovery requires exactly two CA7 devices")
    slots, usb_ports = [], []
    for d in normalized.values():
        require(("usb_port" in d) == ("slots" in d), "usb_port and slots must be supplied together")
        require("host" not in c or "usb_port" in d, "host recovery needs each USB port and slots")
        require("host" in c or "usb_port" not in d, "USB recovery fields require a host table")
        if "usb_port" in d:
            text(d["usb_port"], r"\d+-\d+(?:\.\d+)*", "USB port")
            require(type(d["slots"]) is list and len(d["slots"]) == 2, "need two devN slots per device")
            slots.extend(text(x, r"dev[0-9]+", "device slot") for x in d["slots"])
            usb_ports.append(d["usb_port"])
    unique(slots, "device slot")
    unique(usb_ports, "USB port")
    return c


def spa(value, level=0):
    """Emit PipeWire's native configuration syntax, quoting every string/key."""
    if type(value) is dict:
        lines = [" " * (level + 2) + json.dumps(k) + " = " + spa(v, level + 2)
                 for k, v in value.items()]
        return "{\n" + "\n".join(lines) + "\n" + " " * level + "}"
    if type(value) is list:
        return "[ " + " ".join(spa(v, level) for v in value) + " ]"
    return json.dumps(value, ensure_ascii=True)


def native(values):
    return "\n".join(k + " = " + spa(v) for k, v in values.items()) + "\n"


def render(c):
    c = validate(c)
    files, modules, objects = {}, [], []
    zones = {k: z for k, z in c["zones"].items() if z.get("enabled", True)}
    prefix = c["layout"]["sink_prefix"]
    for key, d in c["devices"].items():
        objects.append({"factory": "adapter", "args": {
            "factory.name": "api.alsa.pcm.sink", "node.name": d["node"],
            "node.description": d["description"], "media.class": "Audio/Sink",
            "api.alsa.path": "hw:" + d["alsa_id"] + ",0", "clock.name": d["clock"],
            "audio.format": "S16LE", "audio.rate": 48000, "audio.allowed-rates": [48000],
            "audio.channels": 8, "audio.position": ["FL", "FR", "FC", "LFE", "RL", "RR", "SL", "SR"],
            "api.alsa.use-chmap": True, "channelmix.disable": True, "node.suspend-on-idle": True,
            "session.suspend-timeout-seconds": 15, "adapter.auto-port-config": {
                "mode": "dsp", "monitor": False, "control": False, "position": "preserve"}},
            "flags": ["nofail"]})
    for key, z in zones.items():
        sink = prefix + key
        modules.append({"name": "libpipewire-module-loopback", "args": {
            "node.description": z["name"], "audio.rate": 48000, "audio.channels": 2,
            "capture.props": {"node.name": sink, "media.class": "Audio/Sink",
                              "audio.position": ["FL", "FR"], "stream.dont-remix": True},
            "playback.props": {"node.name": "playback." + sink, "audio.position": OUTPUTS[z["output"]],
                               "target.object": c["devices"][z["device"]]["node"],
                               "node.passive": True, "node.dont-fallback": True, "node.dont-move": True,
                               "node.dont-reconnect": False, "node.linger": True, "stream.dont-remix": True}}})
        files["ct/etc/sendspin-zones/" + key + ".conf"] = (
            "name = " + z.get("player_name", z["name"]) + "\noutput = pipewire:" + sink
            + "\nport = " + str(z["port"]) + "\nserver = " + c["server"]
            + "\nlog-level = info\nallow-unpaired = false\n")
    pw = "ct/etc/pipewire/pipewire.conf.d/"
    files[pw + c["layout"]["routing_file"]] = native({"context.modules": modules})
    files[pw + "61-ca7-physical.conf"] = native({"context.objects": objects})
    example = ROOT / "examples/two-ca7-seven-zones"
    files[pw + "20-fixed-rate.conf"] = (example / "pipewire.conf.d/20-fixed-rate.conf").read_text()
    files["ct/etc/wireplumber/wireplumber.conf.d/" + c["layout"]["wireplumber_file"]] = (
        example / "wireplumber.conf.d/51-manual-ca7.conf").read_text()
    files["ct/etc/pipewire/client.conf.d/55-sendspin-room-targets.conf"] = native({"stream.rules": [{
        "matches": [{"application.name": "sendspin-cli", "media.class": "Stream/Output/Audio",
                     "target.object": "~^" + prefix + "(" + "|".join(zones) + ")$"}],
        "actions": {"update-props": {"node.dont-fallback": True, "node.dont-move": True}}}]})
    user = "ct/user/"
    files[user + "sendspin-zones.target"] = (
        "[Unit]\nDescription=Stock Sendspin room players\nWants=pipewire.service wireplumber.service\n"
        "After=pipewire.service wireplumber.service\nWants="
        + " ".join("sendspin-zone@" + k + ".service" for k in zones)
        + "\n\n[Install]\nWantedBy=default.target\n")
    for path in ["sendspin-zone@.service", "pipewire.service.d/50-direct-restart.conf",
                 "wireplumber.service.d/50-direct-restart.conf"]:
        files[user + path] = (ROOT / "systemd" / path).read_text()
    if "host" in c:
        host = {**c["host"], "routing_file": "/etc/pipewire/pipewire.conf.d/" + c["layout"]["routing_file"],
                "cards": [{"usb_port": d["usb_port"], "vendor": "0bda", "product": "4f25",
                           "alsa_id": d["alsa_id"], "node": d["node"], "slots": d["slots"]}
                          for d in c["devices"].values()]}
        files["host/etc/sendspin-usb-recovery.json"] = json.dumps(host, indent=2) + "\n"
    return files


def stage(c, destination):
    files = render(c)
    destination = Path(destination)
    # mkdir is exclusive: an existing directory, file or symlink is never reused.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = {}
    for name, content in sorted(files.items()):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        with path.open("xb") as stream:
            stream.write(data)
        manifest[name] = hashlib.sha256(data).hexdigest()
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "render"])
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, help="fresh staging directory; parent must exist")
    args = parser.parse_args()
    try:
        require((args.command == "render") == (args.output is not None), "only render requires --output")
        config = load(args.config)
        if args.command == "render":
            manifest = stage(config, args.output)
            print(f"Staged {len(manifest)} native files; nothing installed or restarted.")
        else:
            print("Configuration valid; nothing changed.")
    except (ValueError, OSError) as error:
        # Do not echo configuration values, URLs or TOML source lines.
        print("Configuration failed: " + (str(error) if type(error) is ValueError else type(error).__name__),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
