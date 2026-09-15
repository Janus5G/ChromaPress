# ChromaPress

**Current release candidate:** `1.0.0a72`
**License:** MIT
**Platforms:** Windows 11 + WSL2, and native Debian/Ubuntu package

Windows uses WSL2 for the Linux-native image engine. The `.deb` build runs that same
engine directly on Linux. Official release builds are produced by the included GitHub
Actions workflow or the scripts in `packaging/`.

Programs and ISO images created with ChromaPress are user output. AI App Studio does not
automatically stamp deployable output with ChromaPress branding, telemetry identifiers,
shared ChromaPress runtime stubs or the internal `chromapress-app.json` review manifest.


## Alpha 72 — final release gate

The approved Alpha 72 eight-Part baseline is unchanged. The final release-candidate polish uses the **MIT License**, keeps `Copyright (c) 2026 Janus Rokkjær`, adds the ChromaPress icon/About/Share experience, and preserves the target-image-backed Components view. Programs and ISO images created with ChromaPress are ordinary user output; ChromaPress adds no automatic branding or runtime fingerprint to AI-generated applications.


**Alpha 72 completes Part 8 — Cross-Distro Hardening & Acceptance.** ChromaPress now has the locked distro-priority matrix, target `/etc/os-release` evidence, fail-closed cross-distro acceptance records, explicit static-vs-runtime verification boundaries, and inspectable diagnostics export. Analysis alone never marks a distro `VERIFIED`; real rebuild/boot/install/live-session evidence remains required where applicable. Part 8 has its own consolidated `testpack/part8_tests.zip`. See `ALPHA72_NOTES.md`.

# Alpha 69 — Part 5 Installer & Desktop complete

Alpha 69 completes Part 5 in one batch: structured native installer profiles (Kickstart, Ubuntu Autoinstall/cloud-init and Debian Preseed when positively verified), reviewed Files/Custom Content staging, desktop-native customization, and generic kiosk/thin-client staging. Part 5 has its own consolidated `testpack/part5_tests.zip`; the normal acceptance runner executes the approved Part 4 regression pack first and then Part 5. See `ALPHA69_NOTES.md`.

Windows acceptance through Part 5:

```powershell
.\.venv-win\Scripts\python.exe chromapress_acceptance.py --through 5 --iso "E:\Custom linux builder\ISO\lubuntu-26.04-desktop-amd64.iso"
```

Alpha 68 completes the planned Part 4 System Configuration sequence. Alpha 65–68 add generic external security-key policy, YubiKey-class policy, a fail-closed platform-authenticator gate, and TPM-backed recovery-key protection. All four remain evidence-driven and preservation-first: physical authenticators, biometrics and TPM hardware are never inferred from package metadata, and runtime/enrollment/key operations remain deferred to verified apply/use.

## Alpha 62 — Part 4 administrator/recovery policy + consolidated Part 4 test package

Alpha 62 adds a narrow administrator/recovery policy gate. A recovery administrator must be non-root, separate from the kiosk role and explicit autologin account, and either already be a verified target administrator or explicitly depend on the Alpha 50 administrator-account gate before apply. Alpha 62 does not read or stage passwords, recovery secrets, PAM/SSH contents, rescue-boot/root policy or authentication factors; FIDO2/WebAuthn/security-key/platform-authenticator/TPM work remains in later dedicated gates.

Part 4 tests remain one verified `testpack/part4_tests.zip` rather than dozens of loose test files. `chromapress_testpack.py` stops on the first failure, stores a checkpoint outside the source tree, resumes from that failed test on the next identical run, and performs a complete seal pass after the resumed run succeeds. `--restart-testpack` forces a clean run from the beginning; the established manual Stage → Changes → Test → Undo workflow remains available as fallback. Future Parts 5–8 receive their own separate consolidated test packages.

## Alpha 61 — Part 4 persistence policy

