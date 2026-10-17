# Sendspin audio on Proxmox

Run one official Sendspin player per room in an unprivileged Proxmox container. Music Assistant controls the rooms; PipeWire sends each stereo pair to the right soundcard outputs.

This is the setup used for seven rooms on two Cubilux CA7 interfaces. The players use the host's USB audio driver directly, so audio stays outside the Home Assistant VM. Home Assistant and Music Assistant can remain where they are.

```text
Music Assistant → Sendspin players → PipeWire → USB soundcards → amplifiers
```

The repository contains configuration and an installer for the released Sendspin CLI. It does not modify Sendspin, PipeWire or QEMU. Each room has its own paired identity and listening level. The host owns fixed hardware calibration; Music Assistant owns queues, volume and announcements.

## Getting started

1. Read [device access and security](docs/SECURITY.md).
2. Follow [setup](docs/SETUP.md) for a dedicated Debian 13 container.
3. Adapt the [seven-room example](examples/two-ca7-seven-zones) to your wiring. Set your own soundcard IDs and server address.
4. Enable startup, pair the players and run the [playback checks](docs/VALIDATION.md).
5. Keep the private player state and [host audio configuration](docs/HOST-AUDIO.md) backed up.

The example has no preset amplifier gain or household credentials. Check each physical output at a safe level, especially if using a center/subwoofer socket as a stereo pair. See [migration](docs/MIGRATION.md) when replacing older players.

## Startup and recovery

Proxmox must have **Start at boot** enabled for the CT. Inside it, a lingering systemd user manager starts PipeWire, WirePlumber and the enabled room players without an interactive login. The room services restart after an unexpected exit and follow audio-server restarts. A deliberate service stop stays stopped.

The installer verifies the official archive and binary, installs just the binary and build information, and masks the unused single-player system service. It refuses to replace a running player. Nothing starts music automatically or replays a queue.

USB recovery still depends on the hardware and its device mappings. If a card is absent at startup, make it available and restart the audio services. A USB replug that changes device nodes may need updated CT grants and a CT restart. The setup does not guess a replacement card or expose every sound device. [Operations](docs/OPERATIONS.md) has the recovery commands and remaining limits.

The [validation record](docs/VALIDATION.md) separates actual playback and recovery tests from things still untested. A physical host reboot and full backup restoration need their own planned checks.

## Versions and checks

The player is [Sendspin CLI 0.4.0](https://github.com/Sendspin/sendspin-cpp-cli/releases/tag/v0.4.0), with core 0.9.5. [Exact pins and checksums](upstream-pins.json) are kept with the configuration. See the [changelog](CHANGELOG.md) for setup releases.

```sh
python3 scripts/check.py
sh -n scripts/install-official.sh
python3 -B -m unittest discover -s tests -v
```

The tests exercise installation in a temporary filesystem without changing services or using the network. They do not replace physical playback tests.

Configuration is MIT licensed. Sendspin is Apache 2.0 licensed; the audio packages retain their own licenses. See [provenance](docs/PROVENANCE.md).
