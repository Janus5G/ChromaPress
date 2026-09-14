# ChromaPress Alpha 60

Part 4 gate: **firewall rules**.

- Adds one narrow traffic-rule capability: stage a single explicit inbound TCP-port deny rule.
- Uses only verified target-rootfs firewall backend and additive command-path metadata.
- UFW and firewalld are supported only when their target command path is verified; nftables remains `UNKNOWN` until a preservation-safe persistent additive mechanism is verified.
- Existing firewall rules, ports/services policy, application profiles, secrets and host firewall state are not read during analysis.
- Existing/default/unrelated firewall policy is preserved. Duplicate/conflict detection, backend state and command presence must be re-verified before apply.
- `UNKNOWN`, `BLOCKED` and `UNSUPPORTED` fail closed.
- Source ISO remains read-only during analysis/staging.
- The automated Part 4 staged-gate sweep remains the default acceptance path, with `--skip-staged-sweep` retaining the established manual fallback.

Part 5 is not started.
