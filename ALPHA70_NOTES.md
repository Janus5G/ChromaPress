# ChromaPress v1 Alpha 70 — Part 6 Complete

Alpha 70 completes Part 6 — AI App Studio as one consolidated gate.

- AI App Studio remains optional; ChromaPress core works without AI.
- Supported provider adapters exposed in the UI are only adapters actually implemented: OpenAI, Caffeine Inference (configured compatible endpoint), generic OpenAI-compatible endpoint, and local loopback endpoint.
- Generation credentials are session-only by default and are never written to project changes, generated source, ISO plans, manifests, diagnostics or QSettings.
- Generation credentials and generated application's runtime credentials are separate concepts.
- Target Linux context is structured and source-hash bound: distribution, version, architecture, desktop, package manager, detected package/library hints and installer family.
- Generated output must be an inspectable multi-file project using explicit file separators and a required `chromapress-app.json` review manifest.
- Unsafe paths, traversal, duplicate files, oversized output, embedded credential/private-key material, malformed manifests and tampered staged file hashes fail closed.
- Dependency packages become normal ChromaPress staged package operations.
- Files, packages, services, permissions, autostart, desktop integration, security implications, build plan and test plan are shown before staging.
- Generated code is never auto-executed on the Windows host and never blindly injected into an ISO. Apply remains blocked until explicit build/test/security/dependency/human review gates are completed.
- Source-ISO changes invalidate a staged Part 6 AI project.
- Consolidated `testpack/part6_tests.zip` uses the same fail-fast/resume/full-seal runner as Parts 4 and 5.

## Fix 1 — Windows GUI staging gate

- `Stage reviewed app` is explicitly disabled during `AiStudioPage` initialization.
- A reviewed AI project cannot be staged until the target Linux context is valid **and** the user explicitly checks the human-review confirmation.
- Changing the generated project or target context invalidates the acknowledgement and disables staging again.
- The staged Part 6 payload records `human_review_acknowledged=true`; preflight rejects payloads without explicit acknowledgement.
