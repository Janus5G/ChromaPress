# ChromaPress v1 Alpha 32

Part 3 increment: controlled persistence planning.

- Adds a staging-only controlled persistence plan on top of the read-only SquashFS + volatile OverlayFS runtime.
- Makes reboot semantics explicit: only listed directories survive reboot; all other runtime changes remain volatile.
- Stages a dedicated target-system ext4 volume intent with explicit size and safe label.
- Rejects root, boot, pseudo-filesystem and traversal paths for persistence.
- Requires distro-native initramfs, boot and mount integration verification before any later apply.
- Never repartitions or modifies the selected source ISO at this stage.
