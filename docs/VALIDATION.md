# Acceptance record

## Configuration reliability review — 18 October 2026

v0.1.7 corrects a gap in the initial import checks: valid quoted PipeWire properties/channel names were incompatible with the existing recovery reader. That failure was reproduced with the installed reader; the corrected stage passed the same reader for all seven routes. No initial stage had been installed. Regenerate v0.1.6 stages before use.

All 86 Linux source tests passed, including a renderer/recovery compatibility test and stage verification for partial, stale, modified, extra or symlinked output. Thirty-four silent native checks passed, including stock parser equivalence, UTF-8 labels and compatibility with the actual installed reader. Live files, seven player PIDs, host rules/map and recovery executable remained unchanged; 57 fresh HA/MA comparisons passed. No service was restarted and no generated file was installed. Existing acoustic/hardware acceptance and remaining gates below are unchanged.

## Single-configuration import — 18 October 2026

The [TOML renderer](CONFIGURATION.md) passed 80 Linux source tests, including unknown/duplicate input, conflicting outputs/ports/identities, disabled zones, stable state keys across rename/move, optional two-card recovery-map generation, deterministic staging, existing/symlink destination refusal and sanitized parse errors. Repository hygiene and installer shell checks passed as well.

On the reference installation, 31 silent checks passed: the stock PipeWire parser found equivalent routing, physical adapters, client rules and fixed native policy; player configs and service policy matched; target dependencies/membership matched apart from its display description; the host recovery map matched. Existing file hashes, host ID rules, recovery executable and all seven player PIDs stayed unchanged. A fresh 57-check HA/MA comparison was unchanged. The generated files were staged only; this does not claim activation, recovery or acoustic acceptance of a newly installed configuration.

## Native deployment

**Tested deployment configuration, 17 October 2026; broader acceptance remains qualified.** The reference installation uses two Cubilux CA7 interfaces and seven independent stereo zones on an unprivileged Debian 13 amd64 CT. The unchanged official CLI 0.4.0/core 0.9.5 binary hash matches upstream; PipeWire 1.4.2/WirePlumber 0.5.8 are distribution packages. Public examples keep generic names/placeholders and no private identities, addresses, levels or port paths.

Passed on that installation:

- With the v0.1.1 service policy, an external SIGTERM to one player recovered in about 5.3 seconds without restarting the other six. PipeWire restart recovered the participating players while a deliberately stopped room stayed stopped; WirePlumber restart recovered all seven. Stopping the zone target stayed effective beyond the restart interval, and starting it restored the group. Paired state, configuration, routing and fixed gains remained unchanged.
- A full graceful CT shutdown and start brought up the audio services and all seven enabled players without a login or manual service start. Proxmox Start at boot was enabled and linger persisted. The original HA/MA entities, queues, references, settings and automation states matched after the restart. This tests the CT startup path; it is not a physical host power-cycle test.
- Twenty-three isolated Linux installer tests passed, including the actual download command, invalid archives/checksums, duplicate-service guards, fresh installation, account-home access, exact executable destinations, candidate execution failure, interruption and atomic replacement/failure boundaries. They ran as an unprivileged account with real shell/archive/checksum/file operations and substituted package/service commands. CI runs the same repository checks and installer tests.

The first injected PipeWire crash exposed a gap in v0.1.1: the daemon recovered, but PartOf stopped its dependent players. Standard systemd user drop-ins setting RestartMode=direct corrected that transient-stop behavior on systemd 257. Repeated real SIGKILL tests then recovered PipeWire and WirePlumber automatically while respecting a deliberately stopped room. A separate graceful stop/start still required the documented explicit target restart. No renderer or vendor source was changed.

A further crash trial left the automatically recovered players running, without a manual group restart. Two normal five-room announcements then completed and restored levels/mutes; the actual five Sendspin streams and exact hardware channel links passed 146 checks. A short PC-microphone recording covered the messages without changing microphone settings. The user was away, so this is recorded acoustic evidence and functional recovery, not a new human listening confirmation or proof that every room is crackle-free. The earlier listening results below remain separate.

