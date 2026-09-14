# ChromaPress v1 Alpha 27

Part 3 incremental gate: staging-only boot configuration planning.

- Keeps the selected source ISO read-only.
- Adds an explicit boot-plan form for default boot entry, timeout and append-only kernel arguments.
- Plans are staged into the existing Changes workflow; only one boot plan is kept at a time.
- The staged plan is locked to the analyzed source SHA-256 and explicit boot configuration evidence.
- Preflight rejects missing source hashes, missing boot configuration evidence, unsafe control characters, invalid timeouts and empty plans.
- No boot files, kernel, initramfs, firmware, drivers or ISO bytes are written in Alpha 27.
- Existing Alpha 26 source analysis remains intact.
