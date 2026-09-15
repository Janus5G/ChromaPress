# Security Policy

ChromaPress works with operating-system images, privileged Linux tooling and generated application source. Security reports are taken seriously.

## Supported version

Security fixes are focused on the current public release/release-candidate line and the current `main` branch.

Older alpha snapshots may not receive separate fixes.

## Reporting a vulnerability

Please do **not** open a public issue for a vulnerability that could expose secrets, enable unintended command execution, bypass a verification gate, alter an input ISO unexpectedly, or otherwise create a meaningful security risk.

When the GitHub repository provides private vulnerability reporting, use:

**Security → Report a vulnerability**

If private vulnerability reporting is not available, contact the maintainer through the GitHub profile/repository contact route and request a private channel before sharing exploit details.

Include, when possible:

- affected ChromaPress version/commit,
- operating system,
- whether Windows/WSL or native Linux is involved,
- a concise description,
- reproduction steps,
- expected vs. actual behavior,
- and the smallest safe proof of concept.

Do not include real credentials, private keys or unrelated personal data.

## Security model

ChromaPress is designed around several boundaries:

- selected input ISOs are treated as read-only,
- analysis and staging are separated from mutation/build work,
- unsupported or missing evidence should fail closed,
- target-image evidence is kept distinct from host Windows/WSL state,
- privileged operations should be explicit,
- API credentials are intended to remain session-scoped,
- AI-generated code is not automatically trusted or executed merely because it was generated,
- and static evidence is not presented as proof of runtime or hardware behavior.

A report showing that one of these boundaries can be bypassed is especially important.

## Scope note

ChromaPress is open-source software and does not promise a bug bounty, guaranteed response time or certification for any particular deployment.

Please allow reasonable time for investigation before publishing vulnerability details.
