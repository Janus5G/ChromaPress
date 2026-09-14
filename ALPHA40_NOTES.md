# ChromaPress Alpha 40

Part 4 incremental gate: locale/language.

- Preserves Alpha 37 identity/accounts, Alpha 38 hostname/machine identity, and Alpha 39 autologin/display-manager behavior.
- Adds read-only rootfs locale evidence from `/etc/default/locale`, `/etc/locale.conf`, or `/etc/locale.gen`.
- Stages only `LANG`; existing `LANGUAGE` and `LC_*` overrides are preserved.
- Target locale availability must be verified again before any future apply step.
- Source ISO remains read-only; no credential secrets are read or staged.
