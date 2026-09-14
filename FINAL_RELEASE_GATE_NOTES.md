# ChromaPress 1.0.0a72 — Final release gate

This release-candidate test build keeps the accepted eight-Part ChromaPress v1 architecture and adds only final release requirements agreed after the Alpha 72 Windows acceptance.

- MIT License restored as the final open-source license, with `Copyright (c) 2026 Janus Rokkjær` and the standard MIT warranty/liability disclaimer.
- About shows the actual version, MIT license, ChromaPress icon and a **Share ChromaPress** button. The button copies a short share message; no unverified project URL is hard-coded before the GitHub release exists.
- The user's own generated applications and customized ISO output are not branded as ChromaPress products by the tool.
- `chromapress-app.json` remains an internal AI App Studio review manifest. A separate deployable-file boundary excludes it from generated application output.
- Deployable AI-generated files are blocked if they contain an automatic ChromaPress fingerprint. No ChromaPress telemetry or shared ChromaPress runtime is added.
- Generation API credentials remain session-only and are not persisted in QSettings, staged into an ISO, or copied into generated source.

The final test gate must pass before Windows `.exe`, Debian `.deb`, and GitHub release artifacts are built.
