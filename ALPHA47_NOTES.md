# Alpha 47 — Part 4 firewall gate

- Adds read-only rootfs firewall backend evidence for UFW, firewalld or nftables.
- Reads path metadata only; firewall rules, ports/services policy, application profiles and secrets are not read.
- Adds a preservation-first staging-only enable/disable firewall plan.
- Requires backend/apply verification before any later apply step.
- Extends source-SHA guard, acceptance coverage and Test/Undo flow for the new plan.
- Preserves all previously approved Alpha 37–46 gates.
