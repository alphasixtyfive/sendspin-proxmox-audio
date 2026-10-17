# Setup

Do not run these commands on the Proxmox host or an existing Home Assistant VM. They are for the dedicated approved CT. Nothing in this repository creates or starts a container automatically.

## 1. Base and account

Use Debian 13 amd64. The official 0.4.0 binary requires GLIBC_2.38 and GLIBCXX_3.4.32; Debian 12's glibc 2.36 is too old. Use normal distribution updates, not replacement C libraries.

Create the CT **without sound-device grants first**. Root inside the CT installs standard packages:

```sh
apt-get update
apt-get install --no-install-recommends pipewire pipewire-bin libpipewire-0.3-modules \
  libspa-0.2-modules wireplumber dbus-user-session libpam-systemd udev alsa-utils
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

Copy the example to ignored `local/` and edit there. Never fill public examples with private values.

```sh
cp -a examples/two-ca7-seven-zones local
```

Replace `@CARD_A_ALSA_ID@` and `@CARD_B_ALSA_ID@` in `pipewire.conf.d/61-ca7-physical.conf.template` with two distinct, persistent ALSA card IDs observed in `/proc/asound/cards` and `/sys/class/sound/cardN/id`. Numeric card indices can change. Identical serial numbers require a host-owned standard udev identity rule matched to the observed physical ports; keep that mapping and calibration in the host's existing configuration owner. Do not guess IDs or copy another household's port paths.

Use the [host audio guide](HOST-AUDIO.md) to assess optional standard index allocation against the actual onboard/USB inventory. The tested 3/4 example is not a default for every machine. Stable physical card IDs remain authoritative; refresh specific Proxmox device mappings when numeric nodes change.

The physical nodes are stock PipeWire `context.objects` adapters opening only each named card's PCM0 playback path. They bypass automatic ALSA card enumeration and create eight-channel S16LE/48kHz outputs. The supplied WirePlumber config disables its automatic ALSA monitor, preventing competing hardware nodes. Keep the adapters' distinct `clock.name` values: named ALSA paths do not automatically provide numeric-card clock identities, and the two USB clocks must remain independent. Do not disable resampling. Verify raw ALSA channel order and driver map; do not copy a PulseAudio surround order blindly.

Replace `@SENDSPIN_SERVER_URL@` in every player template with your verified MA Sendspin endpoint, for example `ws://ma.example.invalid:8927/sendspin`. Save completed files as `zone-N.conf`, without `.template`. The invalid example domain is not a working default. CLI 0.4 requires aiosendspin 10+ encrypted rc1; verify your MA build.

CA7 also exposes a separate stereo-headphone PCM1. The explicit paths end in `,0`, selecting the eight-channel PCM0 playback device; no capture or headphone node is created. `flags = [ nofail ]` keeps PipeWire alive if a card cannot open at startup, but it does not schedule rediscovery. Make the card available and perform an ordinary PipeWire restart before retrying. See [operations](OPERATIONS.md#replug-and-restart-limits).

The routing file creates seven generic stereo sinks across two cards. Edit its channel pairs/number of zones for your wiring; update the target and client fail-closed rule to the same exact zone set. No gain is configured here. Use an existing host ALSA owner/standard `alsactl` restoration for fixed hardware calibration; keep listening volume/mute in MA. Check physical outputs at safe levels before content. FC/LFE must be full-range stereo if used as a room pair.

Install completed native files as root:

- Completed `61-ca7-physical.conf.template` → `/etc/pipewire/pipewire.conf.d/61-ca7-physical.conf`, plus the other `pipewire.conf.d/*.conf` files
- `client.conf.d/*.conf` → `/etc/pipewire/client.conf.d/`
- `wireplumber.conf.d/51-manual-ca7.conf` → `/etc/wireplumber/wireplumber.conf.d/51-manual-ca7.conf`
- Completed `zone-N.conf` → `/etc/sendspin-zones/`, readable by `sendspin-cli`
- `systemd/sendspin-zone@.service` and your configured `sendspin-zones.target` → `/var/lib/sendspin-cli/.config/systemd/user/`, owned by `sendspin-cli`

For the player configuration and user units, these root commands set explicit access without changing an existing home recursively:

```sh
install -d -o root -g sendspin-cli -m 0750 /etc/sendspin-zones
install -o root -g sendspin-cli -m 0640 local/sendspin-zones/zone-*.conf /etc/sendspin-zones/
install -d -o sendspin-cli -g sendspin-cli -m 0700 \
  /var/lib/sendspin-cli/.config /var/lib/sendspin-cli/.config/systemd \
  /var/lib/sendspin-cli/.config/systemd/user
install -o sendspin-cli -g sendspin-cli -m 0644 \
  systemd/sendspin-zone@.service local/sendspin-zones.target \
  /var/lib/sendspin-cli/.config/systemd/user/
```

On Debian 13's systemd 257, install the two audio-service drop-ins as well:

```sh
for daemon in pipewire wireplumber; do
  install -d -o sendspin-cli -g sendspin-cli -m 0700 \
    "/var/lib/sendspin-cli/.config/systemd/user/$daemon.service.d"
  install -o sendspin-cli -g sendspin-cli -m 0644 \
    "systemd/$daemon.service.d/50-direct-restart.conf" \
    "/var/lib/sendspin-cli/.config/systemd/user/$daemon.service.d/"
done
```

These use systemd's `RestartMode=direct` for automatic daemon recovery. Without it, a transient daemon crash can stop the room services through `PartOf`, leaving them stopped after the daemon returns. Explicit stops and restarts still propagate. Check the loaded `RestartMode` for both services after `daemon-reload`; both must say `direct`. This setup targets Debian 13; don't copy this policy to an older systemd without checking support and behavior.

Inspect existing files and directory owners before running these commands. The zone configuration directory needs traversal permission as well as readable files; root-owned mode 0600 files will prevent the player from starting.

Refuse activation if any `@...@` marker remains. Client rules are loaded by each player process when connecting; restart players after changing those rules, not just the daemon. They restrict explicit targets from falling back/moving to another room. Loopback playback halves separately wait/relink to their own physical target.

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
as_audio systemctl --user start sendspin-zone@zone-1.service
as_audio sendspin-cli status --control-socket "$audio_runtime/sendspin-zones/zone-1/control.sock"
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

Replace `CTID` with your container ID. The `up=10` value is a delay **after** this CT starts, before the next guest. It does not wait for a USB device to appear. Both configured soundcards and their narrow device mappings must be present when Proxmox starts the CT.

Inside the CT, keep linger enabled for `sendspin-cli`, enable the PipeWire socket/services as above, and enable the configured zone target only after pairing and playback checks:

```sh
as_audio systemctl --user enable --now sendspin-zones.target
as_audio systemctl --user is-enabled pipewire.socket pipewire.service wireplumber.service sendspin-zones.target
as_audio systemctl --user is-active pipewire.service wireplumber.service sendspin-zones.target
```

Run these user commands through `as_audio` from step 3, or its explicit account/runtime prefix. Verify `loginctl show-user sendspin-cli -p Linger` says `Linger=yes`. Then restart the CT through Proxmox and check all room identities, routes and listening levels. Do not enable `pve-container@CTID.service` yourself; Proxmox owns container startup.
