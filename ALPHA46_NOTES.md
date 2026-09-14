# ChromaPress Alpha 46

Part 4 narrow gate: Targets / systemd default startup target.

- Preserves Alpha 37–45 verified/staging gates.
- Reuses verified read-only systemd unit-directory evidence for default-target staging.
- Does not read target unit contents, the current `default.target` symlink target, environment files or service credentials.
- Stages one `.target` default-startup intent only.
- Target-unit existence must be re-verified before any later apply.
- Source SHA-256 locked, preservation-first and staging-only.
