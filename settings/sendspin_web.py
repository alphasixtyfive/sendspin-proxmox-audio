"""Edit Sendspin zones and prepare files with the native renderer."""

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import re
import runpy
import stat
import tempfile
from threading import Lock
import tomllib


ASSETS = Path(__file__).resolve().parent
FONT = "inter-latin-v20.woff2"
ZONE_KEY = re.compile(r"[a-z][a-z0-9-]{0,47}")
INLINE_VALUE = r"""(?:[^"'{}\r\n]|"(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*')*"""


class StaleSettings(ValueError):
    """The file changed after the client read it."""


def revision(source):
    return hashlib.sha256(source).hexdigest()


def read_topology(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("The settings file is unavailable.")
    source = path.read_bytes()
    return source, tomllib.loads(source.decode("utf-8"))


def check_revision(source, data):
    if data.get("revision") != revision(source):
        raise StaleSettings("Settings changed. Reload the saved settings and try again.")


def table_lines(lines, table):
    headers = [
        (index, line.partition("#")[0].strip())
        for index, line in enumerate(lines)
        if line.lstrip().startswith("[")
    ]
    for index, (start, header) in enumerate(headers):
        if header == f"[{table}]":
            end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
            return start + 1, end
    raise ValueError(f"Could not find the [{table}] table.")


def write_zone(source, key, zone, *, new=False):
    lines = source.splitlines(keepends=True)
    start, end = table_lines(lines, "zones")
    newline = "\r\n" if "\r\n" in source else "\n"
    if zone is not None:
        fields = ", ".join(f"{name} = {json.dumps(value, ensure_ascii=False)}"
                           for name, value in zone.items())
        entry = f"{{ {fields} }}"
    if new:
        while end > start and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
            end -= 1
        if not lines[end - 1].endswith("\n"):
            lines[end - 1] += newline
        lines.insert(end, f"{key} = {entry}{newline}")
        return "".join(lines)

    setting = re.compile(rf"([ \t]*{re.escape(key)}[ \t]*=[ \t]*)\{{{INLINE_VALUE}\}}([ \t]*(?:#[^\r\n]*)?)(\r?\n)?")
    for index in range(start, end):
        match = setting.fullmatch(lines[index])
        if match:
            if zone is None:
                del lines[index]
            else:
                lines[index] = match[1] + entry + match[2] + (match[3] or "")
            return "".join(lines)
    raise ValueError("This zone uses a different TOML layout. Edit it in the settings file.")


def remove_gain_membership(source, config, key):
    policy = config.get("idle_gain")
    if not policy or key not in policy["zones"]:
        return source
    lines = source.splitlines(keepends=True)
    start, end = table_lines(lines, "idle_gain")
    members = [member for member in policy["zones"] if member != key]
    if not members:
        del config["idle_gain"]
        del lines[start - 1:end]
        return "".join(lines)

    policy["zones"] = members
    setting = re.compile(r"([ \t]*zones[ \t]*=[ \t]*)\[[^\]\r\n]*\]([ \t]*(?:#[^\r\n]*)?)(\r?\n)?")
    for index in range(start, end):
        match = setting.fullmatch(lines[index])
        if match:
            lines[index] = match[1] + json.dumps(members) + match[2] + (match[3] or "")
            return "".join(lines)
    raise ValueError("Could not update the shared idle-gain list.")


def new_key(name, zones):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if not base or not base[0].isalpha():
        base = f"zone-{base}".rstrip("-")
    key, suffix = base, 2
    while key in zones:
        key = f"{base}-{suffix}"
        suffix += 1
    return key


def replace_topology(path, candidate, data):
    metadata = path.stat()
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".sendspin-", suffix=".toml")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            if hasattr(os, "fchown"):
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, stat.S_IMODE(metadata.st_mode))
        check_revision(path.read_bytes(), data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def update_zone(path, data, validate, prepare, *, remove=False):
    original, config = read_topology(path)
    check_revision(original, data)
    source = original.decode("utf-8")
    zones = config["zones"]
    key = data.get("room")
    new = key is None and not remove
    if not new and (not isinstance(key, str) or not ZONE_KEY.fullmatch(key) or key not in zones):
        raise ValueError("Choose an existing zone.")

    if remove:
        del zones[key]
        source = remove_gain_membership(write_zone(source, key, None), config, key)
    else:
        name = data.get("name")
        player = data.get("player_name", "")
        socket = data.get("socket")
        enabled = data.get("enabled")
        if not isinstance(name, str) or not name.strip() or not isinstance(player, str):
            raise ValueError("Enter a zone name and, optionally, a player name.")
        if not isinstance(socket, str) or socket.count("/") != 1:
            raise ValueError("Choose a stereo output.")
        if type(enabled) is not bool:
            raise ValueError("Choose whether the zone is enabled.")

        if new:
            key = new_key(name, zones)
            used = {zone["port"] for zone in zones.values()}
            port = next(port for port in range(8931, 65536) if port not in used)
            zones[key] = {"port": port}
        zone = zones[key]
        before = zone.copy()
        zone["name"] = name
        if player:
            zone["player_name"] = player
        else:
            zone.pop("player_name", None)
        zone["device"], zone["output"] = socket.split("/")
        if zone.get("enabled", True) != enabled:
            zone["enabled"] = enabled
        if new or zone != before:
            source = write_zone(source, key, zone, new=new)

    checked = validate(config)
    candidate = source.encode("utf-8")
    if tomllib.loads(source) != config:
        raise ValueError("Could not preserve the rest of the settings.")
    prepare(candidate, checked)
    if candidate != original:
        replace_topology(path, candidate, data)
    else:
        check_revision(path.read_bytes(), data)
    return candidate, checked, key


def renderer_revision(project, calibration):
    digest = hashlib.sha256(calibration)
    for folder in ("scripts", "systemd", "examples/two-ca7-seven-zones"):
        for path in sorted((project / folder).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".service", ".conf"):
                digest.update(path.relative_to(project).as_posix().encode("utf-8"))
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.digest()


def installation_path(stages, source, inputs):
    return stages / f"saved-{revision(inputs + source)[:24]}"


def prepare_installation(directory, config, renderer, calibration):
    existing = directory.exists() or directory.is_symlink()
    if existing:
        try:
            renderer["verify"](config, directory, calibration)
            return
        except (OSError, ValueError):
            pass
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix=".sendspin-") as scratch:
        candidate = Path(scratch) / "files"
        renderer["stage"](config, candidate, calibration)
        renderer["verify"](config, candidate, calibration)
        previous = Path(scratch) / "previous"
        if existing:
            directory.rename(previous)
        try:
            candidate.rename(directory)
        except OSError:
            if existing:
                previous.rename(directory)
            raise


