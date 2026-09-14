# Alpha 49 — Part 4 sysctl gate

Alpha 49 adds one narrow Part 4 sysctl staging gate while preserving all approved Alpha 37–48 behavior.

- Verifies only sysctl infrastructure/path metadata read-only inside the selected SquashFS rootfs.
- Does not read existing sysctl configuration contents or effective runtime values.
- Stages one safe dotted sysctl key with one integer value.
- Preserves all existing sysctl files; any later apply must use a managed drop-in and re-verify target-key/apply semantics.
- Source ISO remains read-only and all changes remain staging-only.
