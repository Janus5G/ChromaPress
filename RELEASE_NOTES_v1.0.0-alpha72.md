# ChromaPress v1.0.0-alpha72

ChromaPress is a free and open-source Linux ISO customization workbench licensed under MIT.

This release completes the eight-part Alpha 72 implementation and final release gate.
The Windows build is intended as the easiest path for school/IT administrators and uses
WSL2 for Linux-native image tooling. The Debian package uses the same ChromaPress engine
natively on Linux.

## Highlights

- Source ISO analysis remains read-only and preservation-first.
- Unified Applications and Components workbench backed by target-image evidence.
- Boot, kernel, hardware, installer, desktop and system-configuration staging.
- Optional AI App Studio with user-selected provider/model and session-only generation API key.
- AI-generated deployable applications do not receive automatic ChromaPress branding,
  telemetry IDs, runtime stubs or `chromapress-app.json` fingerprints.
- Presets, Expert/production workflow and cross-distribution acceptance framework.
- ChromaLearn 0.4.5 and Refract Studio are optional bundled recommendations; neither is
  silently installed.
- MIT license and standard MIT warranty/liability disclaimer.

## Final gate

The accepted Windows run reported:

- Parts 1–8: `AUTOMATION_PASS_MANUAL_REMAINS`
- Part 4–8 test packs: `TESTPACK_PASS`
- Part 4–8 staged gates: `AUTOMATED_GATE_PASS`
- `FAIL=0`
- `NOT_IMPLEMENTED=0`
- `FINAL_RELEASE_GATE=PASS`

The remaining `MANUAL_REQUIRED` checks are the deliberately non-automatable runtime,
visual, VM/hardware and human-review checks documented by ChromaPress; they are not
reported as automated failures.

## License and output

ChromaPress is MIT licensed. Programs, Linux images, scripts and other output produced
with ChromaPress do not become ChromaPress-owned or ChromaPress-branded merely because
ChromaPress was used to create them. Third-party software and Linux distribution content
remain subject to their own licenses.
