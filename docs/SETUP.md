# Setup

Do not run these commands on the Proxmox host or an existing Home Assistant VM. They are for the dedicated approved CT. Nothing in this repository creates or starts a container automatically.

## 1. Base and account

Use Debian 13 amd64. The official 0.4.0 binary requires GLIBC_2.38 and GLIBCXX_3.4.32; Debian 12's glibc 2.36 is too old. Use normal distribution updates, not replacement C libraries.

Create the CT **without sound-device grants first**. Root inside the CT installs standard packages:

```sh
apt-get update
apt-get install --no-install-recommends pipewire pipewire-bin libpipewire-0.3-modules \
  libspa-0.2-modules wireplumber dbus-user-session libpam-systemd udev alsa-utils python3
systemctl mask --now alsa-restore.service alsa-state.service
install -d /etc/udev/rules.d
ln -s /dev/null /etc/udev/rules.d/90-alsa-restore.rules
adduser --system --group --home /var/lib/sendspin-cli --shell /usr/sbin/nologin sendspin-cli
usermod -aG audio sendspin-cli
loginctl enable-linger sendspin-cli
```

Create this persistent-home account before installing the player. The installer requires a non-root account with audio-group membership. Its home must be a real directory owned by that account's numeric UID, with read, write and traversal access for the account. A reused root-owned or inaccessible home is rejected; inspect its ownership and permissions rather than applying a recursive repair. No pipewire-pulse/PulseAudio daemon, desktop session, compiler or nested Docker is needed.

The CT must not independently store/restore hardware calibration: the **host alone owns the mixer state**. Mask both CT ALSA services and suppress its packaged restore rule with the standard same-name `/etc/udev/rules.d` symlink **before granting control devices**. If an override already exists, inspect it rather than overwrite it. Reload CT udev rules only if its daemon is already active; do not start a CT udev daemon just to reload. Gracefully stop the CT before its first device assignment, configure the narrow access described in [SECURITY.md](SECURITY.md), then start it normally. Recheck masks/override and unchanged host mixer gains after CT startup. No host udev database mount or CT metadata-repair service is needed.

From the repository root, install the verified official release:

```sh
sh scripts/install-official.sh ACTUAL_CT_HOSTNAME
```

This script checks hostname, LXC, architecture, Debian version and account home; verifies the upstream archive and binary hashes; installs dependencies and the verified binary; and starts nothing. Do not enable the single-player **system** `sendspin-cli.service`; the deployment uses user template instances instead.

The installer copies only the verified binary and build information. It runs the staged binary's `--version` before replacing an existing executable, and rejects a symlink or non-file at the destination. It does not unpack the upstream system service or sysusers declaration. It masks `sendspin-cli.service` to keep that single-player service from competing with the room services. If that service is already active or enabled, stop and disable it deliberately before continuing. See the [installation failure boundary](OPERATIONS.md#upgrades-and-rollback) before upgrading a working installation.

## 2. Make explicit local configuration

Use [one private TOML](CONFIGURATION.md) for the MA endpoint, persistent card IDs, room sockets and optional existing host recovery map:

```sh
mkdir -p local
cp examples/audio.toml local/audio.toml
# Edit the private TOML with the actual endpoint, card IDs and wiring.
python3 scripts/configure.py check local/audio.toml
python3 scripts/configure.py render local/audio.toml --output local/staged-01
python3 scripts/configure.py verify local/audio.toml --output local/staged-01
```

Observe persistent ALSA IDs on the host through `/proc/asound/cards` and `/sys/class/sound/cardN/id`. Numeric indices can change; identical serials need a physical-port identity rule. [Host audio](HOST-AUDIO.md) owns identity, optional index allocation and fixed calibration. Verify the actual PCM0 channel map; center/sub must provide full-range stereo for a room. The CA7 headphone PCM1 is outside this profile. CLI 0.4 requires MA with aiosendspin 10+ encrypted rc1.

