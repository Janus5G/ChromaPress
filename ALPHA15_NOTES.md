# ChromaPress v1 alpha 15

Alpha 15 continues the Applications review beyond the approved Home / Personal view.

## Scenario recommendations added

### Office / Business
- AbiWord — lightweight documents.
- Notepad++ Linux — native Qt6 Snap Store port, staged explicitly as a Snap source.

### Development / Engineering
- Refract Studio — bundled from the user-supplied ChromaPlex + PRISME Refract Studio ZIP.
- Notepad++ Linux — quick text/source editing.
- AbiWord — office/specification documents.

### Production / Industrial
- Refract Studio — bundled engineering/production application source.

### Gaming / Team / Education
- MangoHud — FPS/frame time/temperature/CPU/GPU overlay.
- nvtop — live GPU utilisation/process monitor.
- Speedtest CLI — internet bandwidth/latency measurement.
- GLMark2 — lightweight graphics benchmark.

All recommendations use the existing visible `Skip | Add` staging model. Nothing is silently installed.
APT, Snap and bundled-source recommendations are labelled separately in the State column.

## Refract Studio bundle

The original uploaded ZIP is included byte-for-byte as:
`bundled_apps/Refract-Studio-ChromaPlex-PRISME-final.zip`

SHA-256:
`ac025ec2b410cce7a85888b04c7ffea0bcb893570cf16b959e21716d2b626c82`

ChromaPress verifies that checksum when the bundled recommendation is staged. This is an integrity check only; target installation/runtime verification remains a later build-engine gate.

During Alpha 15 assembly, the Refract Studio compiler provenance and CPL/CPA semantic checks passed, but its included `verify_preservation.py` currently disagrees with the ZIP's own historical `TEST_RESULTS.txt` for several editor functions. Alpha 15 therefore does not label the bundled Refract Studio build as runtime-verified or preservation-verified.
