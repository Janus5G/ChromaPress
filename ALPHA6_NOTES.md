# ChromaPress v1 Alpha 6

Part 2 catalogue fix and system-scenario foundation.

- Fixes application-catalog extraction on Windows/WSL workspaces by disabling SquashFS xattr restoration for metadata-only extraction. This avoids `trusted.overlay.origin` failures on DrvFS/NTFS while preserving the read-only source image.
- Applications now requires an intended system-use scenario before catalogue loading/prioritisation.
- Scenarios mirror the previously locked user/role scenario principles:
  - Personal / Home
  - Office / Business
  - Development / Engineering
  - Production / Industrial
  - Gaming / Education / Team
  - Custom
- Scenario selection is saved in `.chromapress` projects and passed into AI App Studio target context.
- Quick view prioritises relevant applications; `Show all applications` always exposes the complete detected catalogue.
