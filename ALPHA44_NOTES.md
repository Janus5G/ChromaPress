# ChromaPress Alpha 44

Part 4 narrow gate: Services / systemd startup.

- Preserves Alpha 37–43 verified/staging gates.
- Verifies systemd unit-directory presence read-only from the selected SquashFS rootfs.
- Does not read unit file contents, enablement symlink targets, environment files or service credentials.
- Stages one `.service` enable/disable intent only.
- Target-unit existence must be re-verified before any later apply.
- Source SHA-256 locked, preservation-first and staging-only.
