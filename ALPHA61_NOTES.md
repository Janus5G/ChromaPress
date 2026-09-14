# ChromaPress Alpha 61

Part 4 gate: **persistence policy**.

- Adds a target-only kiosk runtime persistence-policy gate.
- Supports explicit volatile runtime policy and controlled selected-directory policy.
- Underlying OverlayFS/tmpfs/volume/mount/initramfs mechanics are delegated to the existing Part 3 immutable/controlled-persistence model; Part 4 does not reimplement them.
- Controlled persistence is restricted to explicit subdirectories beneath the kiosk user home and never broad system paths.
- Existing persistence configuration, mount contents, persistent data and host storage/mount state are not read.
- UNKNOWN/BLOCKED/UNSUPPORTED fail closed.
- Source ISO remains read-only during analysis/staging.

Test infrastructure: the release tree uses one verified `testpack/chromapress_tests.zip` plus `chromapress_testpack.py`. The runner is fail-fast, keeps a checkpoint outside source files, resumes at the failed test on the next run, and performs a full seal pass after a successful resume. The established manual Stage → Changes → Test → Undo path remains available.

Part 5 is not started.
