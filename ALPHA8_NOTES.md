# ChromaPress v1 alpha 8

Part 2 usability/performance refinement.

- Applications Quick view is now grouped into collapsible human-facing sections.
- LibreOffice is presented as one suite with expandable components.
- Internet, Office, Games, Media, Development, System/Utilities and Other are compact category groups.
- Category ordering follows the selected system scenario.
- Search expands matching groups; normal view starts collapsed for overview.
- Application metadata extraction no longer extracts unused AppStream directories.
- Removed the full SquashFS listing pass before desktop-entry extraction.
- Rootfs LBA extents are queried in one xorriso session instead of one ISO load per layer.
- Package manifests are extracted in one xorriso session.
- Catalogue cache schema bumped to 3.
