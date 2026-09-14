# ChromaPress Alpha 69 — Part 5 Complete

Alpha 69 completes the planned **Part 5 — Installer & Desktop** work in one release and adds a separate consolidated `testpack/part5_tests.zip`. Part 4 remains frozen as the approved Alpha 68 baseline and its own consolidated regression pack is still run first.

## Structured installer profiles

The Installer page now provides structured, credential-free staging for the native installer families explicitly required by the plan when target evidence verifies them:

- Anaconda/Kickstart for RHEL/Rocky/Alma/Oracle-class images.
- Subiquity Autoinstall/cloud-init for Ubuntu LTS images.
- Debian Installer/Preseed for Debian Stable when positively detected.

Installer family is never inferred from a distro label. Calamares/Ubiquity are preserved but this gate reports them as unsupported rather than pretending a native generator exists. The staged template contains only `${CHROMAPRESS_PASSWORD_HASH}`; real credentials are never read or stored. Native installer-tool/schema validation and secure credential injection remain mandatory verified-apply requirements. Advanced/Expert exposes the explicit whole-disk partitioning intent only behind a destructive confirmation.

## Files / Custom Content

The Files page accepts user-selected files, multiple files, folders, drag/drop and `.tar.gz`/`.tgz`. Default-user content is staged under `/etc/skel/`; Advanced system overlays use controlled absolute target paths. Archive and folder inspection rejects traversal, unsafe absolute paths, escaping symlinks/hardlinks and special archive nodes. Review shows target paths, ownership/permissions metadata and conflict policy. `PRESERVE`, `SKIP` and explicitly confirmed `REPLACE` are supported; unknown source-image content is never silently overwritten.

## Desktop-native customization

Desktop controls are exposed only when one supported desktop family is positively identified from the target package manifest. KDE Plasma, GNOME, LXQt, XFCE, Cinnamon and MATE have explicit native-adapter mappings. Multiple desktops are `BLOCKED` rather than guessed; headless/unverified images stay `UNKNOWN`. Staged controls include the planned wallpaper/theme/icons/fonts/panels/menus/shortcuts/favorites/desktop icons/autostart/default applications/MIME/display-manager/login/default-layout intents, with target-native re-verification required before apply.

## Generic kiosk / thin-client staging

Kiosk modes are derived only from verified desktop/Weston/browser package evidence. ChromaPress can stage full/restricted desktop, minimal Wayland/Weston, browser kiosk and custom-application kiosk intents where the target evidence supports them. Browser URLs are explicit HTTP(S) values; application targets are safe absolute target-system paths. Fullscreen/autostart/restricted-session controls and controlled recovery escape are reviewed. No website or provider is hard-coded and runtime VM/session validation remains mandatory.

## Consolidated Part 5 tests

`chromapress_testpack.py --part 5` verifies `testpack/part5_tests.zip`, stops at the first failure, persists a checkpoint outside the project source, resumes from that failure on the next identical run, then performs a complete seal pass. The normal acceptance command through Part 5 runs the approved Part 4 regression pack first, then the Part 5 pack, and reports `PART4_*` and `PART5_*` status separately. The established manual Stage → Changes → Test → Undo path remains available as fallback.


## Alpha 69 Windows compatibility fix 1

- Restores the Alpha 35 read-only installer evidence status contract when no Part 5 capability object is present.
- Evidence-backed legacy installer analysis again reports `READ-ONLY PASS`; unknown installer evidence remains `BLOCKED`.
- Part 5 native installer editing remains gated exclusively by verified `part5_installer_evidence`; no capability is inferred or broadened.
- Version remains `1.0.0a69` because this is a regression fix to the same Part 5 release, not a new planned gate.

## Fix 2 — Windows Part 5 test-pack modal timeout
- Product Part 5 behavior is unchanged.
- The consolidated Part 5 GUI tests now suppress both QMessageBox.warning and QMessageBox.information during offscreen automation. The latter was the Windows-only 900-second hang after Changes -> Test.
- The inner pytest subprocess now fails closed after 120 seconds, well before the outer acceptance timeout, so a future GUI deadlock produces a normal test-pack report and cleanup instead of stranding the runner.
- A Part 5 legacy hash manifest accepts only the exact three generated test files from Alpha 69 Fix 1, allowing safe cleanup/replacement if the previous timed-out run left its temporary tests directory behind. Unknown or edited loose tests remain BLOCKED/preserved.

### Fix 3 — Part-scoped consolidated test collection

The consolidated runner now treats each Part as an independent test scope. A Part 4 run validates, extracts, collects and executes only paths owned by `part4_manifest.json`; legitimate Part 5 or later tests already present under `tests/` are preserved and excluded from the active Part 4 pytest command. The same rule applies to every Part. Only a collision on a path owned by the active Part can block that Part's preparation. Cleanup removes only verified files owned by the active Part and never deletes unrelated tests or assets.

This fixes Windows acceptance after an interrupted Part 5 run left its generated tests under `tests/`. The fix is covered by the consolidated Part 5 regression pack.