def calibration_source(path):
    credentials = os.environ.get("CREDENTIALS_DIRECTORY")
    if path is None and credentials:
        credential = Path(credentials) / "calibration"
        if credential.is_file():
            path = credential
    return path.read_bytes() if path else b"null"


def describe(source, config, pins, outputs):
    devices = config["devices"]
    return {
        "version": pins["sendspin_cli"]["version"],
        "library": pins["sendspin_core"]["version"],
        "revision": revision(source),
        "outputs": [
            {"value": f"{key}/{output}", "label": f"{card['alsa_id']} · {'/'.join(pair)}"}
            for key, card in devices.items() for output, pair in outputs.items()
        ],
        "zones": [
            {"key": key, "name": zone["name"], "player": zone.get("player_name", ""),
             "output": f"{devices[zone['device']]['alsa_id']} · {'/'.join(outputs[zone['output']])}",
             "enabled": zone.get("enabled", True), "socket": f"{zone['device']}/{zone['output']}",
             "port": zone["port"]}
            for key, zone in config["zones"].items()
        ],
    }


class SettingsServer(ThreadingHTTPServer):
    def __init__(self, args):
        self.config_path = args.config
        self.stages = args.stages
        self.clients = {str(ip) for ip in args.client or [args.bind]}
        self.renderer = runpy.run_path(str(args.project / "scripts/configure.py"))
        self.pins = json.loads((args.project / "upstream-pins.json").read_bytes())
        self.page = (ASSETS / "sendspin.html").read_bytes()
        self.font = (ASSETS / FONT).read_bytes()
        self.edit_lock = Lock()
        self.started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.restart_available = bool(os.environ.get("INVOCATION_ID"))
        self.restarting = False

        calibration = calibration_source(args.calibration)
        self.calibration = json.loads(calibration)
        self.inputs = renderer_revision(args.project, calibration)
        self.stages.mkdir(mode=0o700, parents=True, exist_ok=True)

        source, config = self.read_config()
        self.ready_installation = None
        try:
            self.prepare(source, config)
            self.ready_installation = self.installation_path(source)
        except (OSError, ValueError) as error:
            print(f"Could not prepare the saved installation files: {error}", flush=True)

        super().__init__((str(args.bind), args.port), Editor)
        self.host = f"{args.bind}:{self.server_port}"
        self.origin = f"http://{self.host}"

    def read_config(self):
        source, config = read_topology(self.config_path)
        return source, self.renderer["validate"](config)

    def installation_path(self, source):
        return installation_path(self.stages, source, self.inputs)

    def prepare(self, source, config):
        prepare_installation(self.installation_path(source), config, self.renderer, self.calibration)


