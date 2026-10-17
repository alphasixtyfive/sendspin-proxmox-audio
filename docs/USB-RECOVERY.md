# Optional automatic USB recovery

This host component recovers the existing two-card container when a known USB interface disappears or returns. It uses official audio packages and supported `pct`/systemd commands. It never starts content, re-pairs players, changes listening levels, stores new calibration or grants all sound devices. Review the private hardware map and test it before enabling it.

The existing Sendspin installer does not enable this optional component. It runs on the Proxmox host, where USB identity and container permissions are owned. It requires root, Python3, standard Proxmox tooling, host ALSA utilities and the reviewed Debian13/systemd257 audio CT configuration. The CT must provide `pw-config`, `spa-json-dump`, `pw-cli` and the official CLI0.4.0 status command. These utilities were already installed in the reference CT. Host group29 is the audio group in this baseline. Different distributions, routing syntax, user-unit layout or mixer-state syntax require review.

## What happens

The generated udev rule queues a short local event. A systemd path unit starts a bounded recovery operation outside the udev worker. Duplicate events for an unchanged USB/card generation do not restart audio. A file lock serializes changes; events arriving during an operation remain queued for the next pass. Six actual recovery attempts per minute are allowed; persistent flapping then stops with a journal error until another event after cooldown or an explicit reviewed recovery.

Card identity is checked by physical USB port, VID/PID and the existing per-port ALSA ID. USB device number and ALSA sysfs instance distinguish a real reconnect from a repeated change event. Identical cards can swap reserved indices while keeping the same complete device permission set.

For a temporary absence, existing grants are retained. The operation removes the affected physical adapter to release its old hardware handle. On return, it restores and verifies mixer values against the existing host `/var/lib/alsa/asound.state`, with ALSA's initialization fallback disabled, then recreates that adapter through `pw-cli`. Definitions come from the existing merged PipeWire configuration, converted with the vendor `spa-json-dump` utility. No second format/channel/clock template is maintained. `object.linger` keeps a newly created adapter after the control command exits.

Virtual room sinks, the healthy card, PipeWire/WirePlumber and participating Sendspin player processes stay in place. Recovery verifies their PIDs did not change and checks every configured stereo route. This avoids dropping healthy player connections and racing Music Assistant's temporary announcement-volume restoration. It cannot replace the audio physically missed while an interface was absent; it does not replay it.

If returned hardware needs genuinely different device numbers, the operation waits for two paired idle-stream observations, then gracefully shuts down the audio CT, replaces only its configured four control/PCM0 playback grants and starts the same CT. It never force-stops or force-unlocks a CT. A deliberately inactive room blocks this whole-CT fallback; resolve maintenance before retrying. An active stream or startup connection is allowed90seconds to settle. If that expires, pause playback and invoke recovery deliberately. Ordinary same-grant USB return does not wait for playback to end and does not restart players.

An intentionally stopped CT or audio target stays stopped. A maintenance-disable file is checked before each major action. An administrator must disable recovery **before** maintenance: a second stop command issued while the recovery operation itself has the CT stopped cannot reliably express a different intent. An initial Proxmox task lock is allowed30seconds to clear; unapplied pending changes are refused immediately. Configuration changes, a later task lock or changing hardware abort the operation. A failure after shutdown can leave the CT safely stopped for inspection. The idle check reduces overlap with playback; it does not provide a Music Assistant announcement lock against a new request arriving during maintenance.

At host boot, the preparation service runs before ordinary Proxmox guest startup. With the CT stopped, it includes only currently present, validated card nodes, so missing device paths need not prevent the audio CT starting. The existing Proxmox onboot policy owns startup; a return event never starts an administratively stopped CT. No hook calls pct set while holding Proxmox's own configuration lock. Validate absence-at-boot separately from ordinary restart.

## Install deliberately

First retain a protected CT backup and a separate host companion containing its CT configuration, card-ID/module rules and full saved ALSA state. Confirm all selected nodes, per-port IDs, current calibration, user UID, strict routes and room service behavior. This component supports exactly two configured cards and four exclusive devN slots; it refuses extra device grants, capture/headphone paths and unexpected permissions.

Adapt [the private configuration example](../examples/host-usb-recovery.json) to the actual CT, user, USB ports/IDs, ALSA IDs, node names and routing file. The example uses fictitious hardware values. Node names and stereo pairs remain owned by the existing routing file; gains remain owned by the saved ALSA state. Keep the adapted file outside Git, root-owned and mode0600.

