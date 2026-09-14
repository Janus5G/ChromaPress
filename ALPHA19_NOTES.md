# ChromaPress v1 Alpha 19

Part 2 Applications correction after the on-machine Alpha 18 review.

## Corrected

- Application search remains global across all profiles.
- Selecting a different system-use profile now clears any active search text.
- The application tree immediately returns to the newly selected profile's normal prioritised view.
- The checked/darker active-profile indication from Alpha 17 is preserved.
- No package is added, removed or otherwise staged merely by changing profile or clearing Search.

## Intended interaction

1. Select a profile: its own application/recommendation view is shown.
2. Type in Search: results are global across installed and supported available applications.
3. Select another profile while Search contains text: Search is cleared and the newly selected profile view is shown.

This remains Part 2/8. No build-engine, desktop, installer or ChromaLinux-specific behaviour is changed.
