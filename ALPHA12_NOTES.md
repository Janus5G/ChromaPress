# ChromaPress v1 alpha 12

Part 2 Applications UX refinement.

- Installed applications with resolved package ownership now show an explicit two-state `Keep | Remove` control.
- `Keep` is selected by default.
- When `Remove` is selected, the removal is staged and `Remove` remains selected.
- Selecting `Keep` again directly undoes the staged removal.
- Applications whose safe removal is not yet resolved now show `Preserved` rather than a disabled/fake Keep button.
- Action column widened for the two-state control.

The same interaction model can later be mirrored for non-installed applications as `Skip | Add`.