The generated adapters use separate physical clocks, S16LE/eight channels/48kHz, no automatic ALSA monitoring and normal resampling. `nofail` permits startup without a card; [host recovery](USB-RECOVERY.md) handles return when installed. [Operations](OPERATIONS.md#replug-and-restart-limits) covers deliberate manual recovery.

For a fresh installation, review the stage and existing destination files before running these root commands inside the CT. For an existing installation, use the [maintenance procedure](CONFIGURATION.md#review-and-install-native-files) first, including drift review and obsolete instance/file removal. The host recovery map is installed separately on the host.

```sh
audio_stage=local/staged-01
python3 scripts/configure.py verify local/audio.toml --output "$audio_stage"
for folder in pipewire/pipewire.conf.d pipewire/client.conf.d wireplumber/wireplumber.conf.d; do
  install -d -o root -g root -m 0755 "/etc/$folder"
  install -o root -g root -m 0644 "$audio_stage/ct/etc/$folder/"*.conf "/etc/$folder/"
done
install -d -o root -g sendspin-cli -m 0750 /etc/sendspin-zones
install -o root -g sendspin-cli -m 0640 "$audio_stage/ct/etc/sendspin-zones/"*.conf /etc/sendspin-zones/
install -d -o sendspin-cli -g sendspin-cli -m 0700 \
  /var/lib/sendspin-cli/.config /var/lib/sendspin-cli/.config/systemd \
  /var/lib/sendspin-cli/.config/systemd/user
install -o sendspin-cli -g sendspin-cli -m 0644 \
  "$audio_stage/ct/user/sendspin-zone@.service" "$audio_stage/ct/user/sendspin-zones.target" \
  /var/lib/sendspin-cli/.config/systemd/user/
for daemon in pipewire wireplumber; do
  install -d -o sendspin-cli -g sendspin-cli -m 0700 \
    "/var/lib/sendspin-cli/.config/systemd/user/$daemon.service.d"
  install -o sendspin-cli -g sendspin-cli -m 0644 \
    "$audio_stage/ct/user/$daemon.service.d/50-direct-restart.conf" \
    "/var/lib/sendspin-cli/.config/systemd/user/$daemon.service.d/"
done
```

The user drop-ins set `RestartMode=direct` on Debian 13/systemd 257, preserving dependent players during automatic audio-daemon recovery. Explicit stops/restarts still propagate. Check both loaded values after `daemon-reload`. Player configs need directory traversal and group read access; root-only files prevent startup. Client rules load in each player process: changing them requires player restarts as well as any required graph restart.

## 3. Start native services, then one player

Use the same account/session for every native command:

```sh
audio_uid=$(id -u sendspin-cli)
audio_runtime=/run/user/$audio_uid
systemctl start "user@$audio_uid.service"
as_audio() {
  runuser -u sendspin-cli -- env XDG_RUNTIME_DIR="$audio_runtime" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$audio_runtime/bus" "$@"
}
as_audio systemctl --user daemon-reload
as_audio systemctl --user enable --now pipewire.socket pipewire.service wireplumber.service
as_audio systemctl --user restart pipewire.service wireplumber.service
as_audio systemctl --user show pipewire.service wireplumber.service -p Id -p RestartMode
```

The explicit restart loads the newly installed graph even if linger or the socket had already started the daemons. Both loaded RestartMode values must be direct. This interrupts any existing rooms in the shared graph; use this installation step while they are stopped.

Use `as_audio` for `wpctl status`, `sendspin-cli -l` and the following user commands too:

```sh
as_audio systemd-analyze --user verify /var/lib/sendspin-cli/.config/systemd/user/sendspin-zone@.service
as_audio systemctl --user start sendspin-zone@study.service
as_audio sendspin-cli status --control-socket "$audio_runtime/sendspin-zones/study/control.sock"
```

Check exact native outputs, distinct physical clocks, channel routes, service identity and no competing renderer before audio. Adapter creation probes the selected PCM's formats; starting PipeWire is an intentional hardware-initialization boundary. Pair this one endpoint before starting more. Only after acceptance start/enable `sendspin-zones.target` for all configured instances. No script starts content or migrates MA entities.

## 4. Pair and validate

Use MA's official player setup/pairing flow and follow the method it actually offers. In the reviewed MA2.11 beta flow, a player advertising PIN support selects **code pairing**: read the fresh code from `sendspin-cli status --control-socket ...` or the player's private journal and enter it in MA. Run `sendspin-cli pair confirm --control-socket ...` only if status/logs say an attempt is waiting for confirmation. Use `pair-token` only when the server interface offers token pairing; do not require an unavailable token field or add a pairing broker.

Verify `trust: paired` after completion. Codes/tokens and state are secrets; do not paste them into issue reports or source. Each room must have its own state directory. Set safe MA listening levels/mute before an audible test; the defaults do not encode your amplifier calibration. Follow [VALIDATION.md](VALIDATION.md) before migrating.


## 5. Start at boot

On the **Proxmox host**, enable Start at boot for the chosen CT. Choose an order that fits your other guests:

```sh
pct set CTID --onboot 1 --startup order=30,up=10
pct config CTID
```

Replace `CTID` with your container ID. The `up=10` value is a delay **after** this CT starts, before the next guest. It does not wait for USB. In the base setup, both configured soundcards and their narrow mappings must be present. The separately installed [host recovery](USB-RECOVERY.md) prepares available grants before host autostart so virtual rooms can start without a missing card; before a manual CT start after availability changes, invoke its `boot` preparation explicitly.

Inside the CT, keep linger enabled for `sendspin-cli`, enable the PipeWire socket/services as above, and enable the configured zone target only after pairing and playback checks:

```sh
as_audio systemctl --user enable --now sendspin-zones.target
as_audio systemctl --user is-enabled pipewire.socket pipewire.service wireplumber.service sendspin-zones.target
as_audio systemctl --user is-active pipewire.service wireplumber.service sendspin-zones.target
```

Run these user commands through `as_audio` from step 3, or its explicit account/runtime prefix. Verify `loginctl show-user sendspin-cli -p Linger` says `Linger=yes`. Then restart the CT through Proxmox and check all room identities, routes and listening levels. Do not enable `pve-container@CTID.service` yourself; Proxmox owns container startup.
