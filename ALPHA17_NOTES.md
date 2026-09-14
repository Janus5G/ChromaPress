# ChromaPress v1 Alpha 17

Part 2 Applications correction following the Alpha 16 Gaming / Team / Education review.

## Fixed

- Search is global regardless of the selected system-use profile.
- Search covers both installed applications and supported available/recommended applications.
- Searching `MangoHud`, `nvtop`, `Speedtest CLI`, or `GLMark2` can reveal the corresponding available recommendation even if another profile is selected.
- Duplicate Add rows are suppressed when the exact package is already installed.
- A recommendation found through global search keeps its real originating profile in the staged change rather than being mislabeled as the currently selected profile.
- The active system-use button has a persistent slightly darker checked state so the selected profile remains obvious.

## Ubuntu 26.04 Gaming / Team / Education repository mapping

- MangoHud -> `mangohud` -> Universe
- nvtop -> `nvtop` -> Multiverse
- Speedtest CLI -> `speedtest-cli` -> Universe
- GLMark2 -> `glmark2-x11` -> Universe

These mappings describe Ubuntu/Lubuntu 26.04 repository availability. Apply/build must still verify that the required repository component is enabled/resolvable for the selected image and fail closed otherwise.
