# ChromaPress v1 Alpha 38

Alpha 38 continues **Part 4/8 — System Configuration** with one deliberately narrow new gate: hostname and machine identity. The verified Alpha 37 identity/account gate is preserved unchanged.

- Adds read-only rootfs verification of `/etc/hostname` and the state of `/etc/machine-id`.
- The actual machine-id value is never exposed in the GUI and is never stored in a staged plan.
- Adds a separate `Hostname / machine identity plan — staged only`.
- Hostname changes accept only safe lowercase Linux hostnames.
- Machine-id policy is explicit: preserve current boot behavior or regenerate on first boot.
- Plans are source-SHA-256 locked, rootfs-evidence bound, preservation-first and Test/Undo compatible.
- The selected ISO remains read-only; no hostname or machine-id bytes are modified.
- The complete acceptance runner now also requires real-ISO hostname/machine-identity evidence when `--through 4 --iso ...` is used, preventing a green automated run from masking a blocked GUI gate.
- Autologin is intentionally **not** added in Alpha 38. It remains a separate later Part 4 gate so account/login security can be reviewed independently instead of combining multiple policy changes in one increment.
