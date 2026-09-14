# ChromaPress v1 Alpha 55

Part 4 gate: dedicated non-admin kiosk user.

- Derived only from verified target-ISO /etc/passwd and /etc/group evidence.
- Capability model remains SUPPORTED / SUPPORTED_WITH_REQUIREMENTS / UNSUPPORTED / BLOCKED / UNKNOWN.
- UNKNOWN/BLOCKED/UNSUPPORTED fail closed.
- Stages only creation of a new dedicated non-admin account with automatic UID/GID and home intent.
- Never stages administrative groups, passwords, credentials or shadow data.
- Existing users/groups are preservation-first and username absence is re-verified before apply.
- Restricted login, restricted session, autologin and desktop kiosk behavior are explicitly deferred to later gates.
- Windows/WSL host account state is never used as target evidence.
- Source ISO remains read-only during analysis and staging.
