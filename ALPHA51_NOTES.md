# ChromaPress Alpha 51 — Part 4 Networking / NetworkManager / DNS

Alpha 51 continues Part 4 only. Part 5 is not started.

This gate expands the earlier Alpha 43 read-only networking/DNS evidence into structured, capability-driven staged configuration. ChromaPress identifies a supported target-rootfs networking mechanism from read-only SquashFS metadata and reports capability using `SUPPORTED`, `SUPPORTED_WITH_REQUIREMENTS`, `UNSUPPORTED`, `BLOCKED` or `UNKNOWN` semantics.

Implemented staged intents where the analyzed image supports them:

- DHCP / automatic IPv4.
- Static IPv4 with prefix and gateway.
- IPv4 DNS servers.
- Credential-free managed NetworkManager Ethernet profile creation.
- Existing NetworkManager profile autoconnect intent when an exact `.nmconnection` filename is verified from metadata.

Quick mode exposes only preservation, DNS and DHCP. Advanced/Expert exposes static IPv4 and NetworkManager profile controls when the analyzed capability permits them. IPv6 is intentionally blocked in Alpha 51 and no IPv6 controls are exposed.

Preservation and privacy rules:

- Selected source ISO stays read-only during analysis and staging.
- Windows/WSL host interfaces, NetworkManager, DNS and routes are never used as target evidence or fallback.
- Existing NetworkManager profile contents and netplan YAML are not read.
- Wi-Fi/VPN credentials and other credential secrets are not read or staged.
- Existing profiles, unrelated routes and the existing hostname are preserved unless a later explicit gate targets them.
- Generated backend syntax and target paths must be re-verified before any future apply.

The acceptance runner adds `P4-REAL-STAGED-NETWORK-CONFIG`, which takes the capability evidence from the analyzed target ISO, builds an actual Alpha 51 staged DHCP plan in memory, and runs the same preflight validation used by the Changes/Test workflow. This is separate from the existing read-only detection check.
