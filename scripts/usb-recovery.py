#!/usr/bin/env python3
"""Optional Proxmox-host USB recovery. No playback, package changes or private APIs."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time

CONFIG = Path('/etc/sendspin-usb-recovery.json')
RUNTIME = Path('/run/sendspin-usb-recovery')
DISABLED = Path('/etc/sendspin-usb-recovery.disabled')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def secure(path, directory=False):
    s = path.lstat()
    require(s.st_uid == 0 and not s.st_mode & 0o022, 'unsafe owner/mode: ' + str(path))
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode),
            'unexpected file type: ' + str(path))


def runtime():
    for p in [RUNTIME, RUNTIME / 'events']:
        p.mkdir(mode=0o700, exist_ok=True)
        secure(p, directory=True)


def save(name, value):
    p = RUNTIME / name
    temporary = RUNTIME / (name + '.' + str(os.getpid()) + '-' + str(time.monotonic_ns()) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, p)


def read(name, default):
    p = RUNTIME / name
    if not p.exists():
        return default
    secure(p)
    return json.loads(p.read_text())


def load_config(path=CONFIG):
    secure(path)
    c = json.loads(path.read_text())
    require(set(c) == {'ctid', 'user', 'uid', 'routing_file', 'cards'}, 'unknown/missing config keys')
    require(type(c['ctid']) is int and 100 <= c['ctid'] <= 999999999, 'invalid CTID')
    require(re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', c['user']) is not None, 'invalid user')
    require(type(c['uid']) is int and 1 <= c['uid'] <= 65533, 'invalid audio UID')
    require(re.fullmatch(r'/etc/pipewire/pipewire\.conf\.d/[a-zA-Z0-9_.-]+\.conf', c['routing_file'])
            is not None, 'invalid routing file')
    require(isinstance(c['cards'], list) and len(c['cards']) == 2, 'exactly two cards required')
    slots, ids, ports, nodes = [], [], [], []
    for card in c['cards']:
        require(set(card) == {'usb_port', 'vendor', 'product', 'alsa_id', 'node', 'slots'}, 'card config keys')
        require(re.fullmatch(r'\d+-\d+(?:\.\d+)*', card['usb_port']) is not None, 'invalid physical port')
        require(all(re.fullmatch(r'[0-9a-f]{4}', card[k]) for k in ['vendor', 'product']), 'invalid USB ID')
        require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,14}', card['alsa_id']) is not None, 'invalid ALSA ID')
        require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]+', card['node']) is not None, 'invalid physical node')
        require(isinstance(card['slots'], list) and len(card['slots']) == 2
                and all(re.fullmatch(r'dev[0-9]+', x) for x in card['slots']), 'invalid devN slots')
        slots += card['slots']; ids.append(card['alsa_id']); ports.append(card['usb_port']); nodes.append(card['node'])
    require(len(set(slots)) == 4 and len(set(ids)) == len(set(ports)) == len(set(nodes)) == 2,
            'duplicate card identity/node/slot')
    return c


def rules(c):
    ports = '|'.join(card['usb_port'] for card in c['cards'])
    command = 'RUN+="/usr/local/libexec/sendspin-usb-recovery event"'
    return ('# Generated from the private recovery configuration; no device access is granted here.\n'
            'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", KERNEL=="' + ports + '", '
            'ACTION=="add|remove|bind|unbind", ' + command + '\n'
            'SUBSYSTEM=="sound", KERNEL=="controlC[0-9]*", KERNELS=="' + ports + '", '
            'ACTION=="add|change|remove", ' + command + '\n')


def run(args, timeout=30):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, 'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
    # Do not expose CLI config, paired state or command output in failure logs.
    require(p.returncode == 0, 'command failed: ' + args[0] + ' (' + str(p.returncode) + ')')
    return p.stdout


def ct(c, *args):
    return run(['pct', 'exec', str(c['ctid']), '--', *args])


def user(c, *args):
    return ct(c, 'runuser', '-u', c['user'], '--', 'env',
              'XDG_RUNTIME_DIR=/run/user/' + str(c['uid']),
              'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/' + str(c['uid']) + '/bus', *args)


def fields(text):
    return dict(line.split(': ', 1) for line in text.splitlines() if ': ' in line)


def config(c):
    result = fields(run(['pct', 'config', str(c['ctid']), '--current', '1']))
    require(fields(run(['pct', 'config', str(c['ctid'])])) == result, 'CT has unapplied pending changes')
    allowed = {s for card in c['cards'] for s in card['slots']}
    require(result.get('unprivileged') == '1', 'only the reviewed unprivileged CT is supported')
    require(not result.get('lock'), 'CT has a Proxmox task lock')
    require({x for x in result if re.fullmatch(r'dev\d+', x)} <= allowed, 'unexpected CT device grant')
    return result


def wait_config(c, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        still_enabled()
        try:
            return config(c)
        except RuntimeError as exc:
            if str(exc) != 'CT has a Proxmox task lock' or time.monotonic() >= deadline:
                raise
        time.sleep(1)


def device_value(path):
    return path + ',gid=29,uid=0,mode=0660'


def parse_grants(conf):
    result = {}
    for key, value in conf.items():
        if not re.fullmatch(r'dev\d+', key):
            continue
        parts = value.split(',')
        require(re.fullmatch(r'/dev/snd/(?:controlC\d+|pcmC\d+D0p)', parts[0]) is not None,
                'non-speaker/control device grant')
        options = dict(x.split('=', 1) for x in parts[1:])
        require(len(parts) == 4 and options == {'gid': '29', 'uid': '0', 'mode': '0660'},
                'unexpected CT device permissions')
        require(parts[0] not in result.values(), 'duplicate device grant')
        result[key] = parts[0]
    return result


def inventory(c, sysfs=Path('/sys'), dev=Path('/dev')):
    observed = {}
    for card in c['cards']:
        port = sysfs / 'bus/usb/devices' / card['usb_port']
        if not port.exists():
            continue
        require((port / 'idVendor').read_text().strip() == card['vendor']
                and (port / 'idProduct').read_text().strip() == card['product'], 'unknown hardware at configured port')
        matches = [p for p in (sysfs / 'class/sound').glob('card[0-9]*')
                   if port.resolve() in p.resolve().parents]
        # USB may be present while the audio driver is unbound or still enumerating.
        if not matches:
            continue
        require(len(matches) == 1, 'ambiguous ALSA card at configured USB port')
        p = matches[0]
        require((p / 'id').read_text().strip() == card['alsa_id'], 'card port/ALSA ID mismatch')
        number = int(p.name[4:])
        paths = [dev / 'snd' / ('controlC' + str(number)), dev / 'snd' / ('pcmC' + str(number) + 'D0p')]
        if not all(p.exists() for p in paths):
            continue
        for node in paths:
            s = node.stat()
            require(stat.S_ISCHR(s.st_mode) and os.major(s.st_rdev) == 116, 'unexpected ALSA device type/major')
        observed[card['alsa_id']] = {'number': number, 'card_instance': p.resolve().stat().st_ino,
                                     'usb_devnum': (port / 'devnum').read_text().strip(),
                                     'paths': ['/dev/snd/' + p.name for p in paths]}
    require(len({x['number'] for x in observed.values()}) == len(observed), 'card identities overlap')
    return observed


def desired_grants(c, observed, current):
    paths = {p for v in observed.values() for p in v['paths']}
    # Two identical cards exchanging reserved indices need no permission change.
    if set(current.values()) == paths:
        return current.copy()
    return {slot: path for card in c['cards'] if card['alsa_id'] in observed
            for slot, path in zip(card['slots'], observed[card['alsa_id']]['paths'])}


def alsa_tree(text):
    lexer = shlex.shlex(text, posix=True, punctuation_chars='{}')
    lexer.whitespace_split = True
    tokens = iter(lexer)

    def block(nested):
        out = {}
        for key in tokens:
            if key == '}':
                require(nested, 'unexpected ALSA closing brace')
                return out
            require(key not in out and key != '{', 'duplicate/invalid ALSA state key')
            value = next(tokens, None)
            require(value is not None and value != '}', 'incomplete ALSA state')
            out[key] = block(True) if value == '{' else value
        require(not nested, 'unterminated ALSA state')
        return out
    return block(False)


def calibration(state, ident):
    card = alsa_tree(state).get('state.' + ident)
    require(isinstance(card, dict), 'saved ALSA calibration missing for ' + ident)
    controls = []
    for key, values in card.items():
        if not key.startswith('control.') or values.get('iface') != 'MIXER':
            continue
        if 'write' not in values.get('comment', {}).get('access', '').split():
            continue
        name = values.get('name', '')
        require(name and "'" not in name and '\n' not in name, 'unsupported ALSA control name')
        selector = "iface=MIXER,name='" + name + "'"
        for k in ['index', 'device', 'subdevice']:
            if k in values:
                require(values[k].isdigit(), 'invalid ALSA control selector')
                selector += ',' + k + '=' + values[k]
        keys = [k for k in values if k == 'value' or re.fullmatch(r'value\.\d+', k)]
        keys.sort(key=lambda k: -1 if k == 'value' else int(k.split('.')[1]))
        require(keys and all(isinstance(values[k], str) for k in keys), 'unsupported ALSA values')
        normalize = lambda x: {'true': 'on', 'false': 'off'}.get(x, x)
        controls.append((selector, [normalize(values[k]) for k in keys]))
    require(controls, 'no saved writable mixer controls')
    return controls


def verify_calibration(ident, expected):
    for selector, values in expected:
        text = run(['amixer', '-c', ident, 'cget', selector])
        found = re.search(r'(?m)^\s*: values=(.*)$', text)
        require(found is not None and found[1].strip().split(',') == values,
                'saved/live mixer mismatch: ' + ident)


def restore_calibration(ident):
    path = Path('/var/lib/alsa/asound.state')
    secure(path)
    source = path.read_text()
    expected = calibration(source, ident)
    # The existing host state file remains the sole gain owner; no init/default fallback.
    run(['alsactl', '-I', 'restore', ident])
    require(path.read_text() == source, 'saved mixer state changed during recovery')
    verify_calibration(ident, expected)


def service_states(c):
    text = user(c, 'systemctl', '--user', 'show', 'sendspin-zones.target', 'pipewire.service',
                'wireplumber.service', 'sendspin-zone@*.service', '--property=Id,ActiveState,SubState,MainPID')
    states = {}
    for section in text.strip().split('\n\n'):
        p = dict(line.split('=', 1) for line in section.splitlines() if '=' in line)
        if 'Id' in p:
            states[p['Id']] = p
    return states


def active_rooms(states):
    return {name for name, s in states.items() if re.fullmatch(r'sendspin-zone@[a-z0-9-]+\.service', name)
            and s.get('ActiveState') in {'active', 'activating'}}


def target_rooms(c):
    # list-unit-files can omit instances created through a target's wants directory.
    text = user(c, 'systemctl', '--user', 'show', 'sendspin-zones.target', '--property=Wants', '--value')
    return {name for name in text.split() if re.fullmatch(r'sendspin-zone@[a-z0-9-]+\.service', name)}


def native_adapters(c):
    # Use the vendor parser and existing merged configuration, not a second adapter template.
    text = user(c, '/bin/bash', '-o', 'pipefail', '-c',
                'pw-config -n pipewire.conf merge context.objects | spa-json-dump')
    objects = json.loads(text)
    wanted = {card['node']: card for card in c['cards']}
    selected = {}
    for obj in objects:
        args = obj.get('args', {})
        if args.get('factory.name') != 'api.alsa.pcm.sink':
            continue
        name = args.get('node.name')
        require(obj.get('factory') == 'adapter' and name in wanted and name not in selected,
                'unmanaged/duplicate native adapter definition')
        require(args.get('api.alsa.path') == 'hw:' + wanted[name]['alsa_id'] + ',0'
                and str(args.get('audio.channels')) == '8' and str(args.get('audio.rate')) == '48000'
                and args.get('audio.format') == 'S16LE' and args.get('media.class') == 'Audio/Sink',
                'native adapter definition mismatch')
        selected[name] = {**args, 'object.linger': True}
    require(set(selected) == set(wanted), 'native adapter definitions missing')
    return selected


def refresh_physical(c, observed, previous, force=False):
    definitions = native_adapters(c)
    for card in c['cards']:
        ident = card['alsa_id']
        if not force and previous is not None and previous.get(ident) == observed.get(ident):
            continue
        still_enabled()
        require(inventory(c) == observed, 'hardware changed before adapter refresh')
        graph = json.loads(user(c, 'pw-dump'))
        found = [x for x in graph if x.get('type') == 'PipeWire:Interface:Node'
                 and x.get('info', {}).get('props', {}).get('node.name') == card['node']]
        require(len(found) <= 1, 'duplicate physical adapter node')
        if found:
            user(c, 'pw-cli', 'destroy', str(found[0]['id']))
        if ident in observed:
            user(c, 'pw-cli', 'create-node', 'adapter', json.dumps(definitions[card['node']]))


def stream_idle(text):
    # Discard all other status lines: status can also contain private pairing information.
    fields = {key: value for key, value in (line.split(': ', 1) for line in text.splitlines()
              if line.startswith(('trust: ', 'stream: ')))}
    require(fields.get('trust') == 'paired' and fields.get('stream') in {'idle', 'receiving'},
            'cannot establish paired stream status')
    return fields['stream'] == 'idle'


def wait_idle(c, rooms, observed, timeout=90):
    deadline = time.monotonic() + timeout
    stable = 0
    while time.monotonic() < deadline:
        still_enabled()
        require(inventory(c) == observed, 'hardware changed while waiting for idle streams')
        all_idle = True
        for unit in sorted(rooms):
            room = unit.removeprefix('sendspin-zone@').removesuffix('.service')
            try:
                text = user(c, '/usr/local/bin/sendspin-cli', 'status', '--control-socket',
                            '/run/user/' + str(c['uid']) + '/sendspin-zones/' + room + '/control.sock')
                idle = stream_idle(text)
            except RuntimeError:
                idle = False
            all_idle = idle and all_idle
        stable = stable + 1 if all_idle else 0
        if stable >= 2:
            return
        time.sleep(1)
    raise RuntimeError('CT mapping refresh deferred: pause playback, allow announcement restoration, then recover')


def routes(text):
    entries = []
    pattern = r'capture\.props\s*=\s*\{([^{}]*)\}\s*playback\.props\s*=\s*\{([^{}]*)\}'
    for capture, playback in re.findall(pattern, text, re.S):
        def value(section, key):
            m = re.search(re.escape(key) + r'\s*=\s*"([^"\n]+)"', section)
            require(m is not None, 'missing routing property: ' + key)
            return m[1]
        pair = re.search(r'audio\.position\s*=\s*\[([^]]+)\]', playback)
        require(pair is not None and len(pair[1].split()) == 2, 'invalid room stereo pair')
        entries.append((value(capture, 'node.name'), value(playback, 'node.name'),
                        value(playback, 'target.object'), pair[1].split()))
    require(entries and len({x[0] for x in entries}) == len(entries), 'missing/duplicate room routes')
    return entries


def verify_graph(c, observed, expected_routes):
    graph = json.loads(user(c, 'pw-dump'))
    nodes = {x['id']: x.get('info', {}).get('props', {}) for x in graph if x['type'] == 'PipeWire:Interface:Node'}
    ports = {x['id']: x.get('info', {}).get('props', {}) for x in graph if x['type'] == 'PipeWire:Interface:Port'}
    links = [x.get('info', {}) for x in graph if x['type'] == 'PipeWire:Interface:Link']
    def named(name):
        return [(i, p) for i, p in nodes.items() if p.get('node.name') == name]
    physical = set()
    clocks = []
    for card in c['cards']:
        found = named(card['node'])
        present = card['alsa_id'] in observed
        require(len(found) == int(present), 'physical adapter availability mismatch')
        if present:
            physical.add(card['node'])
            p = found[0][1]
            clocks.append(p.get('clock.name'))
            require(p.get('api.alsa.path') == 'hw:' + card['alsa_id'] + ',0'
                    and str(p.get('audio.channels')) == '8' and str(p.get('audio.rate')) == '48000'
                    and p.get('audio.format') == 'S16LE', 'physical adapter format/identity mismatch')
    require(all(clocks) and len(set(clocks)) == len(clocks),
            'missing/shared physical clock')
    for sink, output, target, pair in expected_routes:
        require(len(named(sink)) == len(named(output)) == 1, 'missing/duplicate room node')
        ident, p = named(output)[0]
        require(p.get('target.object') == target and p.get('node.dont-fallback') in [True, 'true']
                and p.get('node.dont-move') in [True, 'true'], 'room target policy mismatch')
        outgoing = [x for x in links if x.get('output-node-id') == ident]
        require(all(nodes.get(x.get('input-node-id'), {}).get('node.name') == target for x in outgoing),
                'wrong physical room target')
        mapped = sorted(ports.get(x.get('input-port-id'), {}).get('audio.channel', '') for x in outgoing)
        require(mapped == (sorted(pair) if target in physical else []), 'incorrect physical stereo pair')


def still_enabled():
    require(not DISABLED.exists(), 'recovery is disabled for maintenance')


def stable_inventory(c, timeout=15):
    deadline = time.monotonic() + timeout
    previous = None
    count = 0
    while time.monotonic() < deadline:
        try:
            now = inventory(c)
        except (FileNotFoundError, RuntimeError):
            previous = None; count = 0
        else:
            count = count + 1 if now == previous else 1
            previous = now
            if count >= 4:
                return now
        time.sleep(0.5)
    raise RuntimeError('USB/card identity did not become ready and stable')


def clear_events():
    for p in (RUNTIME / 'events').iterdir():
        secure(p)
        require(re.fullmatch(r'\d+-\d+', p.name) is not None, 'unknown recovery event file')
        p.unlink()


def recover(c, boot=False, force=False):
    still_enabled()
    conf = wait_config(c)
    current = parse_grants(conf)
    running = run(['pct', 'status', str(c['ctid'])]).strip() == 'status: running'
    if not boot and not running:
        return {'outcome': 'CT stopped; left stopped'}
    observed = stable_inventory(c)
    previous = read('observed.json', None)
    if not boot and not force and previous == observed:
        return {'outcome': 'unchanged USB generation; no restart'}
    if not boot and not force:
        attempts = [t for t in read('attempts.json', []) if time.time() - t < 60]
        require(len(attempts) < 6, 'USB event cooldown: inspect flapping hardware; recover manually after review')
        attempts.append(time.time()); save('attempts.json', attempts)
    desired = desired_grants(c, observed, current)
    if boot and running:
        return {'outcome': 'boot preparation skipped; CT already running'}
    if not boot:
        states = service_states(c)
        target_active = states.get('sendspin-zones.target', {}).get('ActiveState') == 'active'
        audio_active = all(states.get(x + '.service', {}).get('ActiveState') == 'active'
                           for x in ['pipewire', 'wireplumber'])
        require(target_active and audio_active, 'audio/target deliberately stopped or unhealthy; not starting it')
        participating = active_rooms(states)
        expected_routes = routes(ct(c, 'cat', c['routing_file']))
        require(len(expected_routes) == len(target_rooms(c)), 'target rooms/routing count mismatch')
    for ident in observed:
        if boot or force or previous is None or previous.get(ident) != observed[ident]:
            restore_calibration(ident)
    require(inventory(c) == observed, 'hardware changed during calibration')
    if boot:
        apply_grants(c, conf, desired)
        save('observed.json', observed)
        return {'outcome': 'boot grants prepared; ordinary Proxmox onboot owns startup', 'present': sorted(observed)}
    # Keep stale numeric grants during a temporary absence, so same-number return needs no CT restart.
    present_paths = {p for value in observed.values() for p in value['paths']}
    covered = present_paths <= set(current.values())
    action = 'physical adapter refresh'
    if not covered:
        # Replacing an existing devN needs the supported stopped-CT lifecycle.
        require(participating == target_rooms(c), 'CT restart deferred: a configured room is intentionally stopped')
        wait_idle(c, participating, observed)
        still_enabled(); require(config(c) == conf, 'CT configuration changed during recovery')
        require(inventory(c) == observed, 'hardware changed before CT shutdown')
        run(['pct', 'shutdown', str(c['ctid']), '--timeout', '30'], timeout=40)
        require(run(['pct', 'status', str(c['ctid'])]).strip() == 'status: stopped', 'CT did not stop gracefully')
        still_enabled(); require(config(c) == conf, 'CT configuration changed after shutdown')
        require(inventory(c) == observed, 'hardware changed after CT shutdown')
        apply_grants(c, conf, desired)
        still_enabled()
        require(inventory(c) == observed, 'hardware changed before CT startup')
        run(['pct', 'start', str(c['ctid'])], timeout=45)
        action = 'CT restart with refreshed narrow grants'
    else:
        still_enabled(); require(config(c) == conf, 'CT configuration changed before adapter refresh')
        refresh_physical(c, observed, previous, force=force)
    deadline = time.monotonic() + 30
    last = None
    while time.monotonic() < deadline:
        still_enabled()
        require(inventory(c) == observed, 'hardware changed while audio returned')
        try:
            after = service_states(c)
            require(active_rooms(after) == participating and all(after[x].get('ActiveState') == 'active'
                    and after[x].get('SubState') == 'running' for x in participating),
                    'participating rooms have not converged')
            if covered:
                require(all(after[x].get('MainPID') == states[x].get('MainPID')
                            for x in participating | {'pipewire.service', 'wireplumber.service'}),
                        'audio daemon/player process changed during adapter refresh')
            verify_graph(c, observed, expected_routes)
            for ident in observed:
                verify_calibration(ident, calibration(Path('/var/lib/alsa/asound.state').read_text(), ident))
            break
        except RuntimeError as exc:
            last = exc; time.sleep(1)
    else:
        raise RuntimeError('audio did not converge: ' + str(last))
    save('observed.json', observed)
    return {'outcome': 'recovered', 'action': action, 'present': sorted(observed),
            'active_rooms': len(participating), 'physical_routes_checked': len(expected_routes)}


def apply_grants(c, before, desired):
    still_enabled()
    require(config(c) == before, 'CT configuration changed before grant update')
    current = parse_grants(before)
    delete = sorted(set(current) - set(desired))
    args = ['pct', 'set', str(c['ctid'])]
    if delete:
        args += ['--delete', ','.join(delete)]
    for slot, path in sorted(desired.items()):
        if current.get(slot) != path:
            args += ['--' + slot, device_value(path)]
    if len(args) > 3:
        run(args)
    after = config(c)
    require(parse_grants(after) == desired, 'narrow grants did not apply')
    require({k: v for k, v in before.items() if not re.fullmatch(r'dev\d+', k)} ==
            {k: v for k, v in after.items() if not re.fullmatch(r'dev\d+', k)}, 'unrelated CT option changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['event', 'reconcile', 'recover', 'boot', 'check', 'rules'])
    args = parser.parse_args()
    require(sys.platform == 'linux' and os.geteuid() == 0, 'Proxmox root required')
    runtime()
    if args.mode == 'event':
        if not DISABLED.exists():
            p = RUNTIME / 'events' / (str(time.monotonic_ns()) + '-' + str(os.getpid()))
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        return
    c = load_config()
    if args.mode == 'rules':
        print(rules(c), end=''); return
    fd = os.open(RUNTIME / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.mode == 'check':
            print(json.dumps({'inventory': inventory(c), 'grants': parse_grants(config(c)), 'read_only': True})); return
        clear_events()
        if DISABLED.exists():
            print(json.dumps({'outcome': 'disabled; no action'})); return
        started = time.monotonic()
        try:
            result = recover(c, boot=args.mode == 'boot', force=args.mode == 'recover')
            result['seconds'] = round(time.monotonic() - started, 3)
            result['success'] = True
        except Exception as exc:
            result = {'success': False, 'error': str(exc), 'seconds': round(time.monotonic() - started, 3)}
            save('status.json', result)
            print(json.dumps(result), flush=True)
            raise
        save('status.json', result)
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('USB recovery failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
