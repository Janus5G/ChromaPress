# ChromaPress Alpha 52 — Part 4 SELinux capability detection / configuration

Alpha 52 continues Part 4 only. Part 5 is not started.

This gate adds capability-driven, preservation-first SELinux analysis and staged configuration using the shared capability states `SUPPORTED`, `SUPPORTED_WITH_REQUIREMENTS`, `UNSUPPORTED`, `BLOCKED` and `UNKNOWN`.

Key behavior:

- Analysis is bound to the selected target ISO/rootfs only; Windows/WSL host SELinux state is never queried or substituted.
- `/etc/selinux/config` is read only for the non-secret `SELINUX=` and `SELINUXTYPE=` metadata when present.
- Existing SELinux policy trees are detected only as path/name metadata and are always preserved; policy contents are not read, replaced or removed.
- Installed SELinux packages/components, target package-manager/repository metadata, target-carried SELinux package files, kernel SELinux capability metadata, initramfs mechanism and existing boot configuration evidence are tracked separately.
- Missing SELinux is not treated as `UNSUPPORTED`. If addability cannot be proven safely, capability is `UNKNOWN` and staging is blocked.
- `UNSUPPORTED` requires positive incompatible target evidence rather than absence alone.
- Verified targets may expose `enforcing`, `permissive` and `disabled`. Unknown/blocked/unsupported targets expose preservation only.
- Package requirements, filesystem relabel, reboot and post-boot verification are explicit staged dependencies.
- Boot/kernel/initramfs requirements are delegated to the existing Part 3 model. Alpha 52 does not directly write kernel arguments, GRUB configuration, kernel files or initramfs content.
- All intent goes through the central Changes/Test/Undo model; source ISO analysis/staging is read-only.

Dedicated acceptance gate: `P4-ALPHA52-SELINUX`.

When a real ISO is supplied to `chromapress_acceptance.py`, the gate validates the Alpha 52 SELinux capability schema and then either:

- builds and preflights a real staged SELinux permissive-mode plan when capability is verified as supported, or
- proves fail-closed behavior by verifying that staging is rejected for `UNKNOWN`, `BLOCKED` or `UNSUPPORTED` targets.
