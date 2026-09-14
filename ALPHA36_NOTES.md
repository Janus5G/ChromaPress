# ChromaPress v1 Alpha 36

Alpha 36 returns development to the authoritative eight-part plan and starts the actual **Part 4/8 — System Configuration** gate.

- Replaces the `System` placeholder with a real read-only System Configuration page.
- Shows only package-manifest-backed evidence for identity/accounts, locale/time, networking/DNS, services/startup, firewall, AppArmor/SELinux, sysctl, FIDO2/security-key and TPM-related capabilities.
- Explicitly lists configuration that still requires rootfs-level verification before any edit can be staged: users/groups/default user, hostname/machine identity, active locale/timezone, network profiles/DNS, enabled services/timers/targets, firewall/MAC/sysctl policy, kiosk/persistence/recovery policy and authenticator policy.
- No account, password, service, network, firewall or security setting is inferred merely from package presence.
- Secrets/passwords are neither requested nor logged in this read-only gate.
- The selected ISO remains read-only; Alpha 36 exposes no System mutation controls.
- The Alpha 35 Installer analyzer is preserved, but is correctly classified as early read-only **Part 5 — Installer & Desktop** evidence rather than Part 4.
