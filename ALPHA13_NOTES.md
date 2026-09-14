# ChromaPress v1 alpha 13

Home / Personal repository-backed application recommendations.

- Installed applications keep the Alpha 12 `Keep | Remove` interaction.
- Missing everyday roles on validated Ubuntu/Lubuntu 26.04 targets now show concrete `Recommended:` rows.
- Recommendations use a real `Skip | Add` two-state control.
- `Skip` is the no-change/default state; selecting `Add` stages a `PACKAGE_REPOSITORY` change visibly in Changes.
- If an addition is staged, selecting `Skip` again directly undoes it.
- Recommendations are never silently installed.
- A recommendation is only shown if the corresponding role is missing after staged removals are taken into account.
- Alpha 13 recommendation catalogue is intentionally limited to Ubuntu/Lubuntu 26.04 rather than guessing package names for other distributions.

Validated Home / Personal fallbacks:

- Browser: Falkon (`falkon`)
- Email: Evolution (`evolution`)
- Writing: AbiWord (`abiword`)
- Simple image editing: KolourPaint (`kolourpaint`)
- Video: Haruna (`haruna`)
- Music: Audacious (`audacious`)
- E-books: Foliate (`foliate`)
- Podcasts: gPodder (`gpodder`)
- Casual games: Aisleriot (`aisleriot`)
- File manager fallback: PCManFM-Qt (`pcmanfm-qt`)

Repository additions still pass through the existing Changes/preflight flow before any later apply/build stage.
