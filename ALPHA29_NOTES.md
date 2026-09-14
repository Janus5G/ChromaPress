# ChromaPress v1 Alpha 29

Part 3 adds the first manifest-backed firmware/driver planning gate while keeping the selected ISO read-only.

- Shows firmware/microcode and driver/DKMS packages only when they are explicitly present in source manifests.
- Allows staging a re-resolution intent for one manifest-backed hardware package; it does not download or change packages yet.
- Test requires a valid source SHA-256, target rootfs evidence, the distro-native initramfs mechanism, signed repository metadata validation, dependency resolution, last-viable-kernel protection and initramfs regeneration.
- A plan is blocked if the selected source ISO changes after staging.
- Changes/Test/Undo remains the review path.
- No firmware, driver, DKMS, kernel, initramfs, rootfs or ISO bytes are modified in Alpha 29.
## GUI feedback correction
- Kept version at Alpha 29.
- Firmware/driver staging now gives explicit feedback when package/action selection is incomplete.
- Successful hardware staging gives a visible STAGED confirmation and still remains staging-only/read-only.
- No apply/build behavior was enabled.
