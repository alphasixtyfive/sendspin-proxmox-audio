# Quiet Proxmox shutdown

Power down the amplifier before Proxmox stops the audio container and releases its USB soundcards. Use the amplifier's physical relay or standby control, with state feedback. Keep its usual playback and power-on policy. This procedure handles an orderly node reboot or shutdown. For a standalone container restart, run the amplifier action before stopping the container.

## Optional Home Assistant example

This example assumes one shared amplifier on a switch with reliable relay state feedback. Add the script to `scripts.yaml` and replace `switch.sendspin_amplifier` with the real entity. Allow time for the amplifier to settle after power-off. Three seconds is a starting point to verify on your hardware. For a receiver shared with TV, only use standby when the receiver is on the Sendspin analogue input.

```yaml
prepare_sendspin_host_shutdown:
  alias: Prepare Sendspin audio for host shutdown
  mode: queued
  sequence:
    - variables:
        amplifier: switch.sendspin_amplifier

    - if: "{{ not is_state(amplifier, 'off') }}"
      then:
        - action: switch.turn_off
          target:
            entity_id: "{{ amplifier }}"
        - wait_template: "{{ is_state(amplifier, 'off') }}"
          timeout: '00:00:03'
        - if: "{{ not wait.completed }}"
          then:
            - stop: Amplifier relay did not report off.
              error: true
        - delay: '00:00:03'

    - if: "{{ not is_state(amplifier, 'off') }}"
      then:
        - stop: Amplifier relay is on or unavailable after settling.
          error: true
```

Check the HA configuration, reload scripts, then test the script and inspect the relay state while the rooms are idle. See [Home Assistant script actions](https://www.home-assistant.io/docs/automation/building-blocks/).

## Call the script before guests stop

Use a trusted HTTPS URL that Proxmox can reach while Home Assistant runs. Create `/etc/sendspin-amplifier-shutdown.curl` on the host, owned by root with mode `0600`, and enter the URL and a dedicated Home Assistant access token. Keep the completed file outside Git and support bundles.

```text
url = "https://home-assistant.example/api/services/script/prepare_sendspin_host_shutdown"
header = "Authorization: Bearer REPLACE_WITH_DEDICATED_TOKEN"
header = "Content-Type: application/json"
```

Inspect `systemctl cat pve-guests.service` before adding a drop-in. The example below uses the Proxmox VE 9.2 vendor stop commands. Preserve your installed unit's commands and their order. Place the amplifier call before `stopall`, while the network and HA are still available. The nine-second timeout bounds the added wait. A failed request logs an error and Proxmox continues shutting down.

Use `systemctl edit pve-guests.service` to add the following as a local drop-in. Review it after Proxmox upgrades and keep the vendor `ExecStop` entries current.

```ini
[Unit]
After=dbus.service networking.service

[Service]
ExecStop=
ExecStop=-/usr/bin/vzdump -stop
ExecStop=-/usr/bin/curl --disable --config /etc/sendspin-amplifier-shutdown.curl \
    --proto =https --fail --silent --show-error --connect-timeout 2 --max-time 9 \
    --data {} --output /dev/null --write-out "Sendspin amplifier preparation HTTP %%{response_code}\n"
ExecStop=/usr/bin/pvesh --nooutput create /nodes/localhost/stopall
```

Verify `pve-guests.service` with `systemd-analyze verify`, reload systemd, and inspect `systemctl show pve-guests.service -p After -p ExecStop`. Test the exact curl call separately during idle time, replacing `%%` with `%` when running it in a shell. Check the actual relay state. Then record an orderly reboot. Confirm relay-off in HA history precedes the audio CT shutdown in the Proxmox journal, and listen for any transient.

To roll back, remove only this drop-in and reload systemd. Revoke the token and remove its private curl configuration if retiring the integration.

## Time the reboot

```sh
journalctl -b -1 -o short-iso-precise -u pve-guests.service
pvenode task list --vmid CT_ID --limit 10
```

Compare the audio CT's stop request and completion with the entire guest shutdown. Proxmox stops guests in reverse startup order, so a CT can be the last item in the journal after other guests consumed most of the time. The reference audio CT stopped cleanly in about two seconds. Removing an unnecessary startup delay let HA start earlier. Keep each guest's clean shutdown allowance and diagnose the guest that actually takes the time. [Proxmox startup and shutdown ordering](https://github.com/proxmox/pve-docs/blob/master/pct.adoc#automatic-start-and-shutdown-of-containers)

After boot, check the Proxmox UI, HA and Music Assistant separately. Confirm every configured Sendspin instance reconnects and that the optional USB recovery watcher is active. An available host UI precedes room recovery.