Alpha 61 added the kiosk persistence-policy gate. The policy can require a volatile kiosk runtime or controlled persistence for explicit kiosk-home subdirectories, while all OverlayFS/tmpfs/volume/mount/initramfs mechanics remain delegated to the existing Part 3 model. Existing persistence configuration and persistent data are not read or overwritten during analysis/staging.

## Alpha 51 — Part 4 Networking / NetworkManager / DNS staged configuration

Alpha 51 expands the earlier networking/DNS detection gate into capability-driven staged configuration for verified target-ISO backends. Quick mode exposes safe DHCP/DNS choices; Advanced/Expert adds static IPv4 and NetworkManager profile controls when supported. IPv6 remains blocked at this gate. Existing profile contents, netplan YAML, Wi-Fi/VPN credentials and Windows/WSL host networking are never used as configuration evidence or fallback. See `ALPHA51_NOTES.md`.

## Alpha 43 — staged networking / DNS planning

Part 4 now adds a narrow read-only networking/DNS evidence gate and staging-only DNS-server plan. ChromaPress verifies only safe backend/resolver path metadata and deliberately does not inspect NetworkManager connection profiles, netplan YAML or Wi-Fi/VPN credentials. Existing interfaces, DHCP/static addressing, routes and connection profiles are preserved; backend-specific apply mapping must be verified again before any future apply. The selected ISO remains read-only. See `ALPHA43_NOTES.md`.

## Alpha 42 — staged timezone planning

Part 4 now adds a narrow read-only timezone evidence gate and staging-only timezone plan. Target zoneinfo availability must be verified again before any future apply, while RTC/hardware-clock policy and unrelated regional settings are preserved. The selected ISO remains read-only. See `ALPHA42_NOTES.md`.

## Alpha 41 — staged keyboard-layout planning

Part 4 now adds a narrow read-only keyboard evidence gate and staging-only primary-layout plan. Existing keyboard model, variant and options are preserved, and target-layout availability must be verified again before any future apply. The selected ISO remains read-only. See `ALPHA41_NOTES.md`.

## Alpha 28 — staged kernel/initramfs safety planning

Part 3 now adds source-hash-locked, staging-only initramfs regeneration planning with mandatory last-viable-kernel protection. The selected ISO remains read-only; no kernel/rootfs writes occur in Alpha 28. See `ALPHA28_NOTES.md`.

## Alpha 27 — staging-only boot configuration planning

Part 3 now allows a reviewed boot configuration plan to be staged without modifying the selected ISO. The user may choose an explicitly parsed boot entry, a boot timeout, and optional kernel arguments to append. The plan is locked to the analyzed source SHA-256 and explicit boot configuration evidence, then enters the normal Changes/Test/Undo workflow. Alpha 27 still performs no boot, kernel, initramfs, firmware, driver or ISO writes. See `ALPHA27_NOTES.md`.

## Alpha 26 — Part 3 verified boot-configuration evidence

Part 3 remains read-only, but the inspection is deeper. ChromaPress now parses explicit bootloader configuration declarations for boot entries, default/timeout values and kernel command lines, reports El Torito catalog evidence from xorriso even when the catalog is not visible as a normal ISO file, and shows manifest-backed kernel/firmware/driver package hints. No boot, kernel, initramfs, firmware or driver changes are applied in Alpha 26. See `ALPHA26_NOTES.md`.

## Alpha 25 — Part 3 read-only Boot, Kernel & Hardware analysis

Part 3 starts without mutation. `Boot & Hardware` now reports the selected ISO's detected BIOS/UEFI, El Torito/hybrid evidence, bootloader family, boot configuration files, EFI images, kernel/initramfs images and SquashFS layers. Compression metadata is shown where it can be verified read-only. Alpha 25 exposes no boot/kernel/firmware write controls; the source ISO remains untouched. See `ALPHA25_NOTES.md`.

## Alpha 24 — ChromaLearn 0.4.5 + School Evaluation Pack

