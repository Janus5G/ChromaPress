# ChromaPress Alpha 45

Part 4 narrow gate: Timers / systemd startup.

- Preserves Alpha 37–44 verified/staging gates.
- Reuses verified read-only systemd unit-directory evidence for timer staging.
- Does not read timer/unit contents, enablement symlink targets, environment files or service credentials.
- Stages one `.timer` enable/disable intent only.
- Target-timer existence must be re-verified before any later apply.
- Source SHA-256 locked, preservation-first and staging-only.
