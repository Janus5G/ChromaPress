# ChromaPress v1 alpha 16

Alpha 16 stays inside the Applications gate and fixes the two issues found during the on-machine Alpha 15 review.

## Changes panel Undo

- `Test` no longer clears the selected staged change.
- `Undo` therefore remains functional after a change has been tested and marked PASS/WARNING/FAIL.
- Refreshes preserve the selected change where possible.
- Test/Undo are disabled when no change is selected, instead of appearing usable with no target.

## Installed applications: Keep | Remove | Replace

The passive `Preserved` action has been removed from installed application rows.
Every installed desktop launcher now receives a real three-state choice:

`Keep | Remove | Replace`

- **Keep** is the default and directly undoes a staged Remove or Replace.
- **Remove** stages removal.
- **Replace** asks for a replacement repository package and stages one replacement plan.
- If Quick catalogue package ownership is already known, the exact package is stored in the plan.
- If package ownership is not yet known, ChromaPress stores the exact installed `.desktop` launcher as a locator. The later apply/build gate must resolve its owning package and fail closed before any removal or replacement is performed. ChromaPress does not guess a package name.

A replacement is declarative/atomic at this stage: the current application must not be removed unless the replacement can be resolved and the current package can be safely identified and validated.

## Refract Studio bundle

The Alpha 15 raw Python source ZIP recommendation is replaced in Alpha 16 by the packaged Debian application:

`bundled_apps/refract-studio_0.1.0-1_all.deb`

SHA-256:
`9f06a78ab3e75316c00dd71e876313d0d0475066e045de0025c176d3b61b8fdd`

This keeps the recommendation installable as a normal Linux application while runtime installation in the generated image remains a later build-engine verification gate.