- Two explicit stock physical adapters opened eight-channel S16LE at 48 kHz, with distinct clock names, exact stereo channel pairs and disabled automatic ALSA monitoring. Narrow control/PCM0 grants and host-only mixer ownership were verified.
- Actual Sendspin CLI streams were inspected during a five-zone announcement and a separate two-zone test, covering all seven endpoints. Named-target fail-closed properties were present and active links reached only the intended room/channel pairs. This is a positive opened-stream/link proof, not all possible negative-policy cases.
- The first single-room announcement and the normal five-room announcement flow were confirmed clear by the listener in the rooms heard. The separate two-zone service request exceeded its response timeout; observed correct links and eventual idle return are not a separate successful service-response or listening claim.
- Ordinary CT restarts and an isolated, owners-closed snd_usb_audio reload preserved stable card IDs, expected grants, full hardware mixer state (including unused controls), unrelated sound/USB consumers, persisted player identities and native routes. The obsolete metadata bind was removed and both manual adapters continued to work.
- The final normal five-room cold and warm announcements were both confirmed clear by the listener in the rooms heard. Both physical PCMs were observed closed before the cold start, then running at 48 kHz/eight channels. PipeWire error counters remained zero during the bounded observations. Two approximately 5.3 ms lost/regained-sync startup warnings were retained; neither the counters nor listening establish sample-perfect timing or explain those warnings.
- Music announcement/resume passed against an existing queue: music played, the announcement interrupted it, and music resumed at a progressing position with volume restored. Ordered queue items, source and current item were preserved; the test finished paused. This exercises the normal existing announcement path without queue replay or a renderer patch.
- During a real MA-server outage/restart, all seven CT player processes stayed running and automatically reconnected. Post-return checks found registrations, references and settings unchanged. This establishes that bounded server-disconnect/reconnect case; it does not establish USB recovery or every network failure mode.

The final reference environment also used the ordinary released Proxmox QEMU 11.0.3-4 package and Home Assistant audio 2026.08.0, with their earlier local replacements retired. The CT audio route uses the host driver directly; these versions record the tested surrounding environment, not a dependency on a QEMU or PulseAudio audio backend. Exact software baselines are in [upstream-pins.json](../upstream-pins.json).

Not yet established: physical host boot, physical cable/power removal, arbitrary changed-minor combinations, full backup restoration, every missing-target/default-change/forced-move policy scenario, or long-term/sample-perfect synchronization. A clean graph or absence of warnings alone does not establish acoustic quality. Local repository checks below cover syntax/inventory/privacy; they do not simulate hardware or replace these observations.

A subsequent real CT boot exercised startup retry: one player initially rejected its named output before the graph had registered it. The existing five-second restart policy recovered it automatically. All seven current processes started within6.7seconds of CT init and remained stable; loaded daemon policy and configuration/device hashes were unchanged. The early snapshot remains recorded as failed, followed by the timestamp/state proof of convergence. Two normal five-room announcements then completed, restored levels/mutes and passed150 actual stream/hardware-route checks; HA/MA references/settings/queues were unchanged. Boot verification must check every configured player, not just the active group target.

## Repeatable routing and recovery test

Run this optional integration test as root inside the dedicated Debian 13 audio CT, from the repository root:

```sh
python3 tests/pipewire_policy.py --expected-hostname ACTUAL_CT_HOSTNAME \
  --public-root . --output /var/tmp/sendspin-policy-results-UNIQUE
```

Use the CT's actual hostname and a fresh output path. The test requires the reviewed PipeWire 1.4.2/WirePlumber 0.5.8 baseline and the unchanged pinned example files. It launches disposable stock processes as nobody with no supplementary groups, no real sound-device access, a private bus/runtime and null outputs. It does not modify production services, send audio to the house or connect to Music Assistant. Temporary processes/runtime are cleaned up; the requested result directory retains its checks and graph evidence.

The reference run passed 51 recorded checks across two cases. It checks missing named targets, changes of default output, exact seven-room channel links, removal/return of one virtual card while the other stays correct, and event history for wrong-target links. Channel expectations come from the example routing file, avoiding a second manually maintained map.

A missing room makes pw-cat reject its stream; after that client exits, retry uses an explicit new client. This is not an actual Sendspin automatic-recovery test. The loopback case separately verifies automatic exact relinking when its virtual physical target returns. Neither case establishes real USB re-enumeration, driver permissions, mixer restoration or acoustic quality. The ordinary CI job checks this test's syntax; it does not run the native integration test.

## Recovery event checklist

### Optional host recovery acceptance

The separately enabled [host component](USB-RECOVERY.md) passed native selected USB-leaf driver unbind/rebind tests on the reference deployment. This causes actual host ALSA teardown and return; it is not physical cable or power removal.

- Each card recovered automatically with the other card still present. A repeated test with one room deliberately stopped kept that room stopped. PipeWire, WirePlumber and participating player PIDs stayed unchanged; the healthy physical node retained its object serial. CT init/configuration and saved gains stayed unchanged.
- During one normal five-room announcement, actual Study/Dining streams were proven before teardown. Dining's stream and exact hardware links were also proven while the other card was absent. Return restored the routes, retained every daemon/player PID and healthy physical node, and the ordinary announcement restored all original levels/mutes without a manual correction or replay.
- A stopped CT was prepared and started with both selected cards absent. All seven virtual room routes/players started. Returning the second card first, then the first, exercised two automatic idle-gated CT restarts with only the required narrow grants refreshed. Per-port identities, routes and saved gains passed despite reversed card indices. No manual recovery was needed in these accepted phases.
- Seventy Linux tests cover the installer and recovery decisions, identities, parsing, native graph rejection, physical-node recreation, stream-idle gating and failure boundaries. These substituted-command tests complement the native trials; they are not hardware simulation.

