# Changelog

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
