# ChromaPress v1 alpha 14

Applications correction pass following the first on-machine Alpha 13 UI review.

- `Recommended:` rows now physically insert their `Skip` and `Add` buttons into the Action cell.
- Home / Personal no longer lets LibreOffice satisfy the lightweight writing role. AbiWord is recommended instead; LibreOffice is still preserved and shown under `Specialised / Advanced → Full office suites`.
- Everyday essentials and Specialised / Advanced use separate subgroup lists, removing duplicate empty Torrent/Programming/Advanced rows.
- Rebuilding the tree after Add/Remove/Undo now preserves expanded groups, so clicking Remove no longer folds the view closed.
- Description stretches to available width while State and Action stay aligned.

Focused verification in the assembly environment:

- Python compile: PASS
- Core regression tests: 29 PASS
- GUI smoke suite included for the Windows `.venv-win`; it is skipped only when PySide6 is unavailable in the assembly environment.

On-machine acceptance checks before leaving the Applications gate:

1. Expand `Writing & office`; click Remove on an installed removable app. The group must stay expanded and Changes must gain one removal.
2. Click Keep on the staged removal. The removal must disappear from Changes and the group must stay expanded.
3. `Recommended: AbiWord` must show visible `Skip | Add`. Click Add; state becomes `Add staged` and Changes gains one addition. Click Skip; it must undo that addition.
4. LibreOffice must appear only under `Specialised / Advanced → Full office suites` in Home / Personal, not as the everyday writing default.
5. Torrent, Programming and other specialist groups must appear only once, under Specialised / Advanced.
