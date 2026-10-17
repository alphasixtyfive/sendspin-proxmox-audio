# Deployment ownership

This repository configures released Sendspin and distribution PipeWire/WirePlumber inside a dedicated unprivileged Proxmox CT. PipeWire/WirePlumber own physical output routing; the existing host ALSA facilities own explicitly chosen fixed hardware gains; Sendspin owns each persisted endpoint identity; Music Assistant owns listening levels, mute, groups, queues and announcements.

Expected result: independently controlled stereo endpoints over selected multichannel soundcards, without virtual USB, PulseAudio output, renderer source patches or another audio-control daemon. The direct rule is one named stereo route and one stock player per endpoint, each with separate persisted state and exact target selection.

All examples use generic zone names and explicit placeholders. No live values, secrets, gains, traces, pair broker or old patches are copied. The configuration has passed the bounded two-card/seven-zone checks in [VALIDATION.md](VALIDATION.md); deployment, safe local configuration and remaining lifecycle tests remain operator actions.
