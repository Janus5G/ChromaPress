# ChromaPress v1 Alpha 56

Part 4 gate: restricted login.

- Target-only capability detection: verified account metadata plus target-rootfs `usermod` or `passwd` lock tool presence.
- Capability model remains `SUPPORTED | SUPPORTED_WITH_REQUIREMENTS | UNSUPPORTED | BLOCKED | UNKNOWN`.
- Missing verification stays `UNKNOWN`; staging fails closed.
- Alpha 56 stages only password-authentication locking for a non-admin kiosk account.
- Existing verified target users can be selected; an absent kiosk username carries an explicit dependency on the Alpha 55 dedicated-user gate.
- `/etc/shadow` contents, passwords, PAM contents, SSH configuration, host login state, autologin and session policy are not read.
- Autologin, desktop/session behavior, SSH/PAM policy and unrelated login mechanisms are preserved for their own gates.
- Root/admin accounts are blocked.
- Source ISO remains read-only during analysis and staging; all changes use the central Changes/Test/Undo model.
