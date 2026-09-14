# ChromaPress v1 Alpha 26

Part 3/8 continues with verified, read-only Boot, Kernel & Hardware evidence.

Implemented in this increment:

- Preserves the Alpha 25 BIOS/UEFI, El Torito, hybrid/system-area, EFI, kernel, initramfs and SquashFS inspection.
- Parses explicit boot configuration files from the selected ISO without modifying them.
- Displays parsed boot entry titles, declared default(s), declared timeout(s), and kernel command-line arguments with their source configuration file.
- Detects systemd-boot entry `.conf` files when present.
- Uses xorriso El Torito report evidence for the boot catalog when the catalog is not visible as a normal ISO filesystem member.
- Reads package manifests already present on the ISO and exposes conservative kernel, firmware/microcode, driver and DKMS package hints.
- Does not infer that a driver is usable merely because a package is named in a manifest.
- No mutation buttons are introduced. The selected source ISO remains read-only.
- Existing Part 1/2 behavior is preserved.

Safety rule: only explicit source evidence is displayed. Alpha 26 does not write boot records, bootloader configuration, kernels, initramfs, firmware or drivers.
