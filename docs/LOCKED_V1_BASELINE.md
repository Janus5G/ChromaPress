# ChromaPress — Locked V1 Baseline

This file locks the product direction before implementation expands.

1. ChromaPress is a general Linux image customizer, not a Linux distribution.
2. ChromaLinux remains a separate product.
3. Primary UX target: NTLite-level intuitiveness.
4. First-time-user target: choose/open Ubuntu/Lubuntu, remove 3 apps, generate 2 apps with AI, add 1 app, review, build — without a manual.
5. Native desktop GUI: PySide6/Qt.
6. Linux-only operations run through a restricted WSL backend/helper.
7. No local Flask/web UI as the final product.
8. Two source flows: official distribution download and open existing ISO.
9. Official source downloads use upstream release locations and integrity verification.
10. Existing ISO is referenced directly; no hidden upload copy.
11. Input ISO is always read-only.
12. Unknown/custom content is preserved unless explicitly changed.
13. Capability detection controls what the GUI exposes.
14. Quick / Advanced / Expert are depth levels over the same project/change model.
15. Navigation: Source, Overview, Applications, Components, Files, System, Boot & Hardware, Installer, Desktop, AI App Studio, Changes, Build & Verify.
16. Quick Applications shows human-facing applications, real metadata/icons, version and description.
17. Components holds libraries, runtimes, services, drivers and other technical packages.
18. Application sources: target repository, direct URL, local Linux package/file, Git repository, AI-generated project.
19. Local imports include .deb/.rpm/AppImage and other supported Linux application/package formats.
20. Git projects are cloned/built in isolated unprivileged workspaces before any root integration.
21. Direct URLs are downloaded once, verified where possible, then staged.
22. Application Editor will handle menu/launcher/icon/autostart/defaults/config/wrappers/integration where technically supported.
23. AI App Studio is a first-class main area, not a late optional afterthought.
24. AI provider, endpoint, model and coding toolchain are configurable.
25. API keys are secrets and never enter project files, generated applications, ISO images, manifests or logs.
26. AI-generated source is visible/editable and never a black box.
27. AI can generate new apps and revise existing/imported source.
28. AI generation receives selected target distro/architecture/toolchain context.
29. Generated apps must build/test before Add to ISO is considered verified.
30. Source editor supports project tree, code, diagnostics, diff/build output as the studio expands.
31. Toolchains include Python/PySide6, Qt/C++, C/C++, Rust and CPL/CPA.
32. CPL/CPA is first-class and must integrate the existing Cplex / chromaplex-os / chromaplex-os-compiler work rather than randomly reimplement it.
33. ChromaPress is therefore Windows-GUI + Linux-execution, not a Windows-only application internally.
34. Files/Custom Content uses controlled overlays and explicit PRESERVE / REPLACE / SKIP.
35. System configuration covers users/groups, network, services, locale, policies and security.
36. Boot/Hardware covers kernel, initramfs, boot config, drivers and firmware using distro-native tools.
37. Last viable kernel/boot path is protected.
38. Installer editor generates/validates native Autoinstall/cloud-init, Kickstart/Anaconda, Preseed or detected equivalent.
39. Desktop editor is adapter-driven for KDE/GNOME/LXQt/etc.
40. Installer branding/slideshow is preservation-first.
41. Generic kiosk/immutable/thin-client profiles remain planned capabilities.
42. Security capabilities include FIDO2/WebAuthn/security keys/platform authenticators/TPM-backed protection where supported.
43. Changes pane stays visible and is the source of truth.
44. Each change supports Edit/Test/Undo as implementation reaches that change type.
45. Test means prevalidation of that change, not pretending the final ISO has been verified.
46. Status vocabulary is evidence-based: STAGED/UNVERIFIED/PASS/WARNING/BLOCKED/FAIL.
47. Lifecycle: DETECT → CONFIGURE → STAGE → REVIEW → VALIDATE → APPLY → VERIFY.
48. No image mutation while merely browsing/editing the project.
49. Use the least-invasive servicing method that correctly accomplishes the requested change.
50. Full rootfs/image rebuild happens only when necessary.
51. Build & Verify is the final explicit step.
52. Output verification covers ISO readability, boot metadata, manifests, requested changes, preservation checks and SHA-256.
53. VM boot acceptance is distinct from static ISO verification.
54. Projects store metadata/change plan/references/hashes, not embedded multi-GB ISO copies.
55. Projects must be reproducible against the pinned source hash/version.
56. Presets may be exported/imported and are capability-validated against new releases.
57. Storage is explicit and user-visible.
58. Before a large job, show base size, expected workspace, output, reserve and free space.
59. Build is blocked if the reserve cannot be maintained.
60. Dedicated workspace mount/device must be verified before large writes.
61. Never silently fall back to WSL root for large workspaces.
62. One job = one workspace.
63. SUCCESS/FAILED/CANCELLED cleans large transient data by default.
64. Keep workspace for debugging is opt-in and shows the retained size.
65. Cache manager shows actual sizes and allows targeted deletion.
66. No disk may be filled to zero by ChromaPress.
67. Orphaned workspaces are detected at next start and offered for recover/clean.
68. Diagnostics have a human summary plus technical detail.
69. PASS/FAIL/UNVERIFIED are based on actual evidence, never probability.
70. The user should never need a shell during normal product use.
71. A context-aware help assistant is added after functions/workflows are stable enough to build its knowledge database accurately.
72. Existing useful ISO-engine source is ported selectively; old runtime state, caches and broken web workflow are not reused.
73. Old code is KEEP / PORT / REPLACE / DELETE and deleted only after its needed replacement is verified.
74. No autonomous Codex development loop for ChromaPress.
75. Development proceeds in small functional gates with minimal checks in V1 and broader regression/acceptance before V2.
76. V1 Gate 1: native GUI shell + source flow + direct ISO analysis + Overview + safe project/change model.
77. V1 Gate 2: real Applications catalogue + remove/add + source imports + individual preflight.
78. V1 Gate 3: AI App Studio generation/edit/build/test + CPL toolchain bridge.
79. V1 Gate 4: storage/job/helper engine + actual Apply/Build/Verify.
80. V1 Gate 5: Components/Files/System/Boot/Installer/Desktop capability editors.
81. Before V2: one consolidated regression pass, real Ubuntu/Lubuntu builds, boot acceptance and cleanup/storage acceptance.
82. V2 then expands enterprise distro coverage and hardening rather than repeatedly checking every tiny V1 edit.
