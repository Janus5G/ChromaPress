# ChromaPress v1 alpha 7

Part 2 speed/safety iteration.

- Applications catalogue no longer scans/extracts `var/lib/dpkg/info` during Quick load.
- Avoids layered-image overlay whiteout/device-node extraction on NTFS.
- Fast path uses xorriso LBA + `unsquashfs -offset` to read SquashFS directly inside the ISO without creating multi-GB layer copies.
- Safe fallback still uses the configured workspace if `-offset` is unavailable.
- Small application catalogue JSON is cached by analyzed ISO SHA-256.
- Catalogue prefetch starts after image analysis even before scenario selection; scenario selection then filters instantly.
- Home / Personal is explicitly a mix of internet/communication, office/documents, media, everyday utilities and standard games.
- Package ownership is deliberately conservative in Quick load; removal remains unavailable unless an exact package match is known.
