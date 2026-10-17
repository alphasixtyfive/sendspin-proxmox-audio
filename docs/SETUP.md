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

Precreate this persistent-home account before the official player's sysusers declaration, which has no home of its own. Reuse an existing correctly configured account rather than recreating it. No pipewire-pulse/PulseAudio daemon, desktop session, compiler or nested Docker is needed.

The CT must not independently store/restore hardware calibration: the **host alone owns the mixer state**. Mask both CT ALSA services and suppress its packaged restore rule with the standard same-name `/etc/udev/rules.d` symlink **before granting control devices**. If an override already exists, inspect it rather than overwrite it. Reload CT udev rules only if its daemon is already active; do not start a CT udev daemon just to reload. Gracefully stop the CT before its first device assignment, configure the narrow access described in [SECURITY.md](SECURITY.md), then start it normally. Recheck masks/override and unchanged host mixer gains after CT startup. No host udev database mount or CT metadata-repair service is needed.

From the repository root, install the verified official release:

```sh
sh scripts/install-official.sh ACTUAL_CT_HOSTNAME
```

This script checks hostname, LXC, architecture, Debian version and account home; verifies the upstream archive and installed binary hashes; installs dependencies/payload; and starts nothing. Do not enable the shipped single-player **system** `sendspin-cli.service`; the deployment uses user template instances instead.

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

Refuse activation if any `@...@` marker remains. Client rules are loaded by each player process when connecting; restart players after changing those rules, not just the daemon. They restrict explicit targets from falling back/moving to another room. Loopback playback halves separately wait/relink to their own physical target.

## 3. Start native services, then one player

Use the same account/session for every native command:

```sh
audio_uid=$(id -u sendspin-cli)
audio_runtime=/run/user/$audio_uid
systemctl start "user@$audio_uid.service"
runuser -u sendspin-cli -- env XDG_RUNTIME_DIR="$audio_runtime" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=$audio_runtime/bus" \
  systemctl --user enable --now pipewire.socket pipewire.service wireplumber.service
```

Use that `runuser ... env` prefix for `wpctl status`, `sendspin-cli -l` and these commands too:

```sh
systemctl --user daemon-reload
systemd-analyze --user verify /var/lib/sendspin-cli/.config/systemd/user/sendspin-zone@.service
systemctl --user start sendspin-zone@zone-1.service
sendspin-cli status --control-socket "$audio_runtime/sendspin-zones/zone-1/control.sock"
```

Check exact native outputs, distinct physical clocks, channel routes, service identity and no competing renderer before audio. Adapter creation probes the selected PCM's formats; starting PipeWire is an intentional hardware-initialization boundary. Pair this one endpoint before starting more. Only after acceptance start/enable `sendspin-zones.target` for all configured instances. No script starts content or migrates MA entities.

## 4. Pair and validate

Use MA's official player setup/pairing flow and follow the method it actually offers. In the reviewed MA2.11 beta flow, a player advertising PIN support selects **code pairing**: read the fresh code from `sendspin-cli status --control-socket ...` or the player's private journal and enter it in MA. Run `sendspin-cli pair confirm --control-socket ...` only if status/logs say an attempt is waiting for confirmation. Use `pair-token` only when the server interface offers token pairing; do not require an unavailable token field or add a pairing broker.

Verify `trust: paired` after completion. Codes/tokens and state are secrets; do not paste them into issue reports or source. Each room must have its own state directory. Set safe MA listening levels/mute before an audible test; the defaults do not encode your amplifier calibration. Follow [VALIDATION.md](VALIDATION.md) before migrating.
