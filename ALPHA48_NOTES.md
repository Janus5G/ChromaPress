# Alpha 48 — Part 4 AppArmor gate

Alpha 48 adds one narrow Part 4 AppArmor staging gate while preserving all previously approved Alpha 37–47 behavior.

- Verifies AppArmor component presence read-only inside the selected SquashFS rootfs.
- Accepts explicit AppArmor evidence from `apparmor_parser`, the AppArmor systemd unit, or the AppArmor policy directory.
- Does not read AppArmor profile contents, parser configuration contents, abstractions/tunables, or policy secrets.
- Stages only enable/disable AppArmor intent; no profile mutation is implemented at this gate.
- Locks the plan to the source ISO SHA-256 and explicit SquashFS evidence.
- Requires AppArmor boot/apply semantics to be re-verified before any later apply step.
- Keeps the source ISO read-only and preserves unrelated configuration.
- Adds real-ISO acceptance coverage `P4-REAL-ROOTFS-APPARMOR`.

Next security gates remain separate: SELinux, sysctl/kernel settings, broader security overlays and authentication/recovery policies.