From the reviewed checkout on the host, with the adapted file at `/root/sendspin-usb-recovery.json`:

```sh
touch /etc/sendspin-usb-recovery.disabled
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 scripts/usb-recovery.py /usr/local/libexec/sendspin-usb-recovery
install -o root -g root -m 0600 /root/sendspin-usb-recovery.json /etc/sendspin-usb-recovery.json
install -o root -g root -m 0644 systemd/host/sendspin-usb-recovery.service /etc/systemd/system/
install -o root -g root -m 0644 systemd/host/sendspin-usb-recovery.path /etc/systemd/system/
install -o root -g root -m 0644 systemd/host/sendspin-usb-prepare.service /etc/systemd/system/
/usr/local/libexec/sendspin-usb-recovery rules > /root/99-sendspin-usb-recovery.rules
install -o root -g root -m 0644 /root/99-sendspin-usb-recovery.rules /etc/udev/rules.d/
/usr/local/libexec/sendspin-usb-recovery check
systemd-analyze verify /etc/systemd/system/sendspin-usb-recovery.service /etc/systemd/system/sendspin-usb-recovery.path /etc/systemd/system/sendspin-usb-prepare.service
udevadm verify /etc/udev/rules.d/99-sendspin-usb-recovery.rules
systemctl daemon-reload
udevadm control --reload-rules
```

Review existing files before installing: these commands are explicit file replacements, not a general installer with backup/rollback transactions. Do not overwrite another deployment or change distribution-provided units/rules. The disabled marker keeps queued events from causing recovery during staging.

After preflight, during an authorized audio maintenance window, remove that marker and run one controlled recovery. It refreshes the two physical adapters while retaining room connections. A genuinely changed grant set may instead need the idle-gated CT restart. Verify exact graph links, actual playback, preserved paired state, HA/MA queues/levels and mixer state. Then enable the event and boot units:

```sh
rm /etc/sendspin-usb-recovery.disabled
/usr/local/libexec/sendspin-usb-recovery recover
systemctl enable --now sendspin-usb-recovery.path
systemctl enable sendspin-usb-prepare.service
```

## Maintenance and diagnosis

Before deliberately stopping rooms, changing hardware or editing device permissions:

```sh
touch /etc/sendspin-usb-recovery.disabled
systemctl stop sendspin-usb-recovery.path
systemctl stop sendspin-usb-recovery.service
```

Drain/stop the running operation before making changes. Keep the marker through a reboot if maintenance continues. Inspect the current hardware map before re-enabling. Remove the marker, invoke `recover` deliberately if the CT/target are running, then start the path unit. Recovery does not require another physical replug.

The marker does not change Proxmox's existing onboot policy. If the CT must stay stopped across a host reboot, set that policy deliberately through Proxmox too. Before manually starting a stopped CT after device availability changed, run the helper's `boot` preparation and then the normal `pct start` command. The host boot unit does not wrap every manual CT start/reboot. Changing other audio hardware or USB wiring remains a coordinated hardware-map review: devN permissions refer to device numbers, not permanent physical identities.

```sh
/usr/local/libexec/sendspin-usb-recovery check
cat /run/sendspin-usb-recovery/status.json
journalctl -u sendspin-usb-recovery.service -u sendspin-usb-prepare.service
```

Status is an operation result, not a continuous acoustic health sensor. `check` reads actual inventory/grants without consuming pending events. The component never automatically plays sound, unmutes a room, turns on an amplifier or resends missed TTS. Test ongoing music resume separately; a recovered graph/process does not establish audible continuity.

## Validate and remove

Run the ordinary repository tests and the [recovery-event matrix](VALIDATION.md#recovery-event-checklist). Exercise each card, both cards, return order, rapid return, changed numbers, missing-at-start, maintenance stops and timeout/config-lock failure. A driver unbind/rebind is useful native teardown evidence, but must not be called a physical cable/power test. Record the exact tested files and failures. Host reboot and full restore remain separate gates.

To roll back, disable the marker-controlled event path and drain the operation first. Disable the two enabled units, remove only this component's owned rule, config, three unit files and executable, then reload systemd/udev. Verify the current narrow devN assignments and use ordinary manual audio/CT recovery as needed. Do not blindly restore obsolete numeric mappings after hardware changed. Retain private backups and failure evidence; no vendor package or patched library needs restoring.
