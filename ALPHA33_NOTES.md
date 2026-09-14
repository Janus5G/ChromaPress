# ChromaPress v1 Alpha 33

Part 3 increment: explicit runtime integration verification planning.

- Binds an immutable/volatile or controlled-persistence runtime plan to the exact detected SquashFS, boot configuration, kernel and initramfs evidence from the selected ISO.
- Preserves the detected boot structure and requires boot-config re-verification rather than recreating boot flags from assumptions.
- Requires runtime-hook verification followed by the detected distro-native initramfs regeneration mechanism.
- Makes persistent-mount handling explicit: volatile mode has no persistent mount; controlled persistence requires label/UUID resolution and mount verification before persistent binds.
- Keeps the source ISO read-only and all integration work staging-only.
