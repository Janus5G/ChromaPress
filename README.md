<p align="center">
  <img src="src/chromapress/assets/chromapress-logo.png" width="640" alt="ChromaPress">
</p>

[English](README.md) | [Dansk](README.da.md)

# ChromaPress

**Current release:** `1.0.0a72`
**License:** MIT
**Platforms:** Windows 11 + WSL2, and native Debian/Ubuntu
**Runtime:** Python 3.11+ · PySide6 6.8+

ChromaPress is a native desktop workbench for analyzing, staging, customizing, building and verifying Linux installation images.

The central design rule is simple: **the selected source ISO is treated as read-only**. Changes are staged and reviewed separately, then handled by the Linux-native servicing/build engine in a controlled workspace.

> `1.0.0a72` is an alpha release. Static analysis, manifests and package evidence are not a substitute for real boot, install, live-session or hardware validation where those are required.

## Highlights

- Native PySide6/Qt desktop interface.
- Windows front end using WSL2 for Linux-native image tooling.
- Native Linux engine in the Debian package.
- Existing ISO analysis without copying or modifying the source ISO.
- Role-based application selection and target-image application/component inspection.
- Staged **Changes → Test → Undo** workflow.
- Read-only Boot & Hardware evidence before changes are staged.
- Preservation-first System, Installer, Desktop and custom-content planning.
- Current image-plan review before production.
- SHA-256-backed source/integrity checks where applicable.
- Optional AI App Studio with explicit review and validation gates; this feature is not part of the current verified runtime path.
- Danish and English interface support.
- Windows `.exe` and Debian `.deb` release builds.

## Verified ISO build — end-to-end evidence

The screenshots below document one complete ChromaPress build path from a reviewed production plan to a booted live ISO with the requested package change verified at runtime.

### 1. Reviewed build plan ready

![ChromaPress Build & Verify ready](docs/screenshots/01-build-verify-ready.png)

The production plan has passed preflight and is staged for generation. The selected source ISO remains read-only.

### 2. Live ISO generation

![ChromaPress DESTILLATION build progress](docs/screenshots/02-build-progress-tux.png)

During generation, ChromaPress shows the current real build phase and a monotonic progress percentage. The percentage advances from completed build phases rather than elapsed-time estimates.

### 3. Build complete

![ChromaPress ISO build complete](docs/screenshots/03-build-complete.png)

The generated ISO completed ChromaPress' output SHA-256 and static boot-structure checks. Runtime boot verification is still treated as a separate gate.

### 4. Runtime verification

![ChromaPress generated ISO running AbiWord](docs/screenshots/04-runtime-abiword-launched.png)

The generated ISO was booted as a Lubuntu 26.04 live system in Oracle VirtualBox. The package added by ChromaPress was then verified as installed and launched successfully.

```text
BOOT_ISO=PASS
LIVE_DESKTOP=PASS
ABIWORD_INSTALLED=PASS
ABIWORD_VERSION=3.0.8+ds-2
ABIWORD_LAUNCH=PASS
```

### Sorry, Cubic. 🙂

ChromaPress exists in part because of time spent debugging Linux ISO customization tools.

A friendly reminder from one open-source project to another: people who spend hours finding, reproducing, and fixing bugs are contributors too. Treat them that way.

<details>
<summary><strong>Full verification trail</strong></summary>

The complete test sequence is retained below as additional evidence.

#### VirtualBox test machine creation

![VirtualBox VM creation for ChromaPress ISO verification](docs/screenshots/05-virtualbox-create-vm.png)

#### VirtualBox machine settings

![VirtualBox machine settings for ChromaPress ISO verification](docs/screenshots/06-virtualbox-vm-settings.png)

#### Boot-medium check

![VirtualBox boot medium check](docs/screenshots/07-virtualbox-boot-medium-check.png)

#### Generated ISO mounted

![ChromaPress generated ISO mounted in VirtualBox](docs/screenshots/08-virtualbox-iso-mounted.png)

#### Lubuntu live desktop reached

![Lubuntu live desktop booted from the ChromaPress-generated ISO](docs/screenshots/09-lubuntu-live-desktop.png)

#### Live-session screenshot capture

![Lubuntu live-session screenshot during verification](docs/screenshots/10-live-screenshot-tmp.png)

#### AbiWord present in the live system menu

![AbiWord visible in the live system Office menu](docs/screenshots/11-abiword-office-menu.png)

#### VirtualBox shared-clipboard check during testing

![VirtualBox shared clipboard setting during verification](docs/screenshots/12-virtualbox-shared-clipboard.png)

#### Package status verified

![AbiWord package status verified in the generated live ISO](docs/screenshots/13-abiword-dpkg-status.png)

</details>

## Source ISO and analysis

ChromaPress can work from a supported distribution source or open an existing ISO directly. Existing images are referenced in place and analyzed through the Linux-native engine.

![ChromaPress source ISO](docs/screenshots/source.png)

The Overview page presents the detected distribution, architecture, boot mode, root filesystem layers, installer evidence and source SHA-256.

<details>
<summary><strong>ISO overview screenshot</strong></summary>

![ChromaPress ISO overview](docs/screenshots/overview.png)

</details>

## Application selection

ChromaPress can organize applications around the intended use of the target system. Application changes remain explicit and staged rather than silently applied.

![ChromaPress application selection](docs/screenshots/applications.png)

## AI App Studio

> **Verification status:** AI App Studio has not been runtime-tested for this release and is not included in the verified end-to-end release path documented above.

AI App Studio is an optional experimental feature designed to follow the same review model as the rest of ChromaPress.

It is intended to assist with creating or revising applications using target-Linux context while keeping the generated project inspectable. Generated source must be reviewed and validated before it can be staged for inclusion in an ISO.

