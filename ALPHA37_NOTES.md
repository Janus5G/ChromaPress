# ChromaPress v1 Alpha 37

Alpha 37 continues **Part 4/8 — System Configuration** with the first staging-only configuration gate.

- Adds read-only rootfs verification of `/etc/passwd`, `/etc/group` and optional `/etc/login.defs` through direct SquashFS offsets.
- `/etc/shadow` is deliberately never read.
- Adds a structured `Identity / accounts plan — staged only` for target-system default-user intent.
- Username, optional display/full name and standard/admin role can be staged only after rootfs account evidence is verified.
- Administrator staging is allowed only when a distro admin group (`sudo` or `wheel`) is explicitly present in verified rootfs group evidence.
- Passwords, password hashes, tokens and recovery secrets are not accepted or stored in this gate.
- Staged plans are source-SHA-256 locked, preservation-first and Test/Undo compatible.
- The selected ISO remains read-only; no account or credential bytes are modified.
- Corrected rootfs capability detection for squashfs-tools versions where `-offset` is shown only by the full help output; staging remains fail-closed if offset support is genuinely unavailable.
- Corrected identity rootfs verification again: actual read-only direct-offset reads now determine capability instead of help-text parsing; both documented `-offset` and `-o` spellings are attempted without modifying or extracting the source layer.
- Corrected identity verification on WSL hosts where direct embedded-offset SquashFS reads fail: source analysis now uses a tightly scoped WSL-root read-only loop-mount fallback, reads only `/etc/passwd`, `/etc/group` and optional `/etc/login.defs`, never reads `/etc/shadow`, and unmounts immediately.
- Acceptance hardening: the complete runner now verifies that the Windows venv imports the current project `src/chromapress` tree rather than a stale installed copy, and Part 4 real-ISO acceptance fails unless `/etc/passwd` and `/etc/group` are actually verified read-only. This prevents a green automation report from masking the manual identity/rootfs failure seen during Alpha 37 testing.

## Alpha 37 runtime-source synchronization correction
- The acceptance runner now detects when the preserved Windows `.venv-win` still imports an older non-editable `site-packages` copy after a ZIP overlay.
- When that exact mismatch is found, the existing one-command acceptance run performs a local/offline `pip install --no-deps --no-build-isolation --editable <project>` into the preserved venv and then re-verifies the import path.
- This changes only the local venv package link. It does not modify the selected source ISO or fetch dependencies from the network.
- The purpose is to ensure `\.venv-win\Scripts\chromapress.exe` always runs the current Alpha 37 `src/` tree after an overlay update.