`School / Education` and `Education & Learning` remain unchanged. This build replaces the bundled ChromaLearn 0.4.4 package with the verified `ChromaLearn AI 0.4.5` Debian package and pins SHA-256 `024374666992d83df7ae6c9b0f488973e896beec80aeff18c997336d7dbe9fbc`.

The verified `ChromaLearn Skoleevalueringspakke v1.2.1 DA` follows ChromaLearn as linked school/evaluation documentation, pinned to SHA-256 `9fec49879412c056991e123c06d89b3ce99f64eff3ca19718891333fca6e67eb`. It is documentation, not a separate application and not a compliance certificate. ChromaLearn remains explicit `Skip | Add`; nothing is silently installed.

## Alpha 23 — ChromaLearn 0.4.4 reviewed and reintroduced

`School / Education` remains a first-class profile. The withdrawn ChromaLearn 0.3.x line is not restored.
This build bundles the reviewed `ChromaLearn AI 0.4.4` Debian package as an explicit `Skip | Add` recommendation under `Education & Learning`.

The bundle is pinned to SHA-256 `9e1e65157e83a0ae1458701ff650a50446bfd247a74f7cdee2a490214cb473c5`. ChromaPress does not claim that bundling an application makes a school deployment legally compliant; the school's deployment, inference provider, agreements, policies and operational controls remain separate evaluation responsibilities.

## Alpha 21 — ChromaLearn temporarily withdrawn

The `School / Education` profile remains part of ChromaPress, but the bundled `ChromaLearn AI 0.3.0` package and recommendation have been removed from the current build. A replacement must not be bundled again until its child/privacy logging and data-retention design has completed the required legal/compliance review. ChromaPress does not install or expose the withdrawn package as an available recommendation.

## Alpha 20

Selected profile recommendations now open automatically so users can see suggested applications without expanding folders first.

# ChromaPress v1 alpha 20

This is the clean native-desktop restart of ChromaPress.

The design goal is NTLite-like ease of use for Linux images: a first-time user should be able to choose/open a Linux image, remove applications, add an application, create applications with AI, review changes, and proceed toward Build & Verify without needing a shell.

## Architecture

- **Windows desktop UI:** PySide6 / Qt.
- **Linux execution backend:** Ubuntu under WSL2.
- **No local web server and no ISO upload step.** Existing ISO files are referenced directly and remain read-only.
- **Declarative changes:** the GUI stages changes; heavy image mutation is performed later by the Linux engine/helper.
- **No secrets in projects:** AI API keys are runtime-only in this alpha and are not written to `.chromapress` project files.

## Alpha 3 scope

Implemented now:

- Native three-pane workbench shell.
- Source flow with `Create from official distribution` and `Open existing ISO`.
- Official Lubuntu 26.04.1 (default) and Ubuntu 26.04.1 source entries with streaming download/resume and SHA-256 verification support.
- Existing ISO analysis through WSL without copying the ISO.
- Overview page.
- Applications import entry points for repository, direct URL, local Linux package/file, Git, and AI-generated applications.
- AI App Studio with provider/model/endpoint/API-key configuration, coding-toolchain selection, prompt editor and generated-code editor.
- CPL/CPA is present as a first-class toolchain option.
- Persistent Changes pane with Test and Undo.
- Project save/load without embedding the source ISO or API secrets.
- Storage settings and a configurable safety reserve. Large-data paths are deliberately unset on first start, so ChromaPress cannot silently choose C: or WSL root.

Not yet implemented in alpha 3:

- Full package catalogue and image mutation.
- Full Application Editor.
- Actual ISO Build & Verify pipeline.
- Full CPL compiler execution bridge.
- RHEL/Debian/Rocky/Alma/Oracle/Fedora/Mint/Arch/SUSE official-source catalogues.

Those are the next gated steps; the navigation is already visible so the final product shape does not drift.

## Windows setup

```powershell
py -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .
.\.venv-win\Scripts\chromapress.exe
```

The GUI calls the configured WSL distribution only for Linux-only analysis/build operations.

## Safety rules

