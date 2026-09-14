# ChromaPress Alpha 53 — Part 4 Security defaults / login UMASK

Alpha 53 continues Part 4 only. Part 5 is not started.

This is the next remaining narrow `security settings` gate after the already verified firewall, AppArmor, SELinux and sysctl work. It adds target-only capability detection and staging for the default login/file-creation UMASK in `/etc/login.defs`.

- Capability model: `SUPPORTED | SUPPORTED_WITH_REQUIREMENTS | UNSUPPORTED | BLOCKED | UNKNOWN`; missing `/etc/login.defs` evidence remains `UNKNOWN`, never guessed `UNSUPPORTED`.
- Reuses only verified target-rootfs `/etc/login.defs` evidence; Windows/WSL host security state is never consulted.
- Exposes only non-secret `UMASK` and `USERGROUPS_ENAB` metadata. Full configuration and credentials are not exposed.
- Staging supports only allowlisted UMASK values `022`, `027` and `077`.
- Existing `/etc/login.defs`, PAM configuration, account/password policy and unrelated security configuration are preserved.
- A later apply must re-verify the exact target directive and effective login/session semantics before writing anything.
- All intent goes through Changes/Test/Undo and remains source-SHA locked, preservation-first and staging-only.
- Source ISO remains byte-for-byte read-only during analysis and staging.

Dedicated acceptance gate: `P4-ALPHA53-SECURITY-DEFAULTS`.
