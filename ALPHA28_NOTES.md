# ChromaPress v1 Alpha 28

Part 3 adds a staging-only kernel/initramfs safety plan. The selected ISO remains read-only.

- Detects the distro-family initramfs mechanism expected at a later verified apply gate: update-initramfs, dracut or mkinitcpio.
- Allows staging an explicit initramfs-regeneration intent only when source SHA-256, kernel image and rootfs evidence exist.
- Last viable kernel protection is mandatory and cannot be disabled.
- Changes/Test/Undo remains the review path.
- No kernel, initramfs, rootfs, firmware, driver or ISO bytes are modified in Alpha 28.
- A later apply gate must verify the native tool inside the selected rootfs before execution.


## Same-version UI correction

- Compact boot/kernel action rows: status is inline with Stage/Reset controls instead of consuming a separate row.
- Compact one-line read-only footer; full source path/hash remains available as a tooltip.
- Added a system-wide scroll fallback around every main workbench page so lower content remains reachable at smaller/restored window sizes.
- Main window still opens maximized; existing horizontal Changes splitter remains user-resizable.
- No Part 3 staging or source-mutation logic changed.
- Boot & Hardware now has a vertical splitter between controls and detected-source structure so the lower analysis area can be resized by dragging.