ChromaPress must never modify the selected input ISO. It must never create hidden duplicate uploads of an existing ISO. Large jobs must use one explicit workspace and must report storage use before mutation. Failed/cancelled/successful jobs must clean large transient data by default.


## Alpha 5 / Part 2

Part 1 Workbench Foundation has passed the on-machine source, download/resume and storage fail-closed gates. Alpha 5 starts Part 2 by loading real user-facing applications from the selected ISO in the background and staging Remove actions into Changes without mutating the image.


## Alpha 8
Applications Quick view now uses collapsed categories and suite grouping (including LibreOffice) with a faster metadata scan.


## Alpha 11
Applications now has explicit row action buttons, a collapsible Changes side panel, a live full image plan, and a final pre-generation review page. Home / Personal also keeps a visible Internet/browser/email capability group.

## Alpha 13
Home / Personal now fills missing everyday roles with explicit repository-backed recommendations on validated Ubuntu/Lubuntu 26.04 targets. Installed applications retain `Keep | Remove`; missing roles use `Skip | Add`. `Skip` is the default and additions are never silent. Staged additions appear in Changes and can be undone directly by selecting `Skip` again.


## Alpha 14

Alpha 14 fixes the Applications presentation found during the on-machine Alpha 13 review without advancing to the next development gate:

- Home / Personal uses AbiWord as the lightweight writing recommendation even when LibreOffice is already installed.
- LibreOffice remains preserved/installed but is presented under `Specialised / Advanced → Full office suites` in Home / Personal.
- Empty specialist groups no longer appear a second time under Everyday essentials.
- Recommendation rows now render the actual `Skip | Add` buttons.
- Staging Remove/Add and undoing with Keep/Skip preserve the current expanded tree groups instead of collapsing the Applications view.
- Application table sizing was tightened: Description stretches while State and Action remain stable and aligned.


## Alpha 15 scenario application review

The Applications page now adds explicit role-based recommendations for Office / Business, Development / Engineering, Production / Industrial and Gaming / Team / Education. Recommendations remain opt-in with `Skip | Add`; source type is visible as Repository, Snap or Bundled. See `ALPHA15_NOTES.md`.


## Alpha 16 installed-app controls and Undo

Alpha 16 fixes the on-machine Alpha 15 review findings without leaving the Applications gate. Changes-panel selection survives Test/refresh so Undo remains functional. Installed applications no longer show a passive `Preserved` action: every detected launcher uses `Keep | Remove | Replace`, with unresolved package ownership carried by an exact desktop-file locator for fail-closed resolution before apply. Refract Studio is now bundled as the packaged `.deb` rather than the raw Python source ZIP. See `ALPHA16_NOTES.md`.

## Alpha 17 global application search and profile selection

Alpha 17 fixes the on-machine Alpha 16 Gaming / Team / Education review without leaving Part 2. Application search is now global across installed applications and supported available/recommended applications regardless of the selected system-use profile. The active profile button remains visibly selected with a slightly darker checked state. The four Gaming / Team / Education diagnostics use the verified Ubuntu 26.04 package names and repository components: MangoHud (`mangohud`, Universe), nvtop (`nvtop`, Multiverse), Speedtest CLI (`speedtest-cli`, Universe), and GLMark2 (`glmark2-x11`, Universe). Repository availability is still revalidated by the servicing engine before Apply; the source ISO is never changed merely by searching or staging.


## Alpha 18 School / Education profile

Alpha 18 keeps Part 2 active and separates education from the previous combined Gaming / Team / Education profile. `School / Education` is now a first-class system-use choice and `Gaming / Team` remains its own profile. Native desktop entries with the `Education` category are grouped under `Education & Learning`.

For validated Ubuntu/Lubuntu 26.04 targets, the School / Education profile visibly recommends the bundled `ChromaLearn AI` Debian package with the normal `Skip | Add` workflow. The exact bundled package is SHA-256 pinned and is never silently installed. ChromaLearn's own `.deb` contains its developer repository, including Git metadata, source, tests, documentation, packaging and build script, so a school can install the application and continue development locally. Application search remains global, so `ChromaLearn` can be found regardless of which system-use profile is currently selected.


