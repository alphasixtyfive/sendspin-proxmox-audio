# Changelog

## 0.1.7 — 18 October 2026

- Fix generated routing syntax so the existing USB recovery reader can inspect it; add a cross-component regression test. Regenerate uninstalled v0.1.6 stages before use.
- Add read-only stage verification against the current configuration, complete file inventory and manifest; reject stale, partial, modified or symlinked stages.
- Keep Unicode labels as UTF-8, remove obsolete separate player/adapter/target templates, and use one setup path through the TOML renderer.

Installed player binaries, native audio configuration and host recovery code are unchanged.

## 0.1.6 — 18 October 2026

- Describe devices, room sockets and optional existing host recovery in one private TOML.
- Validate identities, allocations, ports and the supported hardware profile, then stage native configuration and a checksum manifest for review.
- Keep player identities and native recovery policy unchanged. Rendering adds no service and never applies changes or starts playback.

## 0.1.5 — 17 October 2026

- Add one fast rollout path for restoring a verified installation or building a new container.
- Clarify the optional missing-card boot preparation in the base setup guide.

Documentation only; installed audio and recovery code are unchanged from 0.1.4.

## 0.1.4 — 17 October 2026

- Add optional host USB recovery using udev events, a systemd path unit and supported Proxmox/PipeWire commands.
- Recreate only the affected physical output, keeping virtual rooms and player connections alive. Read adapter definitions and calibration from their existing owners.
- Prepare available device grants before host autostart, and wait for idle streams before a required CT mapping refresh.
- Respect maintenance stops and pending configuration, wait out short backup locks, and bound event retries.
- Add recovery decision, failure and routing tests, with explicit installation and rollback instructions.

The official player, audio packages and room-service policy are unchanged. This component runs on the Proxmox host and is not installed by the player installer.

## 0.1.3 — 17 October 2026

- Add an optional isolated PipeWire routing/recovery test, including missing targets, default changes and virtual soundcard removal/return.
- Read expected channel assignments from the routing file instead of duplicating a map in the test.
- Document checks for USB return, daemon/server/CT restart, host boot and backup restoration, with automatic and manual recovery boundaries.
- Check Python syntax alongside the existing repository checks, and document bounded per-player readiness after boot.

Production configuration and the official audio binaries are unchanged from v0.1.2.

## 0.1.2 — 17 October 2026

- Reject a wrongly owned, inaccessible or symlinked player home before changing packages.
- Refuse directory or symlink executable destinations and use an exact-destination atomic rename.
- Run the verified candidate before replacing a working executable. Report failures after replacement without implying that package or service changes were rolled back.
- Keep dependent players running through automatic PipeWire/WirePlumber failure recovery using standard systemd user drop-ins. Explicit stops and restarts retain their behavior.
- Add fresh-install, interruption and failure-boundary tests.

The official player and the installed v0.1.1 room-service policy are unchanged.

## 0.1.1 — 17 October 2026

- Fixed extra shell escapes that broke the fresh-install checksum and download commands.
- Install only the verified player binary and build information. Check the audio account and refuse active or enabled single-player services before changing packages.
- Verify the staged binary before replacing the installed one, then use a same-directory rename. Keep the existing binary intact when download, archive or binary checks fail.
- Mask the unused single-player system service so it cannot compete with the room players after a reboot.
- Restart room players with PipeWire/WirePlumber, recover unexpected clean exits, and report executable launch failures immediately.
- Document Proxmox boot enablement, user linger and the difference between an audio-server restart and a separate stop/start.
- Add isolated Linux installer tests and continuous checks for the public configuration.

Sendspin remains the unmodified official CLI 0.4.0/core 0.9.5. This release changes deployment and service policy, not audio rendering.

## 0.1.0 — 17 October 2026

Initial two-card, seven-room deployment using official Sendspin players, stock PipeWire and host-native USB in an unprivileged Proxmox CT.
