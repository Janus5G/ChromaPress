# ChromaPress Alpha 42

Part 4 incremental gate: timezone.

- Preserves all verified Alpha 37–41 Part 4 behavior.
- Adds read-only timezone evidence from `/etc/timezone`, `/etc/default/timezone`, or `/etc/localtime` metadata.
- Never reads binary `/etc/localtime` timezone contents and never reads credential secrets.
- Stages only an IANA-style target timezone such as `Europe/Copenhagen`.
- Target zoneinfo availability must be verified again before any future apply step.
- Preserves RTC/hardware-clock policy and unrelated regional settings.
- Source ISO remains read-only.