## Alpha 19 profile navigation after global search

Alpha 19 keeps the Alpha 17 global-search behaviour but makes system-use profile selection an explicit return to the selected profile view. If a global search is active and the user selects Home / Personal, Office / Business, Development / Engineering, Production / Industrial, School / Education, Gaming / Team or Custom, the search field is cleared and the application tree is immediately rebuilt for that selected profile. Typing in Search remains global and independent of the active profile.


## Alpha 29 manifest-backed firmware / driver planning

Alpha 29 continues Part 3 with a fail-closed, staging-only hardware package plan. Only firmware/microcode and driver/DKMS packages explicitly found in source manifests are eligible. A staged re-resolution requires signed repository metadata, dependency resolution, last-viable-kernel protection and distro-native initramfs regeneration at a later verified apply gate. The selected ISO remains read-only.


## Alpha 30 rootfs / SquashFS planning

Alpha 30 continues Part 3 with a source-hash-locked, staging-only SquashFS repack plan. Only explicitly detected rootfs layers may be selected. Compression changes remain preservation-first and require later unsquashfs/mksquashfs capability verification; the selected source ISO is never modified at this stage.

## Alpha 31 immutable / volatile runtime planning

Alpha 31 continues Part 3 with a source-hash-locked, staging-only immutable runtime plan. A detected SquashFS layer can be selected as the read-only base for a volatile OverlayFS runtime with tmpfs upper/work storage. The plan explicitly states that runtime changes do not survive reboot and requires distro-native initramfs plus boot integration verification before any later apply. Controlled persistent directories and persistent partitions/volumes remain a later gated increment; the selected ISO remains read-only.



## Alpha 32 controlled persistence planning

Alpha 32 continues Part 3 with a source-hash-locked, staging-only controlled persistence plan layered on the Alpha 31 read-only SquashFS + volatile OverlayFS model. Only explicitly listed absolute directories are marked to survive reboot; all unlisted runtime changes remain volatile. Persistence is bounded to a dedicated target-system ext4 volume plan with explicit size and label, while the source ISO is never repartitioned. Distro-native initramfs, boot and mount integration must be re-verified before any later apply.


## Alpha 33 runtime integration verification planning

Alpha 33 continues Part 3 by binding runtime plans to exact source evidence: detected SquashFS layer, explicit boot configuration files, kernel images and initramfs images. The staged plan preserves the detected boot structure, requires distro-native initramfs hook verification/regeneration, and makes mount behavior explicit for volatile versus controlled-persistence targets. The selected source ISO remains read-only.

## Alpha 34 — Boot identity / metadata staging

Alpha 34 adds a source-hash-locked, staging-only boot identity/metadata plan for explicitly detected boot entries, entry labels/order and ISO Volume ID. Existing El Torito/hybrid boot records and unrelated entries are preserved, with boot-catalog re-verification required before any later apply.

## Alpha 35 — installer evidence baseline (early Part 5 preparation)

Alpha 35 added a real read-only Installer page. Installer family detection is evidence-based: ChromaPress uses explicit ISO paths and package manifests instead of inferring from the distribution name. This allows installer payloads inside SquashFS (such as Calamares) to be identified without modifying the image. Alpha 36 corrects the plan classification: Installer belongs to Part 5, while Part 4 is System Configuration.

## Alpha 36 — Part 4 System Configuration evidence baseline

Alpha 36 replaces the System placeholder with a read-only, preservation-first System Configuration page. It reports only manifest-backed capability evidence and explicitly identifies which account, networking, service, security, kiosk/persistence and authenticator settings still require rootfs-level verification before staging is allowed. No system configuration or source-ISO bytes are modified. See `ALPHA36_NOTES.md`.


## Alpha 37 — rootfs-verified identity/account staging