An earlier candidate restarted the whole audio graph on ordinary USB return. Its native route test passed, but one announcement left a room at its temporary announcement level. That candidate was rejected. The accepted method refreshes only affected physical adapters; the exact upstream volume-command race remains a hypothesis. The whole-CT fallback still needs an idle window and cannot lock out a new MA request arriving concurrently.

Physical unplug/power loss, host boot and full restore remain separate unperformed gates. Acceptance does not establish uninterrupted audio on the missing interface, automatic replay, all flapping patterns or a new human listening verdict. This component uses event and boot units, with no periodic restart timer.

Record a healthy baseline first: configured room identities, queues/levels, card IDs and physical ports, device grants, calibration, service policy and actual routes. After each event, inspect the room's real output and normal playback; active processes alone are insufficient.

| Event | Expected behavior and checks |
| --- | --- |
| Unexpected player exit | The affected instance restarts after about five seconds with the same identity. Other rooms and queue context remain intact. |
| PipeWire/WirePlumber crash | Stock automatic daemon recovery and direct restart mode preserve participating rooms. Check actual routing/playback and confirm a deliberately stopped room stays stopped. |
| Deliberate daemon stop, then later start | Use the documented [audio-server maintenance](OPERATIONS.md#audio-server-maintenance) sequence to restore the configured room group. |
| MA restart or network outage | Existing clients reconnect with their original paired identities. Check availability, references, levels and queue context; the check must not replay a queue itself. |
| CT shutdown/start | Linger and enabled services start the configured rooms without login. Wait for each configured player to reach a stable running PID; an active target alone is insufficient. Check loaded direct restart mode, pairing, narrow grants, gains and routes. |
| Card absent at startup | Optional host boot preparation includes only present validated nodes; virtual rooms start without the card. Before a manual CT start after device changes, run its boot preparation explicitly. Without this component use [manual device recovery](OPERATIONS.md#replug-and-restart-limits). |
| USB unplug/replug with the same permitted nodes | Optional recovery refreshes only affected physical adapters, restores saved gains and verifies routes/PIDs. Driver teardown/return passed; physical cable removal is a separate test. |
| USB return with changed indices/minors | The optional operation waits for paired idle streams, gracefully stops the CT, refreshes only corresponding narrow grants and starts it. Reversed reserved indices and absent-at-start grant additions passed. Review other hardware changes deliberately; never substitute a default output. |
| Physical host reboot | Check host module options, per-port IDs, full gains, CT boot and unrelated USB consumers. This remains a separate untested gate. |
| Backup restoration | Stop the original before activating its copied identities. Restore host configuration separately, then check ownership, mapping, gains and playback. Archive integrity/content comparison does not replace a full restore rehearsal. |

The reference deployment's daemon failures, MA outage, CT startup and optional native USB recovery are recorded above. Physical USB unplug/replug and host reboot have not been performed. The base player installer does not enable host recovery; it requires separate deliberate installation. Neither path installs a periodic repair service.

Repeat these gates for each new installation or relevant upgrade:

1. Verify the official binary checksum/version, correct native backend, user/session ownership and one physical hardware owner. Inspect private state isolation, paired trust and actual target names. No leftover template markers.
2. Inspect two explicit eight-channel physical adapters, different hardware clock names, disabled automatic ALSA monitoring and the expected uniquely named stereo sinks. Verify actual opened rate/format/channel order, independent fixed gains and safe listening level. Graph properties alone do not prove an opened PCM. Test every physical pair, including full-range center/LFE, with no leakage or crossover.
3. Prove one room, then one card's concurrent independent streams, then all configured zones. Test normal music, short cold/warm TTS, announcements during music and restoration of group/mute/levels. An aligned long music stream does not establish aligned initial speech.
4. Verify client fail-closed properties on a real opened stream. Remove its named virtual target while other targets remain; it must not link to another room. Restore it and check exact relinking. Test default-target changes and attempted moves separately.
5. Test absent-at-start hardware, USB return, PipeWire restart and MA disconnect/reconnect. Record finite-budget/manual recovery limitations honestly. The optional host operation recreates static adapters on validated events; without it, failed static creation needs manual recovery. Check narrow permissions and same/different-minor behavior.
6. Reboot the CT, then test host reboot separately when authorized. Persist identities, pairing, levels, routes and fixed hardware gains. Measure idle behavior instead of assuming devices suspend when stock players retain their streams.
7. Finish with normal unmonitored playback through the existing announcement flow and human listening. Avoid heavy compilation/diagnostic monitors during the comparison. Judge audible speech or justified waveform discontinuities, not warning count alone.

A failed essential gate blocks acceptance on that installation. Keep a working rollback available and report the exact failed behavior. Recovery must address a verified ownership/lifecycle boundary; it must not conceal failed playback acceptance. Record additional results with exact versions and the scope actually exercised.
