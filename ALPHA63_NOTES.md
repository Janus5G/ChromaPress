# ChromaPress Alpha 63

Part 4 gate: **FIDO2 policy**.

- Adds one bounded policy intent: require FIDO2 as an additional second factor for the Alpha 62 recovery administrator.
- Capability is derived only from target package-manifest evidence that positively verifies a PAM FIDO2/U2F module plus libfido2.
- Distro family, Windows/WSL host packages, USB/HID devices and host authenticator state are never substituted for target evidence.
- PAM contents are not read or changed during analysis/staging.
- No authenticator is enumerated or enrolled; no credential ID, credential secret or token material is read/staged.
- Existing primary authentication remains preserved by this gate; actual PAM integration must be verified before apply.
- WebAuthn, physical security-key enrollment, YubiKey-class behavior, platform authenticators and TPM-backed credential/key protection remain separate later Part 4 gates.
- UNKNOWN/BLOCKED/UNSUPPORTED fail closed.
- Source ISO remains read-only during analysis/staging.

Test infrastructure remains the consolidated verified `testpack/part4_tests.zip` with fail-fast checkpoint/resume and full seal pass after a successful resume. Manual Stage → Changes → Test → Undo remains available as fallback.

Part 5 is not started.