Alpha 37 continues Part 4 with the first real System Configuration staging gate. ChromaPress reads only non-secret `/etc/passwd`, `/etc/group` and optional `/etc/login.defs` metadata directly from the detected layered SquashFS rootfs; `/etc/shadow` is deliberately never read. The System page can stage a source-hash-locked target-system default-user plan with username, display name and standard/admin role. Passwords, hashes, tokens and recovery secrets are not stored in the plan and remain deferred to a later secure verified-apply gate. The selected ISO remains read-only.

## Alpha 38 — hostname / machine identity staging

Alpha 38 continues Part 4 with a deliberately narrow hostname/machine-identity gate. ChromaPress verifies `/etc/hostname` and inspects only the state of `/etc/machine-id` from the read-only layered rootfs. The machine-id value itself is never displayed or staged. A source-hash-locked plan can configure a safe target hostname and either preserve current machine-id boot behavior or request machine-id regeneration on first boot. The selected ISO remains read-only. Autologin is deferred to a separate later Part 4 gate to keep login/security policy review isolated.


## Alpha 39 — autologin / display-manager staging

Alpha 39 continues Part 4 with a deliberately isolated autologin gate. ChromaPress verifies the selected rootfs default display manager read-only, inspects only explicit non-secret autologin directives, and stages either enable or disable intent without reading/storing passwords or other credential secrets. Enabling autologin requires the target user to be re-verified before any later apply. The current/default session is preserved, and the source ISO remains read-only.


## Alpha 44 — Part 4 services/systemd gate

Alpha 44 adds read-only systemd unit-directory evidence and a staging-only single-service enable/disable plan. Unit contents, enablement-link targets, environment files, credentials and source-ISO bytes remain untouched.

## Alpha 45 — Part 4 timers/systemd gate

Alpha 45 adds a narrow staging-only systemd timer gate. It verifies read-only unit-directory evidence, never reads timer contents or credentials, and stages only one `.timer` enable/disable intent with target re-verification required before apply.

## Alpha 46 — Part 4 targets/startup gate

Alpha 46 adds a narrow staging-only systemd default-target gate. It reuses verified read-only unit-directory evidence, does not read target unit contents or the current `default.target` symlink target, and stages only one `.target` default-startup intent with target re-verification required before apply.


## Alpha 47 — Part 4 firewall gate

Alpha 47 adds a narrow staging-only firewall state gate. It verifies only supported firewall backend path metadata read-only inside the selected SquashFS rootfs, does not read firewall rule contents, ports/services policy, application profiles or secrets, and stages only enable/disable intent. Backend/apply semantics must be re-verified before any later apply step.

## Alpha 48 — Part 4 AppArmor gate

Alpha 48 adds a narrow staging-only AppArmor state gate. It verifies only AppArmor component path metadata read-only inside the selected SquashFS rootfs, does not read AppArmor profile contents, parser configuration contents, abstractions/tunables or policy secrets, and stages only enable/disable intent. AppArmor boot/apply semantics must be re-verified before any later apply step.

## Alpha 49 — Part 4 sysctl gate

Alpha 49 adds a narrow staging-only sysctl gate. It verifies only sysctl infrastructure/path metadata read-only inside the selected SquashFS rootfs, does not read existing sysctl configuration contents or effective runtime values, and can stage one safe dotted key with one integer value. Existing sysctl files are preserved; any later apply must use a managed drop-in and re-verify the target key and apply semantics.


## Alpha 50 — Part 4 Users / Groups / Password Policy gate

Alpha 50 expands the Part 4 account gate without starting Part 5. It analyzes target-ISO users/groups and non-secret password-aging defaults read-only, reports capability status explicitly, and stages preservation-first default-user/create-user/modify-user/create-group plans. Quick mode keeps technical identifiers hidden; Advanced/Expert exposes UID/GID, supplementary groups and password-aging controls. `/etc/shadow`, credential secrets and Windows/WSL host accounts are never used by this gate.


## Alpha 63 — Part 4 FIDO2 policy gate

