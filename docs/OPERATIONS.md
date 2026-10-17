# Upgrade, backup and restore

## Supervision and normal operation

Run user-manager/control commands as `sendspin-cli` with its real `XDG_RUNTIME_DIR` and user bus, as in [setup](SETUP.md). Each instance has its own `/etc/sendspin-zones/ZONE.conf`, `%S/sendspin-zones/ZONE` identity/state, and `%t/sendspin-zones/ZONE/control.sock`. For this account, `%S` is normally `/var/lib/sendspin-cli/.local/state` and `%t` is `/run/user/UID`.

`systemctl --user stop sendspin-zones.target` intentionally stops its member players; restart recreates them with the same persistent identities. A player process failure is retried after 5 seconds. An intentional stop is respected. The template does not restart PipeWire, inspect queues or replay media. Ordinary media stop differs from process stop: stock CLI clears its ring but may leave the audio callback/device active. No extra keepalive is configured.

Stock CLI recovery has a finite reopen/rescan budget. A running process can exhaust it and discard until a new stream configures, so `Restart=on-failure` is not a cure for every silent endpoint. The graph and kernel also have separate device-recovery responsibilities. Keep the actual outage/replug validation record; do not add a watchdog to make a failed test appear successful. [Stock recovery](https://github.com/Sendspin/sendspin-cpp-cli/blob/45ff8b00e72ad1572a39e6e8ce21891748ab7d9e/src/sink_recovery.cpp#L62), [native clear/stop](https://github.com/Sendspin/sendspin-cpp-cli/blob/45ff8b00e72ad1572a39e6e8ce21891748ab7d9e/src/pipewire_sink.cpp#L447).

The reference installation passed a real MA-server outage/restart with all seven existing player processes left running: they reconnected without configuration repair or player restart. Its normal music-announcement-resume flow also preserved the queue context and restored listening volume. These bounded results do not extend the separate USB/static-adapter recovery limits below.

## Private backup

Before upgrades or migration, stop the players and take an access-controlled CT backup/snapshot through normal Proxmox facilities. Also retain:

- `/var/lib/sendspin-cli/.local/state/sendspin-zones/`: identity keypairs, pairing records, remembered player levels/mute/delay. Losing a key makes a new endpoint.
- Completed `/etc/sendspin-zones`, `/etc/pipewire`, `/etc/wireplumber` configuration and the account's user service files.
- Installed binary checksum/version, distribution package versions, CT device mappings and the observed stable physical-port mapping.
- The separately owned host ALSA calibration/state and standard restore configuration, if used. Preserve unrelated card settings.
- Your MA player-ID mapping, groups and affected HA scripts/entities through their existing backup owners.

State/tokens are secrets. Store backups outside the public repository with restrictive permissions; `.gitignore` is only a convenience, not access control. Do not include them in support bundles or release assets.

Restore state to the same corresponding zone while all copies of that identity are stopped. Set account ownership/private permissions before start. Restore local routing/device access and verify exact outputs before audio. Never run two endpoints with the same copied key or share one room's state directory with another. A changed numeric UID does not change the identity key; runtime paths must use the account's actual current UID.

## Upgrades and rollback

Use reviewed release versions and hashes, not an automatic `latest` downloader. The supplied installer is intentionally pinned to 0.4.0. A future update must resolve the official release/source pins and archive checksum, read protocol/state compatibility notes, check runtime ABI/backends, and update the recorded provenance. Install no local source patch to bypass an upstream failure.

Retain the previous verified binary and **matching pre-upgrade private state/config backup**. Stop the user target, install the reviewed binary, restart one pilot and prove pairing/identity retention, routing and normal TTS/music before the whole target. A binary downgrade alone may be unsafe after a state/protocol migration; restore the matching backup. Do not erase working pairing state as a routine upgrade step.

Install ordinary Debian security updates and record actual versions. Recheck routing/fail-closed behavior after PipeWire/WirePlumber upgrades. Their packaged services remain unchanged; this repository supplies only normal configuration. A distribution/kernel update and a player update are separate changes with separate rollback boundaries.

## Replug and restart limits

The two physical adapters are configured directly at PipeWire startup. Their `nofail` flag permits the server to start when a card is missing or cannot open; it does not schedule another creation attempt. After making the correctly identified hardware available, perform an ordinary `systemctl --user restart pipewire.service wireplumber.service`, then verify the exact physical nodes/links and restart affected player instances if needed. Preserve state directories and pairing. Coordinate the restart because it interrupts every zone in that shared graph.

An ordinary ALSA XRUN/suspend recovery on an existing handle differs from USB removal/rediscovery. Neither stock Sendspin's finite retries nor static adapter configuration establishes automatic recovery from every USB fault. If re-enumeration changes device minors, stop the CT, update its supported `devN` assignments after checking physical identity/exclusive ownership, and start it normally. A stable card ID selects the intended hardware; it does not update Proxmox node permissions. Test same-minor return, changed-minor return and absent-at-start separately. No script broadens permissions, changes other USB assignments, replays queues or installs a host watcher.
