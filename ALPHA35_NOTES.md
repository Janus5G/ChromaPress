# ChromaPress v1 Alpha 35

Part 4/8 begins with evidence-only installer analysis.

- Replaces the Installer placeholder with a real read-only Installer page.
- Detects installer family only from explicit ISO paths and package-manifest evidence.
- Uses package manifests to detect installer payloads that live inside SquashFS, including Calamares, Subiquity, Anaconda, Debian Installer and Ubiquity families.
- Shows explicit installer package evidence, ISO-level configuration paths, detected capability and source SHA-256.
- Unknown installer evidence fails closed: configuration editing remains blocked rather than guessed.
- The selected ISO remains read-only; Alpha 35 exposes no installer mutation controls.

> Classification correction recorded in Alpha 36: according to the authoritative eight-part plan, System Configuration is Part 4 and Installer & Desktop is Part 5. The Alpha 35 read-only Installer analyzer is preserved as early Part 5 preparation.
