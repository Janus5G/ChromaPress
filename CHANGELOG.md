# Changelog

This file summarizes the major public-development milestones of ChromaPress.

The detailed alpha-by-alpha development record that originally lived in the README is preserved in `docs/DEVELOPMENT_HISTORY.md`.

## 1.0.0a72 — Release candidate

- Completed the Part 8 cross-distro hardening and acceptance baseline.
- Preserved explicit static-vs-runtime verification boundaries.
- Added/finished target-image component browsing and release polish.
- Completed Danish/English localization work.
- Added final ChromaPress branding, application icons and About experience.
- Kept the selected source ISO read-only during analysis/staging.
- Final release gate updated to the current UI/version contract.

## 1.0.0a70 — AI App Studio

- Completed the consolidated AI App Studio workflow.
- Added target-Linux context for generated projects.
- Kept API credentials session-only.
- Added manifest/path/credential validation and explicit human-review staging gates.
- Kept generated code reviewable rather than automatically trusted/executed.

## 1.0.0a69 — Installer and Desktop

- Completed structured native installer profiles.
- Added reviewed Files/Custom Content staging.
- Added desktop-native customization and kiosk/thin-client planning.

## 1.0.0a63–a68 — Security/authenticator policy gates

- Added FIDO2, WebAuthn, external security-key, YubiKey-class, platform-authenticator and TPM-related policy gates.
- Preserved the distinction between package/static evidence and actual physical/runtime hardware verification.

## 1.0.0a36–a62 — System Configuration

- Added preservation-first System Configuration evidence and staged policies.
- Added account, hostname, autologin, networking/DNS, services, timers, targets, firewall, AppArmor, sysctl, persistence and recovery planning.
- Kept credentials/secrets outside analysis/staged project data.

## 1.0.0a25–a34 — Boot, hardware and rootfs planning

- Added read-only Boot & Hardware analysis.
- Added boot configuration, firmware/driver, SquashFS, immutable/volatile runtime, persistence and boot-identity planning.
- Maintained source-hash locking and source-ISO preservation.

## 1.0.0a15–a24 — Application profiles and education

- Expanded role-based application profiles.
- Added global application search and installed-app controls.
- Added School / Education as a first-class profile.
- Iterated reviewed ChromaLearn bundling and evaluation material.

## 1.0.0a3–a14 — Workbench foundation

- Established the native PySide6 workbench.
- Added source selection/download, WSL-based analysis, Overview and Applications.
- Added the persistent Changes panel, Test/Undo flow and image-plan review.
- Established the preservation-first staging model.
