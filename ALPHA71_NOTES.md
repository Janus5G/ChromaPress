# ChromaPress v1 Alpha 71 — Part 7 Complete

Alpha 71 completes Part 7 as one consolidated batch: reusable inspectable customization profiles, source/change-plan comparison, deterministic profile fingerprints, profile import for matching source images, capability-backed production presets, reviewed Expert hooks, production preflight/build-plan staging, output naming/location/compression/verification policy, and diagnostics-bundle intent.

Safety remains preservation-first. Profiles and production plans exclude secret material. Expert hooks are SHA-256 locked, require explicit human review, may execute only in an isolated WSL build workspace, may not bypass ChromaPress preflight, and may not mutate the selected source ISO. Production presets are exposed only when their underlying staged capabilities actually exist. The Part 7 production plan is declarative and staged; it does not silently start ISO mutation.

Part 7 has its own consolidated `testpack/part7_tests.zip`. Acceptance runs Parts 4, 5, 6 and 7 in sequence and reports Part 7 staged-gate automation separately.
