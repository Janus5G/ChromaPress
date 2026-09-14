# ChromaPress v1 Alpha 57

Part 4 gate: restricted session.

- Target-only capability detection; no Windows/WSL host session state is consulted.
- First safe backend is deliberately narrow: verified SDDM + verified target session descriptor filenames + collision-free `/etc/sddm.conf.d`.
- Missing/other unverified display-manager mechanisms stay `UNKNOWN`; existing managed-file collision is `BLOCKED`; no unsupported claim is inferred from distro name.
- Alpha 57 stages only a structured SDDM `[Autologin] Session=<verified .desktop>` intent for the kiosk account.
- Effective restricted access requires explicit Alpha 56 password-login restriction and same-user Alpha 39 autologin dependencies; both must be re-verified before apply.
- Session descriptor contents and existing SDDM drop-in contents are never read; existing sessions, display-manager configuration, PAM/SSH configuration and other users are preserved.
- Full desktop/service lockdown, network restrictions, persistence/recovery and FIDO2/TPM remain later Part 4 gates.
- Source ISO stays byte-for-byte read-only during analysis/staging; all changes use Changes/Test/Undo.
