# ChromaPress v1 Alpha 64

Part 4 gate: **WebAuthn policy**.

- Adds one bounded policy intent: allow browser-mediated WebAuthn recovery workflows for the verified Alpha 62 recovery administrator.
- Capability derives only from target package-manifest evidence identifying an allowlisted browser product family; distro family or host software is never substituted.
- Actual WebAuthn runtime support, relying-party/origin compatibility and authenticator availability are deliberately not claimed at analysis/staging time.
- Browser/RP/origin configuration, USB/HID/authenticator state, credential IDs/secrets and enrollment are not read or staged.
- Existing primary authentication is preserved.
- Security keys, YubiKey-class authenticators, platform authenticators and TPM remain later dedicated Part 4 gates.
- The Part 4 consolidated fail-fast/resume test pack remains the only packaged test suite.
