# ChromaPress Alpha 59

Part 4 gate: **network restrictions** plus an additive automated staged-gate acceptance sweep.

- Network restriction scope is deliberately narrow and truthful: one kiosk account may be prevented from changing NetworkManager network state/system settings through a verified target NetworkManager + polkit mechanism.
- This gate does **not** claim traffic isolation and does not stage firewall rules; firewall traffic rules remain the next separate Part 4 gate.
- Detection uses target-rootfs metadata only: NetworkManager capability, `/etc/polkit-1/rules.d`, the NetworkManager polkit action metadata path, and managed-filename collision detection.
- NetworkManager profiles, polkit rule/policy contents, firewall rules, credentials and Windows/WSL host networking are never read.
- `UNKNOWN` remains fail-closed when the mechanism cannot be verified; existing managed-file collision is `BLOCKED`; `UNSUPPORTED` is never guessed from distro/backend name.
- The plan requires the Alpha 55 dedicated non-admin kiosk-user dependency before apply and preserves network profiles, existing polkit rules, firewall policy and other users.

Acceptance improvement:

- `chromapress_acceptance.py` now runs all discoverable paired Part 4 GUI gate tests in one additional sweep and reports `AUTOMATED_GATE_PASS`, `AUTOMATED_GATE_FAIL` or `AUTOMATED_GATE_SKIP` per Alpha plus `PART4_STAGED_GATES=...` in the console.
- The known manual Stage → Changes → Test → Undo workflow remains untouched and available as fallback. `--skip-staged-sweep` disables only the new sweep if it misbehaves, without rolling back ChromaPress functionality.
- The automated sweep is additive; it does not change source-ISO servicing or gate semantics.

Part 5 is not started.
