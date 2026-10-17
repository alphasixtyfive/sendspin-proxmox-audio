<img src="assets/icon.svg" alt="A speaker connected to room outputs" width="88" height="88">

# Sendspin audio on Proxmox

Play music and announcements in separate rooms using official Sendspin players in a Proxmox container. Music Assistant controls playback, and PipeWire sends each room to the right soundcard outputs.

This setup runs seven rooms on two Cubilux CA7 USB interfaces. The cards use the host’s Linux audio driver directly. Home Assistant and Music Assistant stay in their existing VM.

```text
Music Assistant → Sendspin players → PipeWire → USB soundcards → amplifiers
```

Each player keeps its own paired identity. Music Assistant owns the room queues and listening levels. The host keeps fixed hardware calibration. The container starts at boot without a login and supervises the players through normal systemd services.

## Set it up

1. Read [device access and security](docs/SECURITY.md).
2. Follow [setup](docs/SETUP.md) for a dedicated Debian 13 container.
3. Adapt the [seven-room example](examples/two-ca7-seven-zones) to your cards and wiring.
4. Pair the players, check every output and run the [playback checks](docs/VALIDATION.md).
5. Back up the private player state and [host audio configuration](docs/HOST-AUDIO.md).

The installer uses the released [Sendspin CLI 0.4.0](https://github.com/Sendspin/sendspin-cpp-cli/releases/tag/v0.4.0), with core 0.9.5. [Exact pins](upstream-pins.json) and the [changelog](CHANGELOG.md) explain what’s included. Sendspin, PipeWire and QEMU have no source changes.

## Keeping it running

Players recover after unexpected exits. Audio-server recovery preserves running rooms; deliberate service stops stay effective. A missing or replugged USB card can still need checked device mappings and a coordinated restart. [Operations](docs/OPERATIONS.md) covers recovery, updates and rollback.

The [validation record](docs/VALIDATION.md) says what was actually tested, including the remaining hardware and long-term limits. [Migration](docs/MIGRATION.md) covers replacing an older setup.

Repository checks:

```sh
python3 scripts/check.py
sh -n scripts/install-official.sh
python3 -B -m unittest discover -s tests -v
```

Configuration is MIT licensed. Sendspin is Apache 2.0 licensed. See [provenance](docs/PROVENANCE.md).
