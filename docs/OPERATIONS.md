# Upgrade, backup and restore

## Supervision and normal operation

Run user-manager/control commands as `sendspin-cli` with its real `XDG_RUNTIME_DIR` and user bus, as in [setup](SETUP.md). Each instance has its own `/etc/sendspin-zones/ZONE.conf`, `%S/sendspin-zones/ZONE` identity/state, and `%t/sendspin-zones/ZONE/control.sock`. For this account, `%S` is normally `/var/lib/sendspin-cli/.local/state` and `%t` is `/run/user/UID`.

`systemctl --user stop sendspin-zones.target` intentionally stops its member players; restart recreates them with the same persistent identities. An unexpected player exit, including a clean exit after an external SIGTERM, is retried after 5 seconds. `systemctl stop` still means stop. The template does not restart PipeWire, inspect queues or replay media. Ordinary media stop differs from process stop: stock CLI clears its ring but may leave the audio callback/device active. No extra keepalive is configured.

Stock CLI recovery has a finite reopen/rescan budget. A running process can exhaust it and discard until a new stream configures, so a restart policy alone cannot repair every silent endpoint. The graph and kernel also have separate device-recovery responsibilities. Keep the actual outage/replug validation record; do not add a watchdog to make a failed test appear successful. [Stock recovery](https://github.com/Sendspin/sendspin-cpp-cli/blob/45ff8b00e72ad1572a39e6e8ce21891748ab7d9e/src/sink_recovery.cpp#L62), [native clear/stop](https://github.com/Sendspin/sendspin-cpp-cli/blob/45ff8b00e72ad1572a39e6e8ce21891748ab7d9e/src/pipewire_sink.cpp#L447).

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

The installer checks the archive, binary checksum and staged executable before its atomic rename into `/usr/local/bin/sendspin-cli`. Failure or a handled interruption before that rename leaves the previous binary intact, or leaves the destination absent on a fresh install. Package installation and the system-unit mask are separate operations; this is not a transaction over the whole CT. After the rename, a build-information or daemon-reload failure can return an error while the complete verified new binary remains installed. The installer reports that boundary. Keep players stopped, inspect the installed checksum/build information and resolve the failed step before starting them or deliberately restoring the previous binary. It does not automatically roll back packages, masks or private state.

Install ordinary Debian security updates and record actual versions. Recheck routing/fail-closed behavior after PipeWire/WirePlumber upgrades. Their packaged unit files remain unchanged; user drop-ins set RestartMode=direct for automatic daemon recovery. This repository supplies normal configuration. A distribution/kernel update and a player update are separate changes with separate rollback boundaries.

## Replug and restart limits

The optional [host USB recovery component](USB-RECOVERY.md) automates the usual return path through standard PipeWire adapter creation, keeping existing room connections alive. It can prepare missing-card startup and perform an idle-gated CT/grant refresh when numbers genuinely change. It is configured and enabled separately. The following describes the base setup and deliberate manual recovery when that component is absent, disabled or reports a failure.

The two physical adapters are configured directly at PipeWire startup. Their `nofail` flag permits the server to start when a card is missing or cannot open; it does not schedule another creation attempt. After making the correctly identified hardware available, perform an ordinary `systemctl --user restart pipewire.service wireplumber.service`, then verify the exact physical nodes and links. The room units follow these explicit daemon restarts through `PartOf`. Preserve state directories and pairing. Coordinate the restart because it interrupts every zone in that shared graph.

An ordinary ALSA XRUN/suspend recovery on an existing handle differs from USB removal/rediscovery. Neither stock Sendspin's finite retries nor static adapter configuration establishes automatic recovery from every USB fault. If re-enumeration changes device minors, stop the CT, update its supported `devN` assignments after checking physical identity/exclusive ownership, and start it normally. A stable card ID selects the intended hardware; it does not update Proxmox node permissions. Test same-minor return, changed-minor return and absent-at-start separately. No script broadens permissions, changes other USB assignments, replays queues or installs a host watcher.


## Audio-server maintenance

Automatic PipeWire/WirePlumber failure recovery uses `RestartMode=direct` so a temporary failure does not stop the dependent room services. Stock daemon `Restart=on-failure` is retained. This differs from an explicit stop or restart. See [systemd 257 service semantics](https://github.com/systemd/systemd/blob/v257/man/systemd.service.xml) and its [restart-dependency implementation](https://github.com/systemd/systemd/blob/v257/src/core/service.c). A daemon that exits cleanly without an automatic restart may still need the manual recovery below.

An explicit restart of PipeWire or WirePlumber restarts the participating room services in order, using their existing private identities. `Type=exec` reports an executable launch failure immediately; it does not mean a player is paired or ready to play.

Stopping a daemon and starting it later is different from restarting it. After a separate stop/start, start the room target again:

```sh
systemctl --user start pipewire.service wireplumber.service
systemctl --user restart sendspin-zones.target
```

This explicitly restores the configured group. If you intentionally stopped an individual room for maintenance, check its state before bringing the group back. A process can be alive while its device recovery has failed; inspect the actual room route and playback rather than relying only on `active`.

To roll back the v0.1.1 service policy, stop the zone target, restore its previous template from the matching backup, run `daemon-reload`, then start the target. The player binary and paired state are unchanged by this setup release. Restore any retired system files only for a deliberate return to the upstream single-player deployment.

To remove the v0.1.2 automatic-daemon policy, stop the zone target, remove only the two documented `50-direct-restart.conf` files from the account’s audio-service drop-in directories, run `daemon-reload`, then start the ordinary stack and target. This reintroduces the demonstrated transient-crash stop behavior; keep the matching backup and test the intended replacement policy.
