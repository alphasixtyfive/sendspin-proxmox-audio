# Changelog

## 0.1.9 — 22 November 2026

- Start the USB event watcher during boot and keep recovery ordered after guest startup. This removes a systemd ordering cycle that could leave the watcher inactive after reboot.
- Document optional amplifier shutdown before Proxmox stops guests, and show how to measure shutdown and room recovery separately.

## 0.1.8 — 20 November 2026

- Add Sendspin Settings for editing, adding and removing zones. Saving prepares
  and verifies the installation files. The editor listens on loopback by default.
- Reject malformed recovery maps and ambiguous paired stream status before
  changing hardware. Keep calibration selection explicit at the restore boundary,
  and separate generated hook text from staged files without changing native output.
- Separate fixed host calibration from ALSA runtime autosave through an explicit
  `host.calibration_file`, required for idle gain. Exports identify that source;
  rendering rejects a runtime snapshot in its place. Retain the fixed source
  when disabling policy. Normal ALSA services and unrelated cards are untouched.
- Let asynchronous stream hooks wait for the shared card lock, avoiding lost
  transitions under contention. Keep native unit pre/post waits bounded and
  cover a lock held longer than the former two-second limit.

- Add shared `[idle_gain]` over an explicit room set, or optional per-room
  `idle_gain`, to the existing topology renderer. Generate
  stock stream hooks and native unit drop-ins from a host calibration export;
  retain normal listening-volume ownership and independent stereo calibration.
- Use `AUDIO_*` calibration variables outside the stock hook runner's reserved
  `SENDSPIN_*` namespace, and reject missing variables before a mixer write.
- Extend existing USB recovery to reconcile and verify stream-owned hardware
  gains under the same per-card lock, preserving deliberately stopped rooms.
  Defer managed speaker verification until that lock so a stream-end hook during
  calibration restore cannot cause a false normal-gain mismatch.
- Validate sparse writes, concurrent native hooks, lifecycle and forced physical
  adapter recovery on the reference setup without audible playback. Physical
  replug, reboot and acoustic acceptance beyond the Guest pilot remain separate
  gates. The official player binary and vendor source remain unchanged.

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
