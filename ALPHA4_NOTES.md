# ChromaPress v1 Alpha 4

Part 1 storage fail-closed gate.

- Large official ISO writes now enforce the configured free-space reserve before writing.
- A conservative per-release download headroom is included (Lubuntu 4 GiB, Ubuntu 7 GiB).
- Resume subtracts the existing partial size from required download headroom.
- The configured cache path is used exactly; no C:, WSL-root, temp, or alternate fallback path is selected.
