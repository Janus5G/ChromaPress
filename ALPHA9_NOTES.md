# ChromaPress v1 Alpha 9

Focused Part 2 usability/performance patch.

- Reuses the small application-catalog JSON directly from the configured Windows cache before starting WSL.
- Makes xorriso report_lba parsing robust and prefers direct SquashFS offset reads to avoid multi-GB fallback extraction.
- Prevents duplicate identical staged changes, fixing the apparent Undo problem caused by duplicate Remove clicks.
- Gives application/category/suite rows more breathing room and reserves a 24 px icon slot.
- Uses neutral local Qt icons only as placeholders in this alpha; real ISO application icons remain required and will be loaded progressively after the speed path is stable so icons never block first display.
