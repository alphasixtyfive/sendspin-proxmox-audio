# Sendspin audio on Proxmox

Deployment configuration for **released, unmodified Sendspin CLI** and distribution **PipeWire/WirePlumber** in a dedicated, unprivileged Linux container. Music Assistant remains the music server and controller. This repository contains no audio renderer fork, source patches, custom daemon or Home Assistant app.

**Status: deployment configuration tested on one two-card, seven-zone installation.** Native eight-channel/48kHz playback, all seven active routes, cold/warm announcement listening, music interruption/resume, MA outage/reconnection, CT restart and isolated USB-audio driver reload with calibration preserved have passed. Physical host boot, arbitrary USB replug, full restore and every negative routing scenario remain unproven. Results apply to the recorded configuration and hardware; read the [acceptance record](docs/VALIDATION.md) before adapting it.

```text
Music Assistant → stock Sendspin players → stock PipeWire stereo routes
                                              ↓
                                  host ALSA / USB soundcards → amplifier
```

The CT shares Proxmox's kernel and uses host-owned sound devices directly. It avoids passing USB through a QEMU virtual controller and does not use PulseAudio output. One persistent Sendspin identity and supervised process represent each stereo zone.

The supplied example splits two Cubilux CA7 7.1 interfaces into seven independent stereo zones. Two stock PipeWire ALSA adapters open explicitly named hardware; WirePlumber's automatic ALSA monitor is disabled. This preserves narrow Proxmox device grants without relying on automatic card enumeration or exposing the host udev database. It uses generic names, explicit server/card-ID placeholders and **no preset gain or pairing credentials**. Other devices need their own channel/format validation. Center/LFE can be used as a full-range stereo pair only after checking routing and hardware behavior.

1. Read [security and device access](docs/SECURITY.md).
2. Follow [setup](docs/SETUP.md), filling a private local configuration.
3. Complete the [acceptance checks](docs/VALIDATION.md) before migration.
4. Keep identities backed up and follow [upgrade/restore](docs/OPERATIONS.md).

The [host audio guide](docs/HOST-AUDIO.md) explains persistent physical IDs, optional standard index allocation and calibration ownership without copying private port mappings or gains.

[Legacy-app migration](docs/MIGRATION.md) describes replacing older local players without reusing their IDs incorrectly. This deployment is a new setup, not a continuation of a patched app release.

The reviewed player is [Sendspin CLI v0.4.0](https://github.com/Sendspin/sendspin-cpp-cli/releases/tag/v0.4.0), with core v0.9.5; exact revisions and checksums are in [upstream-pins.json](upstream-pins.json). The installer verifies the official amd64 archive and binary and starts nothing. The example services retain normal player defaults and explicitly named native PipeWire outputs. Pairing is required. No watchdog, queue replay, keepalive helper or automatic device rebinding is added.

Stock limitations remain visible: finite device recovery attempts, an output stream that may remain active after playback, specific CT device-node mappings and new encrypted player identities. A missing physical adapter at startup needs an ordinary PipeWire restart after hardware becomes available; static configuration adds no rediscovery watcher. Read the setup/operations guidance before relying on unattended recovery.

Configuration in this repository is MIT licensed. Upstream Sendspin is Apache 2.0 licensed and downloaded from its own release; PipeWire/WirePlumber/ALSA keep their respective licenses. See [provenance](docs/PROVENANCE.md).

Repository checks: `python3 scripts/check.py` and `sh -n scripts/install-official.sh`. They check the deployment inventory and shell syntax without network, hardware, installation or playback. They do not replace the physical acceptance record.
