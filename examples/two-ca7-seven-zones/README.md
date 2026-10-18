# Native policy reference

These files supply the fixed-rate/manual-monitor policy used by the renderer and the isolated routing fixtures used by `tests/pipewire_policy.py`. They are kept for those checks; configure an installation through [audio.toml](../audio.toml) and the [configuration guide](../../docs/CONFIGURATION.md).

The former separate player, physical-adapter and room-target templates were removed. The renderer now creates those from the single topology.
