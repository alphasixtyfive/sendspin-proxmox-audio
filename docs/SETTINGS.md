# Sendspin Settings

Use the editor to rename players, choose stereo outputs, and add, disable or
remove zones. It edits the private TOML and prepares verified files using the
same renderer as [the command line](CONFIGURATION.md). Install those files
during your usual [maintenance window](OPERATIONS.md).

The editor needs Python 3.11 or newer. The bundled Inter font is distributed
under the [SIL Open Font License](../settings/inter-OFL.txt).

## Try it on a copy

From the repository root, use a fresh file under the ignored `local/`
directory.

```sh
mkdir -p local
cp -i examples/audio.toml local/sendspin.toml
python3 -B settings/sendspin_web.py --project . --config local/sendspin.toml --stages local/stages
```

Open [http://127.0.0.1:8768/](http://127.0.0.1:8768/) in your browser. Use
`--calibration` with a private [host export](CONFIGURATION.md#optional-idle-hardware-gain)
when your TOML enables idle gain.

## Run it in the container

From a trusted checkout, run the following as root for a fresh install. Replace
`local/sendspin.toml` with the private configuration you plan to edit.

```sh
install -d -m 0755 /opt/sendspin-settings
cp -R settings scripts systemd examples upstream-pins.json /opt/sendspin-settings/
install -d -m 0700 /var/lib/sendspin-settings
test -e /var/lib/sendspin-settings/sendspin.toml ||
    install -m 0600 local/sendspin.toml /var/lib/sendspin-settings/sendspin.toml
install -m 0644 systemd/sendspin-settings.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sendspin-settings.service
```

The service uses a dynamic user and binds to loopback. To connect from a
workstation, forward the port over SSH to the container and open the loopback
URL above.

```sh
ssh -N -L 8768:127.0.0.1:8768 user@audio-container
```

On a trusted network you can set `SENDSPIN_BIND` and `SENDSPIN_CLIENT` to
specific IPv4 addresses in `/etc/sendspin-settings/network.conf` and restart
the service. Open the exact address configured in `SENDSPIN_BIND`. The editor
checks the source address and Host, and requires the same Origin for writes.
Use the SSH tunnel for access across networks.

For idle gain, install the private calibration export at
`/etc/sendspin-settings/calibration.json` with owner root and mode 0600. Add
this drop-in using `systemctl edit sendspin-settings.service`, then restart
the service.

```ini
[Service]
LoadCredential=calibration:/etc/sendspin-settings/calibration.json
```

## Save and restore

Keep each entry in `[zones]` and the shared `idle_gain.zones` array on one
line. Edit other TOML settings directly while the editor is stopped.

Keep the existing zone key when moving or renaming a player. Removing a zone
keeps its paired state, so reusing the key can restore that identity.
Diagnostics shows the folder for the saved configuration. The installed
service can restart itself from that section.

Back up the TOML before updating. Replace the application files with the
desired checkout and restart the settings service. See
[Operations](OPERATIONS.md) for rollback of the installed audio configuration.
