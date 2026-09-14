# ChromaPress v1 Alpha 39

Alpha 39 continues **Part 4/8 — System Configuration** with one narrow gate: autologin/display-manager policy. Alpha 37 identity/accounts and Alpha 38 hostname/machine-identity remain unchanged.

- Verifies the default display manager read-only from the selected layered rootfs.
- Supports explicit evidence for SDDM, LightDM and GDM/GDM3.
- Inspects only known non-secret autologin configuration; no password, hash, token or credential secret is read.
- Adds a separate `Autologin plan — staged only` with Preserve, Enable and Disable choices.
- Enabling autologin requires a safe target username and mandatory target-user re-verification before any later apply.
- The current/default desktop session is preserved in Alpha 39 rather than invented or rewritten.
- Plans are source-SHA-256 locked, explicit SquashFS-evidence bound, preservation-first and Test/Undo compatible.
- The selected ISO remains read-only; Alpha 39 writes no login configuration.
- The acceptance runner now requires real-ISO display-manager/autologin evidence for Part 4 when `--iso` is supplied.
