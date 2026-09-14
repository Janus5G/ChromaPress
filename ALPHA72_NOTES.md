# ChromaPress v1 Alpha 72 — Part 8 Complete

Alpha 72 completes **Part 8 — Cross-Distro Hardening & Acceptance** as one consolidated batch.

## What is implemented

- Locked distribution priority matrix:
  - PRIMARY: RHEL, Ubuntu LTS
  - NEXT: Debian Stable, Rocky Linux, AlmaLinux, Oracle Linux
  - SECONDARY: Fedora, Linux Mint, CentOS Stream
  - COMMUNITY: Arch Linux, Manjaro
  - LATER: SUSE/openSUSE
- Read-only target `/etc/os-release` evidence is collected from the selected rootfs when available. Host/WSL distribution state is not substituted for target evidence.
- Exact adapter contracts record expected package format, package manager, installer mechanism and initramfs mechanism without claiming the distro is already verified.
- Generic `RPM-family Linux` / `Arch-family Linux` evidence never silently becomes RHEL/Rocky/Arch or another named distribution.
- One inspectable Part 8 acceptance record covers source readability, distro/architecture/rootfs detection, package/repository/installer/kernel evidence, filesystem/custom-content preservation, rebuild, BIOS/UEFI preservation, staged-rootfs verification, unintended changes, diagnostics, output SHA-256 and runtime acceptance.
- **Analysis alone can never produce `VERIFIED`.** Runtime/manual checks require explicit evidence.
- Build & Verify now shows Part 8 static acceptance state and can export shareable JSON diagnostics without source paths or credentials.
- Acceptance records and diagnostics are SHA-256 fingerprinted and source-SHA locked.
- The source ISO remains read-only throughout analysis/acceptance.

## Automated acceptance

Part 8 owns `testpack/part8_tests.zip` with fail-fast/resume behavior. Previous Part 4–7 packs remain separate and are run first by `chromapress_acceptance.py --through 8`.

Real per-distro rebuild/boot/install/live-session validation remains deliberately `MANUAL_REQUIRED` until actual runtime evidence exists. A distro is never marked VERIFIED merely because the analyzer recognizes it.
