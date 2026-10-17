# Host card identities, indices and calibration

The host's standard USB-audio driver owns the interfaces. The CT receives only the selected control and PCM0 playback nodes. Keep fixed mixer calibration and persistent card IDs in the existing host udev/ALSA owner; keep listening volume/mute in MA. Back up these host files separately from the CT rootfs/private player state.

Two interfaces with identical serials require physical-port identity rules. Observe the actual host USB port/ID_PATH and assign distinct ALSA IDs using standard host configuration. Put those IDs into the private adapter template; never assume numeric card 3 is permanently the first physical interface. The public example intentionally contains no port paths or household IDs.

Where stable numeric allocation is useful for Proxmox devN grants, normal module parameters can reserve an index **pair**. The tested topology had three existing onboard ALSA cards occupying 0–2 and exactly two CA7 interfaces with USB VID/PID `0bda:4f25`. This standard option was verified through a controlled leaf-driver reload:

```conf
# Example only: first verify your existing cards, available indices and options.
options snd_usb_audio index=3,4 vid=0x0bda,0x0bda pid=0x4f25,0x4f25
```

Use an ordinary `/etc/modprobe.d/` configuration owned by the administrator. Inspect `modprobe -c`, actual module parameters and existing driver users before changing it; do not append conflicting duplicate options. These values are not an installer default for arbitrary systems. More onboard/USB audio hardware or occupied indices requires a different reviewed allocation. Do not change core cards_limit merely because its default is 1; it controls autoload aliases, not the number of already usable cards.

The [Linux 7.0 USB driver](https://github.com/torvalds/linux/blob/v7.0/sound/usb/card.c) selects the first unused matching VID/PID parameter slot and uses that slot's index. Identical devices can probe in either order. Do not use the driver's id array to pretend that the first match is a particular physical room/card. Per-port ALSA IDs select routing/calibration; inspect the actual role-to-control/PCM mapping and regenerate only the corresponding Proxmox grants while the CT is stopped. [Kernel ALSA parameters](https://docs.kernel.org/sound/alsa-configuration.html).

A controlled reload is a maintenance action, not normal playback operation: quiesce/mask the players, close all selected PCM/control owners, stop the CT gracefully, and establish that snd_usb_audio owns only the intended devices. Reload only that leaf module without force or dependency pruning; preserve unrelated HDA cards, USB controllers, serial/Zigbee consumers and all mixer state. If removal is refused, stop and inspect the owner. Do not unload usbcore, xHCI, serial or unrelated audio drivers. Recheck per-port IDs, full mixer contents, unrelated devices, grants and the native graph before restarting content. This repository installs no reload/watchdog daemon.

Check the distribution's normal initramfs/module-loading path. If a selected boot image embeds this module or stale options, use its supported update tools after review; a root-filesystem option file alone does not establish early-boot behavior. The reference deployment passed CT restart and a controlled leaf-driver reload with calibration preserved. Physical host boot and arbitrary USB return remain separate unproven tests.

Preserve the complete saved ALSA state, including unused headphone/capture controls. Verify the installed distribution restore rule and its selected-card behavior before relying on it; see [Debian restore-rule caveat](SECURITY.md). Test only the selected card and compare unrelated live controls too. The public configuration supplies no gain values or custom restoration service.
