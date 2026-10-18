# Fast rollout

Use the protected private CT backup for the quickest recovery of an existing installation. Use the clean-build path for a new machine. The public repository contains no paired identities, listening levels, hardware calibration or household map.

## Restore an existing installation

1. Stop the original CT before starting any restored copy of its paired players. Verify the CT archive and matching host-companion checksums from your private runbook.
2. Restore the CT with normal Proxmox backup/restore tooling, initially stopped. Review its network, volume references, unprivileged mode and current UID/GID.
3. Restore the reviewed host card-ID rule, module options and complete saved ALSA state. Identify the actual physical ports and control/PCM0 nodes; old numeric card indices are observations, not identities. Keep exactly the selected playback/control grants.
4. Restore/install the reviewed host recovery executable, private map, event rule and three units using [USB recovery](USB-RECOVERY.md#install-deliberately). Keep its maintenance marker present while staging. The companion manifest records each owned file's mode, owner and hash.
5. With the CT stopped and the map verified, remove the maintenance marker and run the following on the host. Substitute the restored ID:

```sh
/usr/local/libexec/sendspin-usb-recovery check
/usr/local/libexec/sendspin-usb-recovery boot
pct start CTID
systemctl enable --now sendspin-usb-recovery.path
systemctl enable sendspin-usb-prepare.service
```

6. Verify every configured room, paired identity, exact channel links, fixed gains and normal announcement-volume restoration before handing over. A restored clone must never run alongside the original identity.

## Build a new installation

```sh
git clone --branch v0.1.7 --depth 1 \
  https://github.com/alphasixtyfive/sendspin-proxmox-audio.git
cd sendspin-proxmox-audio
python3 scripts/check.py
```

Follow these steps in order; commands and configuration destinations live in the linked guide once:

| Step | Action | Guide |
| --- | --- | --- |
| 1 | Create a dedicated unprivileged Debian 13 amd64 CT; inspect native hardware ownership and narrow grants. | [Security](SECURITY.md), [host audio](HOST-AUDIO.md) |
| 2 | Install stock packages, the persistent audio account and verified official CLI. Disable CT ALSA restoration before granting control nodes. | [Setup 1](SETUP.md#1-base-and-account) |
| 3 | Edit one private TOML for devices/rooms, render and review its native files, then install with explicit ownership. | [Configuration](CONFIGURATION.md), [setup 2](SETUP.md#2-make-explicit-local-configuration) |
| 4 | Start the stock audio session and one pilot player; pair through MA, then enable the accepted room target and CT onboot. | [Setup 3–5](SETUP.md#3-start-native-services-then-one-player) |
| 5 | Add the optional, reviewed host USB recovery with a private map and retain one matching recovery set. | [USB recovery](USB-RECOVERY.md) |

New keys create new endpoints. Transfer existing private identities only deliberately; otherwise pair new players and update HA/MA mappings through their existing owners. Never replay a completed household migration script.

## Handover and rollback

- Confirm the official binary checksum, one user session, separate private room states, distinct physical clocks and no competing hardware owner.
- Check each configured player, not only the group target. Retry may take several seconds during startup. Verify actual streams reach their own stereo pair with no fallback.
- Test music, cold/warm announcements, music resume and volume/mute restoration. Compare existing HA/MA registrations and queues. Exercise CT restart, daemon failure and selected USB return separately; record acoustic and physical-test limits honestly.
- Leave CT onboot, user linger and accepted targets enabled. Keep the protected CT backup and matching host manifest private. See [validation](VALIDATION.md) for the tested scope.
- Before maintenance: create `/etc/sendspin-usb-recovery.disabled`, stop/drain the recovery path/service, then stop the affected owners. Restore matching state/configuration for rollback; review actual device numbers before starting. [Operations](OPERATIONS.md), [USB removal](USB-RECOVERY.md#validate-and-remove).

The reference uses unchanged CLI 0.4.0/core 0.9.5, PipeWire 1.4.2 and WirePlumber 0.5.8 on Debian 13. [Exact pins](../upstream-pins.json) own versions/checksums. No QEMU, PulseAudio or renderer patch is required by this native CT audio path.
