# Alpha 50 — Part 4 Users / Groups / Password Policy gate

Alpha 50 expands the existing identity gate only. It does not start Part 5 or add networking, SELinux, kiosk, TPM or FIDO2 work.

- Reads target-ISO `/etc/passwd`, `/etc/group` and non-secret `/etc/login.defs` password-aging defaults read-only from verified SquashFS layers.
- Never reads `/etc/shadow` and never uses or modifies Windows/WSL host account databases as a substitute for target-image servicing.
- Reports capability states truthfully with `SUPPORTED`, `SUPPORTED_WITH_REQUIREMENTS`, `UNSUPPORTED`, `BLOCKED` or `UNKNOWN`; missing detection remains `UNKNOWN`.
- Quick mode exposes preservation-first normal user operations. Advanced/Expert exposes UID/GID, supplementary groups, group creation and password-aging planning when target-rootfs capability is verified.
- Supports staged default-user, create-user, modify-user and create-group intents. Existing users/groups/configuration are preserved unless explicitly targeted.
- Passwords, hashes, tokens and recovery secrets are never accepted into the staged account plan. Password assignment remains deferred to a later secure verified apply gate.
- The separate autologin policy is preserved by this gate; the existing Alpha 39 autologin gate remains unchanged.
- Acceptance now contains a dedicated `P4-REAL-ROOTFS-USERS-GROUPS-PASSWORD` check so Part 4 automation cannot silently omit the Alpha 50 evidence schema.
