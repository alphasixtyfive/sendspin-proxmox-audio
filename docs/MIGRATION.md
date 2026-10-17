# Replacing older local players

This is a fresh deployment of stock upstream software. It does not import a patched renderer, Home Assistant app options, household paths or private diagnostic artifacts.

1. Back up the old app/configuration, MA queues/groups/levels and affected Home Assistant scripts/entities. Record physical-port/channel assignments and fixed hardware gains through their existing owners. Retain an explicit rollback procedure.
2. Create the new CT with no competing access to audio hardware. Validate software, pairing and virtual routing first. Give new endpoints pilot names; do not delete the old players yet.
3. Arrange a reversible hardware handoff. Stop the old player application and remove only its selected soundcard passthrough/ownership. Preserve unrelated USB devices and automations. Do not let both native audio servers own the same devices.
4. Prove one room, one card and finally all zones using [VALIDATION.md](VALIDATION.md). Set safe listening levels/mutes in MA and check actual amplifier gains before any audible test. Different renderers' volume percentages are not a calibrated loudness comparison.
5. Pair each new encrypted identity separately. CLI 0.4 refuses the former explicit `--id`; its persisted keypair is the ID. Old MA volume/group/entity assignments do not automatically transfer. Record the old/new IDs and deliberately update MA groups and the existing HA announcement flow after acceptance. Retire duplicate old players only when the working path is clear.
6. Disable/remove the old app through its supported lifecycle. Remove only its obsolete routes/settings and return obsolete custom images/packages to their supported upstream versions after confirming no other consumer needs them. This repository does not downgrade a host hypervisor or edit unrelated HA configuration.

Before removing an old repository, keep a verified Git bundle, release metadata/assets and the matching private configuration backup. Check that the replacement is published and recoverable first. Repository deletion is a separate owner action; the installer never changes GitHub repositories.

The new public project contains no patches, generated private topology, identity blobs, pairing broker or logs. Configuration is the maintained boundary; new source workarounds are not part of this migration.
