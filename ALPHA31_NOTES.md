# ChromaPress v1 Alpha 31

Part 3 increment: immutable/volatile runtime planning.

- Adds a staging-only plan for a read-only SquashFS rootfs with volatile OverlayFS.
- Uses tmpfs for the OverlayFS upper/work runtime layer.
- Makes reboot semantics explicit: runtime changes do not survive reboot.
- Requires distro-native initramfs integration and boot integration to be re-verified before any later apply.
- Locks the plan to the selected source ISO SHA-256 and explicit SquashFS base layer.
- Keeps the selected ISO read-only and preserves unrelated source content.
- Controlled persistent directories and persistent partitions/volumes are intentionally deferred to a later gate.
