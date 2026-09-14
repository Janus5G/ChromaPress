# ChromaPress v1 Alpha 25

Part 3/8 begins with read-only Boot, Kernel & Hardware inspection.

Implemented in this increment:

- `Boot & Hardware` is no longer a placeholder.
- The selected ISO remains read-only.
- The page shows detected BIOS/UEFI modes, El Torito presence, hybrid/system-area evidence, bootloader family, boot catalog and volume ID.
- ISO-visible boot configuration files, EFI images, kernel images and initramfs/initrd images are listed.
- SquashFS layers are listed and their compression/block size are reported when `unsquashfs` can verify them directly by offset.
- ISO-level firmware hints are shown conservatively; ChromaPress does not claim full firmware/driver inventory until the rootfs can be inspected safely.
- No boot/kernel/firmware/driver mutation controls are enabled in Alpha 25.
- Existing Part 1/2 behavior is preserved.

Safety rule: source boot structures are evidence, not assumptions. Alpha 25 does not write to the selected ISO.
