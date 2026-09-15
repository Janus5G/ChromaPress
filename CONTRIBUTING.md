# Contributing to ChromaPress

Thank you for considering a contribution to ChromaPress.

Ideas, bug reports, documentation improvements, tests and focused code changes are welcome. You do not need to understand the entire ISO-servicing engine before contributing to a clearly scoped area.

## Before you start

For a substantial change, open an issue first and describe:

- the problem or use case,
- what you want to change,
- which platform(s) it affects,
- and whether it touches ISO servicing, privileges, security, packaging or AI App Studio.

Small documentation fixes and narrowly scoped corrections can normally go directly to a pull request.

## Core project rules

Contributions must preserve the existing safety model unless a change is explicitly discussed and approved.

In particular:

- The selected source ISO must not be modified in place.
- Analysis must not silently turn into mutation.
- Changes should remain staged/reviewable before application.
- Unknown capability or missing evidence must not silently become `VERIFIED`.
- Windows/WSL host state must not be substituted for missing target-image evidence.
- Security-sensitive or privileged operations must remain explicit and narrowly scoped.
- API keys, passwords, tokens, private keys and other secrets must not be committed or written into project files.
- AI-generated code must be treated as reviewable source code, not trusted merely because it was generated.
- Existing Windows + WSL and native-Linux behavior should not be broken by platform-specific changes.

If your proposal intentionally changes one of these rules, explain why in the issue/pull request.

## UI and localization

ChromaPress currently supports Danish and English.

New user-visible UI text should use the existing translation path (`tr(...)`) rather than bypassing localization.

Please check both language modes when changing dialogs, navigation, status text or validation messages.

## Tests

At minimum, run the final release regression gate:

```bash
python -m pytest -q final_testpack/tests/test_final_release_gate.py
```

For changed Python files, also run an appropriate syntax/compile check.

If your change affects a platform-specific feature, packaging, privilege handling, ISO mutation, build output or runtime behavior, describe the real test you performed. A unit/static test should not be presented as proof of boot, install, hardware or deployment behavior.

## Pull requests

Keep pull requests focused. A good pull request should explain:

- what changed,
- why it changed,
- which files/areas are affected,
- what was tested,
- any known limitations,
- and whether security-sensitive behavior changed.

Please do not include:

- virtual environments,
- `build/` or `dist/`,
- `__pycache__`,
- local ISO images,
- generated test/cache output,
- local backups,
- API keys or other secrets.

## Dependencies

Avoid adding a dependency unless it provides clear value.

If a dependency is necessary, explain:

- why the existing stack cannot reasonably provide the feature,
- where the dependency is used,
- its license,
- and whether it adds network, privilege or runtime requirements.

## Security-sensitive changes

Changes involving any of the following deserve explicit review:

- `subprocess`, shell execution or command construction,
- `sudo`, `pkexec` or privilege elevation,
- filesystem deletion/permissions,
- mounts, bootloaders, initramfs or ISO writing,
- network downloads or repository configuration,
- credential handling,
- GitHub Actions permissions/releases,
- AI credential storage or generated-code execution.

This does not mean those changes are forbidden; it means they must be easy to inspect and justify.

## AI-assisted contributions

AI-assisted code is welcome.

Please review and test it before submission. The same correctness, security and maintainability requirements apply regardless of whether code was written manually or with an AI assistant.

## License

By submitting a contribution, you agree that your contribution may be distributed under ChromaPress' MIT License.
