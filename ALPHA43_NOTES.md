# ChromaPress Alpha 43

Part 4 incremental gate: networking / DNS.

- Preserves all verified Alpha 37–42 Part 4 behavior.
- Adds read-only network-backend/resolver path evidence from safe rootfs metadata only.
- Does not read NetworkManager connection profiles, netplan YAML, Wi-Fi/VPN credentials or resolver contents.
- Stages only explicit DNS-server IP-address intent.
- Preserves interfaces, DHCP/static addressing, routes and existing connection profiles.
- Requires backend-specific mapping verification before any future apply.
- Extends Part 4 source-hash guarding to timezone and networking/DNS plans.
- Source ISO remains read-only.
