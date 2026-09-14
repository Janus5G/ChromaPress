# ChromaPress v1 Alpha 72 Fix 1 — release polish

This fix keeps the approved `1.0.0a72` source baseline and addresses the final visible workbench issues found during manual inspection after all eight Parts passed Windows acceptance.

- Replaces the Components placeholder with a real target-image component browser backed by package-manifest evidence from the selected ISO.
- Installed component inventory never uses Windows/WSL host packages as substitute data.
- Components are grouped into restrained technical categories; low-level libraries can be hidden in the normal view and exposed with **All installed components**.
- Core/kernel/package-management/boot packages are conservatively protected from direct removal; other removals are staged for normal dependency/preflight review.
- Adds a ChromaPress application/window icon using the bundled CP asset.
- Adds an **About** dialog with version, `Copyright © 2026 Janus Rokkjær`, and the ChromaPress Proprietary License v1.0.
- Adds the repository `LICENSE` file and bundles the identical license text with the installed application.
- ChromaPress is no longer marked MIT: official compiled use is licensed while modification and unauthorized redistribution are prohibited; authorized ChromaLearn education deployments and approved hardware bundles are explicit exceptions.
- Replaces the stale status-bar `v1 alpha 37` label with the actual package version.

The final standalone Windows executable still needs to be rebuilt from the approved/fixed source after Windows GUI acceptance.
