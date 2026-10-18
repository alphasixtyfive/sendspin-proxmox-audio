# One configuration

Edit a private copy of [audio.toml](../examples/audio.toml). It describes the MA endpoint, named USB devices and each room's socket. Python 3.11+ reads TOML without extra packages. The renderer is a command in this repository; it adds no service, web app or player modification.

```sh
mkdir -p local
cp examples/audio.toml local/audio.toml
# Edit local/audio.toml with the actual endpoint, persistent ALSA IDs and wiring.
python3 scripts/configure.py check local/audio.toml
python3 scripts/configure.py render local/audio.toml --output local/staged-01
```

The output directory must not exist and its parent must exist. Rendering writes only that fresh directory. A failure or interruption may leave an incomplete stage: accept it only if the command succeeded and `manifest.json` contains all expected files and matching SHA256s. Review a new stage after each edit; a render never installs, starts, pairs, restarts or plays anything.

## Everyday edits

```toml
[devices.a]
profile = "ca7"
alsa_id = "CARD_A"

[zones]
study = { name = "Study", device = "a", output = "front", port = 8931 }
```

- Change `name` to rename the display. Keep the `study` key: it selects the service, sink and existing private player-state directory. For an adopted player with a different advertised name, optional `player_name` preserves it separately from the routing description.
- Change `device`/`output` to move that same player to another free socket. A card's `alsa_id` is its persistent host-assigned ID, not a numeric card index.
- Add a zone with a new stable key, free socket and unique port (1024–65535). Pair its new endpoint normally in MA; HA entities, labels and announcement membership remain under HA/MA control.
- Set `enabled = false` to omit a saved zone from generated routes, rules, player configs and target membership. Retain its private state for reuse. At least one zone must remain enabled. Disabled definitions must still be valid, but do not reserve sockets/ports.

| `output` | CA7 socket | Channels |
| --- | --- | --- |
| `front` | FRONT | FL / FR |
| `surround` | SURR | RL / RR |
| `side` | SIDE-SURR | SL / SR |
| `center_sub` | CENTER / SUB | FC / LFE |

Only the reviewed CA7 eight-channel PCM0 S16LE/48kHz profile is supported. Its center/sub pair must carry full-range stereo for this wiring. Headphone PCM1, arbitrary DACs and other channel layouts need separate hardware validation. Up to four rooms share each CA7. Duplicate active sockets, ports, ALSA IDs, nodes or clocks are rejected; spelling mistakes and unknown settings fail validation.

## Optional host recovery

If using the existing [host recovery](USB-RECOVERY.md), add this to the same private TOML:

```toml
[host]
ctid = 123
user = "sendspin-cli"
uid = 999

[devices.a]
profile = "ca7"
alsa_id = "CARD_A"
usb_port = "1-2.3"
slots = ["dev0", "dev1"]

[devices.b]
profile = "ca7"
alsa_id = "CARD_B"
usb_port = "1-2.4"
slots = ["dev2", "dev3"]
```

Merge these tables into the existing configuration; TOML rejects duplicate table definitions. Observe the real USB paths, account UID and narrow Proxmox grant slots. Host recovery supports exactly two CA7s/four distinct slots. VID/PID `0bda:4f25` comes from the reviewed profile. The renderer produces its existing JSON map; it does not create host identities, grants, udev rules, recovery units or calibration. Follow their existing [installation and maintenance procedure](USB-RECOVERY.md#install-deliberately) when adopting the map. Moving a USB plug or replacing a card also needs the host-owned identity rule reviewed; changing a label alone cannot assign hardware.

## Review and install native files

| Staged tree | Destination |
| --- | --- |
| `ct/etc/` | CT `/etc/`, using the same relative paths |
| `ct/user/` | Audio user's `$HOME/.config/systemd/user/` |
| `host/etc/sendspin-usb-recovery.json` | Optional host `/etc/sendspin-usb-recovery.json`, root 0600 |
| `manifest.json` | Private review evidence; do not install as audio configuration |

These are the same native files described in [setup](SETUP.md#2-make-explicit-local-configuration). Keep `/etc/sendspin-zones` root:audio-group 0750, player configs root:audio-group 0640, user units/drop-ins audio-user owned (directories 0700/files 0644), and PipeWire/WirePlumber config root-owned 0644. Use the actual audio account's group. There is no live apply command: installation is an explicit maintenance operation, with the [recovery marker and path/service drained first](OPERATIONS.md).

Before installation, compare the manifest and native contents with the live files, inspect externally edited settings, and retain the existing matching recovery set. Install only the reviewed paths. **Do not overlay a whole stage blindly:** when disabling/removing a zone, stop and disable its instance; remove its obsolete generated config and any obsolete generated graph/rule file. Keep paired state. Otherwise stale files or enabled instances can remain active. Never remove unrelated configuration. Resume through the existing [native service commands](SETUP.md#3-start-native-services-then-one-player), including user `daemon-reload` and the graph/player restarts needed to load changed files. A graph restart interrupts the shared audio session. Recheck routes, pairing, gains and HA/MA restoration before normal use. Roll back matching native files through the same maintenance procedure.

## Adopting an existing installation

Keep zone keys, native sink names, port numbers and private state paths unchanged. Optional layout overrides preserve existing filenames and sink prefixes:

```toml
[layout]
sink_prefix = "sendspin_"
routing_file = "60-zones.conf"
wireplumber_file = "51-manual-ca7.conf"
```

Devices optionally accept `node`, `clock` and `description` to preserve existing physical identities. Defaults are `ca7_card_<device-key>`, `api.alsa.ca7_<device-key>` and `CUBILUX CA7 card <KEY> eight-channel output`. Every physical clock must be distinct. Compare parsed native properties, not whitespace. A target's description is cosmetic; its dependencies and exact instance membership must match. Keep exactly one generated routing file, physical-adapter file and matching client rule.

The TOML is the topology source for future maintenance; the live daemons continue reading their installed native files until a reviewed stage is installed. Keep the private TOML with the recovery records. Pairing keys, fixed hardware gains, Proxmox storage/network settings and HA/MA policies remain with their existing owners and are deliberately outside this file. Never publish filled household configuration or pairing state.
