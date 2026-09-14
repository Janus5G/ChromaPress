# ChromaPress Alpha 41

Part 4 incremental gate: keyboard layout.

- Preserves all verified Alpha 37–40 Part 4 behavior.
- Adds read-only rootfs keyboard evidence from `/etc/default/keyboard` or `/etc/vconsole.conf`.
- Stages only the primary keyboard layout; existing model, variant and options are preserved.
- Target layout availability must be verified again before any future apply step.
- Source ISO remains read-only; no credential secrets are read or staged.