Alpha 63 adds a deliberately narrow FIDO2 policy gate for the Alpha 62 recovery administrator. ChromaPress requires positive target package-manifest evidence for a PAM FIDO2/U2F module plus libfido2 before it can stage a FIDO2 second-factor intent. The gate does not read PAM contents, enumerate or enroll authenticators, inspect USB/HID state, read credential identifiers/secrets, or claim WebAuthn, security-key, YubiKey, platform-authenticator or TPM support. Existing primary authentication is preserved and actual integration must be re-verified before apply.


## Alpha 64 — Part 4 WebAuthn policy gate

Alpha 64 adds one bounded browser-mediated WebAuthn recovery-policy intent. ChromaPress requires target package-manifest evidence for an allowlisted browser package plus the verified Alpha 62 recovery-administrator dependency. The gate never reads browser configuration, relying-party/origin configuration, authenticator devices, USB/HID state, credential IDs/secrets, or host browser/authenticator state. It never claims actual WebAuthn runtime support or enrollment. Runtime browser support, relying party, origin, and authenticator compatibility must be re-verified before apply/use. Security keys, YubiKey-class authenticators, platform authenticators, and TPM remain separate later gates.

## Alpha 68 — Part 4 complete: security keys, YubiKey-class, platform authenticators and TPM

Alpha 65 adds a generic external/roaming FIDO2/U2F security-key policy bound to the verified Alpha 62 recovery role and Alpha 63 FIDO2 stack. Package metadata may verify target-side tooling, but no physical key presence, compatibility, credential or enrollment is claimed.

Alpha 66 adds a separate YubiKey-class policy. It requires positively identified target YubiKey userspace/PAM tooling and never infers a physical YubiKey from generic FIDO2 support. Serial numbers, PIN/OTP secrets, USB/HID state and enrollment remain outside analysis/staging.

Alpha 67 deliberately remains `UNKNOWN` under static ISO analysis unless separately verified runtime and hardware evidence exists. ChromaPress does not equate a browser, biometric stack or TPM package with a WebAuthn platform authenticator. Biometrics and TPM remain distinct concepts.

Alpha 68 adds TPM-backed recovery-key protection policy when target package metadata verifies both TPM2 tooling and a TSS2 userspace stack. This does not prove a physical TPM. TPM presence, ownership, PCR policy, key generation and sealing must be verified later. TPM is never presented as biometric capability or as proof of a platform authenticator.

With Alpha 68, the planned Part 4 sequence is complete. The consolidated `testpack/part4_tests.zip` covers the full Part 4 implementation with fail-fast/resume behavior and a final full seal pass. Parts 5–8 will each receive their own consolidated test package rather than reusing the Part 4 bundle.


**Alpha 69 Fix 3 test-pack note:** consolidated test collection is Part-scoped. Tests belonging to later Parts may coexist under `tests/`; the active Part collects and runs only its own verified manifest paths, and unrelated files are preserved.

## Alpha 70 — Part 6 AI App Studio Complete

Part 6 is now handled as one consolidated, fail-closed workflow. AI remains optional. Generated applications are normal inspectable projects, receive structured detected Linux target context, must declare integration metadata in `chromapress-app.json`, undergo path/manifest/credential validation, and stage dependencies as ordinary ChromaPress package operations. Generation credentials remain session-only and are never included in staged project data or the target ISO. Build/test commands are review plans only; untrusted generated code is not automatically executed on the host, and apply remains blocked until explicit review gates are completed.

### Alpha 70 Fix 1 — AI App Studio staging safety

Part 6 now requires both a validated target Linux context and an explicit human-review acknowledgement before **Stage reviewed app** can be enabled. Any project/target change invalidates that acknowledgement and disables staging again.

## Alpha 72 Fix 1 — release polish

Post-acceptance GUI review replaced the old Components placeholder with a target-image manifest-backed component browser, added the ChromaPress window/application icon, an About dialog with copyright, MIT license information and a Share ChromaPress action, and corrected the status-bar version display. The Components view fails closed rather than substituting Windows/WSL host package data.
