# ChromaPress v1 Alpha 2 — cumulative source/UX patch

This Alpha 2 working tree keeps the Alpha 1 native Qt direction and adds:

- cancelable/resumable official ISO download;
- fresh ISO download starts before checksum lookup/verification;
- explicit status: connect/download/resume/verify/analyze/READY;
- normal-size repository/direct-link/Git dialogs (760×420, resizable);
- simplified Settings with `General` and `Advanced` tabs;
- one user-facing Storage location that derives `build` and `cache` by default;
- OpenAI as the default AI provider;
- model/version dropdown with descriptions/tooltips;
- OpenAI GPT-5.6 Sol/Terra/Luna model choices;
- optional Caffeine Inference Early Access provider entry;
- API key moved to Settings and kept runtime-only (not project/QSettings persistence);
- AI App Studio normal view reduced to provider + model/version; toolchain is under Advanced;
- CPL/CPA status remains visible while the execution bridge is still pending.

The provider model catalogue is intentionally centralized so it can later be refreshed without redesigning AI App Studio.