API credentials are intended to remain session-scoped and are not designed to be stored in ChromaPress project files or copied into the target image.

![ChromaPress AI App Studio](docs/screenshots/ai-app-studio.png)

## Review before build

The current image plan provides one place to inspect the selected source and staged intent before production.

![ChromaPress current image plan](docs/screenshots/image-plan.png)

The production page keeps reusable profile handling, output configuration, verification settings and reviewed expert hooks together.

![ChromaPress build and verification](docs/screenshots/build-verify.png)

## Safety and verification model

ChromaPress is deliberately preservation-first and fail-closed.

- The selected input ISO is not modified in place.
- Changes are staged before they are applied.
- Unknown or unsupported target capabilities are not silently treated as verified.
- Host Windows/WSL state is not substituted for missing target-image evidence.
- Security-sensitive configuration is separated into explicit gates.
- Passwords, API keys, signing keys and similar secrets are not intended to be stored in project files.
- AI-generated code is treated as reviewable source, not trusted merely because AI produced it.
- Static evidence does not prove runtime, hardware or deployment behavior.
- Final release acceptance still requires the relevant real-world runtime tests.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and security expectations.

## More screenshots

<details>
<summary><strong>Files and custom content</strong></summary>

![ChromaPress files and custom content](docs/screenshots/files.png)

</details>

<details>
<summary><strong>System configuration</strong></summary>

![ChromaPress system configuration](docs/screenshots/system.png)

</details>

<details>
<summary><strong>Boot and hardware</strong></summary>

![ChromaPress boot and hardware](docs/screenshots/boot-hardware.png)

</details>

<details>
<summary><strong>Installer configuration</strong></summary>

![ChromaPress installer configuration](docs/screenshots/installer.png)

</details>

<details>
<summary><strong>Desktop configuration</strong></summary>

![ChromaPress desktop configuration](docs/screenshots/desktop.png)

</details>

<details>
<summary><strong>Language and AI settings</strong></summary>

![ChromaPress settings](docs/screenshots/settings-language.png)

</details>

## Installation

### Windows

The release build is a native Windows GUI. Linux-native ISO operations are delegated to WSL2.

1. Install/enable WSL2 and a supported Linux environment.
2. Download `ChromaPress.exe` from the GitHub Releases page.
3. Start ChromaPress normally from Windows.
4. Select or open the Linux ISO you want to analyze.

The source ISO remains referenced in place; ChromaPress does not require an upload step.

### Debian / Ubuntu

Download the `.deb` release asset and install it with your normal package manager, for example:

```bash
sudo apt install ./chromapress_1.0.0~a72-1_all.deb
```

The Debian package uses the Linux engine directly rather than routing through WSL.

### From source

```bash
python -m venv .venv
python -m pip install -e .
python -m chromapress.app
```

On Windows, create the virtual environment with your normal Windows Python installation and ensure WSL2 is available for Linux-native image operations.

## Development and tests

The final release regression gate can be run with:

```bash
python -m pytest -q final_testpack/tests/test_final_release_gate.py
```

Windows release build:

```powershell
.\packaging\build_windows_release.ps1 -SkipInstall
```

Debian release build:

```bash
./packaging/build_deb.sh
```

A successful build is not, by itself, a complete release acceptance. The produced artifacts must also be tested as the actual installed/distributed programs.

## Built with ChatGPT

ChromaPress was created through an extended human–AI collaboration between **Janus Rokkjær and ChatGPT**.

The program's architecture, implementation, interface work, debugging, testing, localization, documentation and release preparation were developed with ChatGPT as the primary development assistant. The product direction, requirements, acceptance criteria and hands-on testing were controlled by Janus Rokkjær throughout development.

Rather than hiding the use of AI, ChromaPress is published openly as an example of what can be achieved when AI-assisted development is combined with continuous human review, testing and correction.

ChatGPT and OpenAI are not affiliated with or endorsing ChromaPress.

## Generated output

Programs and ISO images created with ChromaPress are user output. ChromaPress does not automatically add deployment branding, telemetry identifiers or a shared ChromaPress runtime to applications created through AI App Studio.

## Roadmap

The next ChromaPress development cycle is planned to explore two major additions after the initial release has had time for real-world use and feedback.

### System Backup ISO

Create a bootable recovery ISO from an existing Linux installation while preserving the original system during capture.

Planned goals include:

- safe, read-only system collection
- explicit include/exclude review before capture
- SquashFS-based system image
- bootable recovery ISO generation
- manifest and SHA-256 integrity verification
- preservation-first handling of user and custom system content

### Bootable USB Writer

Write a ChromaPress-generated ISO directly to removable USB media.

Planned safety requirements include:

- explicit removable-device selection
- no automatic selection of the first disk
- system/internal disks blocked by default
- destructive-write confirmation
- write, flush and read-back verification
- final PASS/FAIL evidence

These features are planned for the next development build after the initial ChromaPress release.

Implementation ideas, platform-specific experience and security recommendations are very welcome.

## Contributing

Ideas, bug reports, documentation improvements and focused code contributions are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. ChromaPress has strict preservation and verification rules around ISO handling, staged changes, privilege boundaries and security-sensitive operations, but contributors do not need to be experts in every part of the project to propose an idea or improvement.

## Development history

The original alpha-by-alpha development record is preserved in [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md).

A shorter release-oriented history is available in [CHANGELOG.md](CHANGELOG.md).

## Privacy Policy

ChromaPress does not intentionally collect, store or transmit personal user data.

[Read the Privacy Policy](PRIVACY.md)

## License

ChromaPress is released under the [MIT License](LICENSE).

Copyright © 2026 Janus Rokkjær.

Third-party components and notices are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
