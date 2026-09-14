# ChromaPress v1 Alpha 18

Part 2 Applications extension: dedicated School / Education profile.

## Added

- New first-class `School / Education` system-use profile.
- The previous `Gaming / Team / Education` profile is now `Gaming / Team`; education is no longer mixed with gaming.
- New human-facing `Education & Learning` application section for native desktop entries carrying the Education category.
- `ChromaLearn AI` 0.3.0 is bundled as an optional School / Education recommendation.
- ChromaLearn uses the standard `Skip | Add` staging model; it is never silently installed.
- The bundled ChromaLearn `.deb` is pinned to SHA-256 `39e02ae512c0b2139ee6dcdf52f9e7a81f5cd7e14109896f5a8020a51c078ff2`.
- Global application search can find ChromaLearn from every active profile.

## ChromaLearn package inspection

The supplied Debian package declares `Section: education` and installs a normal `Education` desktop entry. It also contains `/usr/share/chromalearn/developer-repo/` with an initialized `.git` repository, application source, tests, docs, packaging, examples and the build script. ChromaPress therefore bundles the `.deb` itself; a second source archive is not required for ISO inclusion.

## Scope

This remains Part 2/8. No ChromaLinux desktop integration or ChromaLinux-specific behavior is added to ChromaPress.

## Verification in this build environment

- Python compile: PASS
- Core tests: 41/41 PASS
- GUI smoke tests: 5 skipped here because PySide6 is not installed in the Linux test environment; run them on the existing Windows PySide6 environment.
