# ChromaPress v1 Alpha 30

Part 3 continues with a staging-only root filesystem / SquashFS plan.

- Uses only SquashFS layers explicitly detected in the selected source ISO.
- Shows detected compression and block size before staging.
- Stages a later verified repack with preservation-first safety gates.
- Supports preserving detected compression or requesting xz, zstd, gzip or lz4; apply must verify actual unsquashfs/mksquashfs capability first.
- Preserves the detected block size at this gate and requires unrelated source-image content to remain untouched.
- Source ISO remains read-only; no rootfs or ISO bytes are modified in Alpha 30.
- Source SHA-256 changes block stale Part 3 rootfs plans.
