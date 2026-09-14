# ChromaPress Alpha 62

Part 4 gate: **administrator/recovery policy**.

- Adds one bounded policy for a dedicated recovery administrator.
- Recovery administrator must be non-root and must not be the explicitly configured autologin account.
- Existing verified administrators can be designated directly; a new username explicitly depends on the Alpha 50 administrator-account gate before apply.
- Existing non-admin accounts are never silently promoted by this gate.
- Recovery/kiosk role separation is mandatory and re-verified before apply.
- No password, password hash, recovery secret, credential, PAM/SSH contents, rescue-boot configuration, root-account policy or host account/login state is read or staged.
- FIDO2, WebAuthn, security keys, YubiKey-class authenticators, platform authenticators and TPM-backed credential/key protection remain separate later Part 4 gates.
- Existing administrators, root policy, rescue configuration, PAM and SSH configuration are preservation-first.
- UNKNOWN/BLOCKED/UNSUPPORTED fail closed.
- Source ISO remains read-only during analysis/staging.

Test infrastructure remains the consolidated verified `testpack/part4_tests.zip` with fail-fast checkpoint/resume and full seal pass after a successful resume. Manual Stage → Changes → Test → Undo remains available as fallback.

Part 5 is not started.