class Editor(BaseHTTPRequestHandler):
    server: SettingsServer

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        pass

    def reply(self, status, content, mime="application/json; charset=utf-8", *, cache="no-store"):
        body = content if isinstance(content, bytes) else json.dumps(content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        return (self.client_address[0] in self.server.clients
                and self.headers.get("Host") == self.server.host)

    def config(self, source, config, key=None):
        data = describe(source, config, self.server.pins, self.server.renderer["OUTPUTS"])
        data["started"] = self.server.started
        data["restart"] = self.server.restart_available
        directory = self.server.installation_path(source)
        if directory == self.server.ready_installation and (directory / "manifest.json").is_file():
            data["installation"] = str(directory)
        if key is not None:
            data["saved"] = key
        self.reply(200, data)

    def do_GET(self):
        if not self.allowed():
            self.reply(403, {"error": "This computer is not allowed to open Sendspin Settings."})
        elif self.path == "/":
            self.reply(200, self.server.page, "text/html; charset=utf-8")
        elif self.path == f"/{FONT}":
            self.reply(200, self.server.font, "font/woff2", cache="private, max-age=31536000, immutable")
        elif self.path == "/api/config":
            try:
                self.config(*self.server.read_config())
            except (OSError, KeyError, ValueError):
                self.reply(500, {"error": "Could not read the saved settings."})
        else:
            self.reply(404, {"error": "Page not found."})

    def do_POST(self):
        if not self.allowed() or self.headers.get("Origin") != self.server.origin:
            self.reply(403, {"error": "Open Sendspin Settings from the allowed computer."})
            return
        if self.path not in ("/api/zone", "/api/zone/remove", "/api/restart"):
            self.reply(404, {"error": "Page not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid request.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Invalid request.")
            with self.server.edit_lock:
                if self.server.restarting:
                    self.reply(503, {"error": "The settings service is restarting."})
                elif self.path == "/api/restart":
                    self.restart()
                else:
                    self.change(data)
        except StaleSettings as error:
            self.reply(409, {"error": str(error)})
        except ValueError as error:
            message = str(error)
            if message == "duplicate enabled device/output allocation":
                message = "That stereo output already belongs to an enabled zone."
            self.reply(400, {"error": message})
        except (OSError, KeyError):
            self.reply(500, {"error": "Could not save the settings and installation files."})

    def change(self, data):
        source, config, key = update_zone(
            self.server.config_path, data, self.server.renderer["validate"],
            self.server.prepare, remove=self.path == "/api/zone/remove",
        )
        self.server.ready_installation = self.server.installation_path(source)
        self.config(source, config, key)

    def restart(self):
        if not self.server.restart_available:
            self.reply(409, {"error": "Restart is available when running as a systemd service."})
            return
        self.server.restarting = True
        try:
            self.reply(202, {})
        finally:
            self.server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", type=IPv4Address, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--client", type=IPv4Address, action="append")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, help="host calibration export for idle gains")
    parser.add_argument("--stages", type=Path, required=True)
    args = parser.parse_args()
    if args.bind.is_unspecified:
        parser.error("Bind to a specific IPv4 address.")
    if not args.bind.is_loopback and not args.client:
        parser.error("A network listener needs at least one --client address.")

    with SettingsServer(args) as server:
        print(f"Sendspin Settings on {server.origin}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
