# ChromaPress Alpha 54 — Part 4 System configuration overlays

Alpha 54 continues Part 4 only. Part 5 is not started.

This gate implements a narrow, real system-configuration overlay mechanism using a verified target `/etc/profile.d` drop-in path. It does not provide arbitrary file injection; Part 5 Files/Custom Content remains separate.

- Capability model: `SUPPORTED | SUPPORTED_WITH_REQUIREMENTS | UNSUPPORTED | BLOCKED | UNKNOWN`.
- Reads only target `/etc/profile` to verify profile.d sourcing semantics and lists only immediate `/etc/profile.d` entry names for collision detection. Existing drop-in contents are never read.
- Missing/unverifiable semantics stay `UNKNOWN`, never guessed from Lubuntu/Ubuntu.
- Staging supports only deterministic generated non-secret environment overlays named `99-chromapress-<name>.sh`.
- Arbitrary shell content, secret-like variable names, shell metacharacters and overwrite of an existing target filename are blocked.
- Existing `/etc/profile`, all existing profile.d files and unrelated configuration are preserved. A later apply must re-verify target filename absence.
- Windows/WSL host configuration is never consulted.
- Changes/Test/Undo uses the central staged Changes model; analysis/staging never mutates the source ISO.

Dedicated acceptance gate: `P4-ALPHA54-CONFIG-OVERLAY`.
