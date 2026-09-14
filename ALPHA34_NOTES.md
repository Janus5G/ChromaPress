# ChromaPress v1 Alpha 34

Part 3 incremental gate: boot identity and metadata planning.

- Adds a staging-only Boot identity / metadata plan.
- Uses only explicitly parsed boot entries and boot configuration sources.
- Supports a reviewed boot-entry label change, moving one detected entry to first position, and a staged ISO Volume ID change.
- Preserves El Torito/hybrid boot records and all unselected boot entries.
- Requires boot-catalog re-verification before any later apply.
- Plans are source-SHA-256 locked and fail closed if source evidence changes.
- The selected source ISO remains read-only; Alpha 34 performs no boot-record or ISO write.
