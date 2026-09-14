# ChromaPress Alpha 58

Part 4 gate: **service lockdown**.

Alpha 58 adds a capability-driven, preservation-first staged plan for disabling and masking one explicitly selected, verified, non-protected target systemd service. Detection is target-rootfs-only and collects immediate `.service` filenames without reading unit contents, enablement-link targets, environment files, credentials or host/WSL service state.

Critical/core display, network-management and systemd units are excluded from the selectable set by ChromaPress safety policy. Unknown/unverified target state fails closed. Source ISO bytes remain unchanged during analysis and staging.

Out of scope: network restrictions, firewall redesign, persistence/recovery, FIDO2/WebAuthn/security keys, TPM and Part 5.
