# ChromaPress final Windows release test package

This is the last release-gate overlay before building the Windows `.exe`, Debian `.deb`, and GitHub release artifacts.

It is designed to be extracted directly over the already accepted ChromaPress `1.0.0a72` project folder. Keep `.venv-win` unchanged.

The overlay finalizes:

- MIT licensing and MIT warranty/liability disclaimer;
- About + ChromaPress icon + Share ChromaPress;
- target-image-backed Components regression protection;
- session-only AI generation API key protection;
- neutral AI-generated application output: `chromapress-app.json` stays internal and is excluded from deployable output;
- no automatic ChromaPress branding, telemetry IDs, hidden metadata or shared ChromaPress runtime in generated application output;
- the existing Parts 1–8 acceptance packs, including the updated final license regression.

Run from the ChromaPress project root in PowerShell:

```powershell
.\.venv-win\Scripts\python.exe chromapress_final_release_test.py --iso "E:\Custom linux builder\ISO\lubuntu-26.04-desktop-amd64.iso"
```

The command first runs the dedicated final-release regressions, then reruns the full Parts 1–8 acceptance with a clean test-pack restart. It writes final Markdown and JSON reports into `test-reports`.

Required result before packaging:

```text
FINAL_RELEASE_GATE=PASS
```

`MANUAL_REQUIRED=8` from the established 8-Part acceptance is expected and is not a failure. It remains the truthful boundary for checks that require human/VM/hardware runtime verification.
