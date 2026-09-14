# ChromaPress v1 Alpha 5

Part 1 Workbench Foundation is now PASS on the user's machine.

Alpha 5 begins Part 2 — Software & Components.

Implemented in this gate:
- The Applications page automatically reads user-facing `.desktop` applications from the selected ISO, not from the WSL host.
- Layered Lubuntu/Ubuntu Casper SquashFS metadata is processed base -> standard -> standard.live.
- Only application/package metadata is extracted into the explicitly configured ChromaPress workspace; transient catalogue data is removed automatically.
- A conservative storage preflight keeps 4 GiB transient headroom plus the configured safety reserve.
- Quick Applications view shows application name, installed version when resolved, description, installed state and a Remove action when package ownership is known.
- Search field and Reload Applications action added.
- Remove is staged into the existing Changes pane; no image mutation happens during browsing.
- Technical dependencies remain out of Quick view.

Not yet in this gate:
- icons
- selected-image online repository refresh / available package catalogue
- dependency/protected-package validation for removal
- actual package mutation
- Components full technical catalogue
