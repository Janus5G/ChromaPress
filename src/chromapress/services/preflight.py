from __future__ import annotations

from pathlib import Path
import ipaddress
from urllib.parse import urlparse
import re

from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
from chromapress.services.part5 import (
    validate_installer_payload, validate_custom_content_payload, validate_desktop_payload, validate_kiosk_payload,
)
from chromapress.services.part6 import validate_ai_app_payload
from chromapress.services.part7 import validate_build_plan_payload


_ALLOWED_LOCAL = {".deb", ".rpm", ".appimage", ".flatpak", ".snap", ".tar", ".gz", ".xz", ".zst", ".zip"}


def test_change(change: ChangeItem) -> tuple[ChangeStatus, str]:
    config_type = str(change.payload.get("config_type", "")).strip() if change.kind == ChangeKind.CONFIG else ""
    if config_type == "part7_production_build_plan":
        ok, message = validate_build_plan_payload(change.payload)
        return (ChangeStatus.PASS, message) if ok else (ChangeStatus.FAIL, message)
    if config_type == "part5_installer_profile":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Part 5 installer profile is not locked to a valid source SHA-256."
        ok, message = validate_installer_payload(change.payload)
        if not ok:
            return ChangeStatus.FAIL, message
        if change.payload.get("generated_template_contains_real_secret") is not False:
            return ChangeStatus.FAIL, "Generated installer template must explicitly contain no real secret."
        template = str(change.payload.get("generated_native_template") or "")
        if "${CHROMAPRESS_PASSWORD_HASH}" not in template:
            return ChangeStatus.FAIL, "Generated installer template must keep credentials as a secure apply-time placeholder."
        return ChangeStatus.PASS, "Part 5 installer profile is source-hash locked, structured-form validated, credential-secret free, native-validator gated and staging-only."
    if config_type == "part5_custom_content":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Part 5 custom-content plan is not locked to a valid source SHA-256."
        ok, message = validate_custom_content_payload(change.payload)
        return (ChangeStatus.PASS, "Part 5 custom content is source-hash locked, archive/path/symlink inspected, conflict-policy explicit, reviewed and staging-only.") if ok else (ChangeStatus.FAIL, message)
    if config_type == "part5_desktop_defaults":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Part 5 desktop plan is not locked to a valid source SHA-256."
        ok, message = validate_desktop_payload(change.payload)
        return (ChangeStatus.PASS, "Part 5 desktop plan is source-hash locked, desktop-native-adapter bound, preservation-first and staging-only.") if ok else (ChangeStatus.FAIL, message)
    if config_type == "part5_kiosk_session":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Part 5 kiosk/session plan is not locked to a valid source SHA-256."
        ok, message = validate_kiosk_payload(change.payload)
        return (ChangeStatus.PASS, "Part 5 kiosk/session plan is source-hash locked, generic, capability-bound, recovery-aware, runtime-validation gated and staging-only.") if ok else (ChangeStatus.FAIL, message)
    if change.kind == ChangeKind.LOCAL_PACKAGE:
        path = Path(str(change.payload.get("path", "")))
        if not path.is_file():
            return ChangeStatus.FAIL, "Local file does not exist."
        if path.suffix.lower() not in _ALLOWED_LOCAL and not any(str(path).lower().endswith(x) for x in (".tar.gz", ".tar.xz", ".tar.zst")):
            return ChangeStatus.WARNING, "File exists, but its packaging format is not yet recognized."
        return ChangeStatus.PASS, "Local package/file exists and can be staged for target-specific inspection."
    if change.kind == ChangeKind.DIRECT_URL:
        parsed = urlparse(str(change.payload.get("url", "")))
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            return ChangeStatus.FAIL, "Direct link is not a valid HTTP(S) URL."
        return ChangeStatus.PASS, "Direct link syntax is valid; download/signature checks happen before apply."
    if change.kind == ChangeKind.GIT:
        value = str(change.payload.get("url", "")).strip()
        if not (re.match(r"^https?://", value) or value.startswith("git@")):
            return ChangeStatus.FAIL, "Git source must be an HTTPS/HTTP or git@ URL."
        return ChangeStatus.PASS, "Git source syntax is valid; clone/build remains isolated and unprivileged."
    if change.kind == ChangeKind.PACKAGE_REPOSITORY:
        name = str(change.payload.get("package", "")).strip()
        if not name:
            return ChangeStatus.FAIL, "Package name is empty."
        manager = str(change.payload.get("manager", "apt")).strip().casefold() or "apt"
        if manager == "bundled":
            path = Path(str(change.payload.get("path", "")))
            if not path.is_file():
                return ChangeStatus.FAIL, "Bundled application source is missing from the ChromaPress project."
            expected = str(change.payload.get("sha256", "")).strip().casefold()
            if expected:
                import hashlib
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    return ChangeStatus.FAIL, "Bundled application source failed its SHA-256 integrity check."
            documentation_path_raw = str(change.payload.get("documentation_path", "")).strip()
            if documentation_path_raw:
                documentation_path = Path(documentation_path_raw)
                if not documentation_path.is_file():
                    return ChangeStatus.FAIL, "Bundled application documentation is missing from the ChromaPress project."
                documentation_expected = str(change.payload.get("documentation_sha256", "")).strip().casefold()
                if documentation_expected:
                    import hashlib
                    documentation_actual = hashlib.sha256(documentation_path.read_bytes()).hexdigest()
                    if documentation_actual != documentation_expected:
                        return ChangeStatus.FAIL, "Bundled application documentation failed its SHA-256 integrity check."
                return ChangeStatus.PASS, "Bundled application and documentation exist and passed their staging integrity checks."
            return ChangeStatus.PASS, "Bundled application source exists and passed its staging integrity check."
        if manager == "snap":
            return ChangeStatus.PASS, "Snap Store package request is staged; availability/signature checks run before apply."
        return ChangeStatus.PASS, "Repository package request is ready for target catalogue resolution."
    if change.kind == ChangeKind.PACKAGE_REMOVE:
        package = str(change.payload.get("package", "")).strip()
        desktop = str(change.payload.get("desktop_file", "")).strip()
        target_ref = str(change.payload.get("target_ref", "")).strip()
        if package:
            return ChangeStatus.PASS, "Installed application removal is staged; dependency/protection validation runs before apply."
        if desktop and target_ref:
            return ChangeStatus.PASS, "Installed launcher is identified exactly; package ownership will be resolved fail-closed before removal is applied."
        return ChangeStatus.FAIL, "Installed application has no safe package or launcher locator."
    if change.kind == ChangeKind.PACKAGE_REPLACE:
        replacement = str(change.payload.get("replacement_package", "")).strip()
        package = str(change.payload.get("package", "")).strip()
        desktop = str(change.payload.get("desktop_file", "")).strip()
        target_ref = str(change.payload.get("target_ref", "")).strip()
        if not replacement:
            return ChangeStatus.FAIL, "Replacement package name is empty."
        if not (package or (desktop and target_ref)):
            return ChangeStatus.FAIL, "Installed application has no safe package or launcher locator."
        return ChangeStatus.PASS, "Replacement plan is staged; replacement resolution and current-package ownership/dependency checks run before any apply step."
    if change.kind == ChangeKind.AI_APP:
        if str(change.payload.get("config_type", "")) == "part6_ai_app_project":
            ok, message = validate_ai_app_payload(change.payload)
            return (ChangeStatus.PASS, message) if ok else (ChangeStatus.FAIL, message)
        code = str(change.payload.get("code", ""))
        return (ChangeStatus.PASS, "Legacy generated source exists; migrate to the Part 6 reviewed-project gate before apply.") if code.strip() else (ChangeStatus.FAIL, "No generated source is attached to this change.")
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "boot":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Boot plan is not locked to a valid source SHA-256."
        config_files = change.payload.get("boot_config_files")
        if not isinstance(config_files, list) or not [x for x in config_files if str(x).strip()]:
            return ChangeStatus.FAIL, "No explicit boot configuration source was recorded for this plan."
        default_entry = change.payload.get("default_entry")
        timeout = change.payload.get("timeout_seconds")
        kernel_args = str(change.payload.get("kernel_args_append", ""))
        if default_entry is not None:
            if not isinstance(default_entry, dict) or not str(default_entry.get("title", "")).strip() or not str(default_entry.get("source", "")).strip():
                return ChangeStatus.FAIL, "Default boot entry is not tied to explicit parsed source evidence."
        if timeout is not None:
            if not isinstance(timeout, int) or isinstance(timeout, bool) or not 0 <= timeout <= 600:
                return ChangeStatus.FAIL, "Boot timeout must be between 0 and 600 seconds."
        if any(ch in kernel_args for ch in ("\r", "\n", "\x00")) or len(kernel_args) > 512:
            return ChangeStatus.FAIL, "Kernel arguments contain unsafe control characters or exceed 512 characters."
        if default_entry is None and timeout is None and not kernel_args.strip():
            return ChangeStatus.FAIL, "Boot plan contains no requested configuration change."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 27 boot plans must remain staging-only."
        return ChangeStatus.PASS, "Boot plan is source-hash locked and staging-only. Apply must re-verify the source and boot structure before writing anything."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "boot_metadata":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Boot identity/metadata plan is not locked to a valid source SHA-256."
        config_files = change.payload.get("boot_config_files")
        if not isinstance(config_files, list) or not [x for x in config_files if str(x).strip()]:
            return ChangeStatus.FAIL, "No explicit boot configuration source was recorded for the metadata plan."
        entries = change.payload.get("boot_entries")
        if not isinstance(entries, list) or not entries:
            return ChangeStatus.FAIL, "No explicit parsed boot-entry evidence was recorded for the metadata plan."
        normalized_entries = {
            (str(item.get("title") or "").strip(), str(item.get("source") or "").strip())
            for item in entries if isinstance(item, dict)
        }
        selected = change.payload.get("selected_entry")
        new_label = str(change.payload.get("entry_label_new", "")).strip()
        order = str(change.payload.get("boot_order_operation", "preserve")).strip()
        volume_new = str(change.payload.get("volume_id_new", "")).strip()
        entry_change = bool(new_label) or order == "move_selected_first"
        if order not in {"preserve", "move_selected_first"}:
            return ChangeStatus.FAIL, "Boot order operation is not supported."
        if entry_change:
            if not isinstance(selected, dict):
                return ChangeStatus.FAIL, "Boot entry label/order changes require an explicit detected boot entry."
            key = (str(selected.get("title") or "").strip(), str(selected.get("source") or "").strip())
            if not all(key) or key not in normalized_entries:
                return ChangeStatus.FAIL, "Selected boot entry is not tied to the recorded parsed source evidence."
            if key[1] not in [str(x).strip() for x in config_files]:
                return ChangeStatus.FAIL, "Selected boot entry source is not one of the recorded boot configuration files."
        if new_label and (len(new_label) > 80 or any(ord(ch) < 32 or ord(ch) > 126 for ch in new_label)):
            return ChangeStatus.FAIL, "Boot entry label must contain 1–80 printable ASCII characters."
        if volume_new and (len(volume_new) > 32 or any(ord(ch) < 32 or ord(ch) > 126 for ch in volume_new)):
            return ChangeStatus.FAIL, "Volume ID must contain 1–32 printable ASCII characters."
        if not entry_change and not volume_new:
            return ChangeStatus.FAIL, "Boot identity/metadata plan contains no requested change."
        if change.payload.get("preserve_boot_records") is not True or change.payload.get("preserve_unselected_entries") is not True:
            return ChangeStatus.FAIL, "Boot metadata servicing must preserve boot records and unrelated boot entries."
        if change.payload.get("require_boot_catalog_reverification") is not True:
            return ChangeStatus.FAIL, "Boot catalog re-verification is mandatory before metadata changes are applied."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Boot identity/metadata plans must keep the selected ISO read-only and preserve unrelated content."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 34 boot identity/metadata plans must remain staging-only."
        return ChangeStatus.PASS, "Boot identity/metadata plan is source-hash locked, explicit-entry bound, boot-record preserving, catalog-reverification gated and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "kernel_initramfs":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Kernel/initramfs plan is not locked to a valid source SHA-256."
        kernels = change.payload.get("kernel_images")
        if not isinstance(kernels, list) or not [x for x in kernels if str(x).strip()]:
            return ChangeStatus.FAIL, "No detected kernel image is recorded; fail-closed."
        rootfs = change.payload.get("rootfs")
        if not isinstance(rootfs, list) or not [x for x in rootfs if str(x).strip()]:
            return ChangeStatus.FAIL, "No target root filesystem layer is recorded; fail-closed."
        mechanism = str(change.payload.get("initramfs_mechanism", "")).strip()
        if mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "No supported distro-native initramfs mechanism was identified."
        if change.payload.get("protect_last_viable_kernel") is not True:
            return ChangeStatus.FAIL, "Last viable kernel protection is mandatory."
        if change.payload.get("regenerate_initramfs") is not True:
            return ChangeStatus.FAIL, "Kernel/initramfs plan contains no requested operation."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 28 kernel/initramfs plans must remain staging-only."
        return ChangeStatus.PASS, "Kernel/initramfs plan is source-hash locked, last-kernel protected and staging-only. Apply must verify the native tool inside the selected rootfs before execution."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "hardware_package":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Firmware/driver plan is not locked to a valid source SHA-256."
        package = str(change.payload.get("package", "")).strip()
        kind = str(change.payload.get("hardware_kind", "")).strip()
        if not package or kind not in {"Firmware / microcode", "Driver / DKMS"}:
            return ChangeStatus.FAIL, "Hardware package is not tied to supported manifest-backed firmware/driver evidence."
        rootfs = change.payload.get("rootfs")
        if not isinstance(rootfs, list) or not [x for x in rootfs if str(x).strip()]:
            return ChangeStatus.FAIL, "No target root filesystem layer is recorded; fail-closed."
        mechanism = str(change.payload.get("initramfs_mechanism", "")).strip()
        if mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "No supported distro-native initramfs mechanism was identified."
        if str(change.payload.get("operation", "")) != "re_resolve":
            return ChangeStatus.FAIL, "Firmware/driver plan contains no supported explicit operation."
        if change.payload.get("require_signed_repository_metadata") is not True:
            return ChangeStatus.FAIL, "Signed repository metadata verification is mandatory for hardware package resolution."
        if change.payload.get("require_dependency_resolution") is not True:
            return ChangeStatus.FAIL, "Dependency resolution is mandatory for hardware package changes."
        if change.payload.get("protect_last_viable_kernel") is not True:
            return ChangeStatus.FAIL, "Last viable kernel protection is mandatory for firmware/driver changes."
        if change.payload.get("regenerate_initramfs") is not True:
            return ChangeStatus.FAIL, "Initramfs regeneration is mandatory for this staged hardware plan."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 29 firmware/driver plans must remain staging-only."
        return ChangeStatus.PASS, "Firmware/driver plan is source-hash locked, manifest-backed, repository/dependency gated, initramfs-protected and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "rootfs_squashfs":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Rootfs plan is not locked to a valid source SHA-256."
        layer = str(change.payload.get("layer_path", "")).strip()
        if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Rootfs plan is not tied to an explicit detected SquashFS layer."
        source_compression = str(change.payload.get("source_compression", "")).strip().casefold()
        target_compression = str(change.payload.get("target_compression", "")).strip().casefold()
        if source_compression not in {"xz", "zstd", "gzip", "lz4", "lzo"}:
            return ChangeStatus.FAIL, "Source SquashFS compression was not identified safely."
        if target_compression not in {"xz", "zstd", "gzip", "lz4", "lzo"}:
            return ChangeStatus.FAIL, "Requested SquashFS compression is outside the supported staging set."
        if str(change.payload.get("operation", "")) != "repack":
            return ChangeStatus.FAIL, "Rootfs plan contains no supported explicit operation."
        if change.payload.get("preserve_block_size") is not True:
            return ChangeStatus.FAIL, "Preserving the detected SquashFS block size is mandatory at this gate."
        if change.payload.get("require_unsquashfs_verification") is not True or change.payload.get("require_mksquashfs_verification") is not True:
            return ChangeStatus.FAIL, "SquashFS extract/repack tool verification is mandatory before apply."
        if change.payload.get("preserve_unrelated") is not True or change.payload.get("source_read_only") is not True:
            return ChangeStatus.FAIL, "Rootfs plan must preserve unrelated source content and keep the selected ISO read-only."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 30 rootfs/SquashFS plans must remain staging-only."
        return ChangeStatus.PASS, "Rootfs/SquashFS plan is source-hash locked, explicit-layer bound, tool-verification gated, preservation-first and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "immutable_runtime":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Immutable runtime plan is not locked to a valid source SHA-256."
        base_layer = str(change.payload.get("base_layer", "")).strip()
        if not base_layer.startswith("/") or not base_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Immutable runtime plan is not tied to an explicit SquashFS base layer."
        if str(change.payload.get("runtime_mode", "")) != "volatile_overlay":
            return ChangeStatus.FAIL, "Only the explicitly staged volatile OverlayFS runtime mode is supported at this gate."
        if str(change.payload.get("writable_layer", "")) != "tmpfs":
            return ChangeStatus.FAIL, "Volatile OverlayFS requires a tmpfs writable upper/work layer at this gate."
        if str(change.payload.get("persistence_policy", "")) != "volatile":
            return ChangeStatus.FAIL, "Alpha 31 supports only explicit volatile persistence; controlled persistence is a later gate."
        if change.payload.get("runtime_changes_survive_reboot") is not False:
            return ChangeStatus.FAIL, "Volatile runtime plans must state explicitly that runtime changes do not survive reboot."
        mechanism = str(change.payload.get("initramfs_mechanism", "")).strip()
        if mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "No supported distro-native initramfs mechanism was identified."
        if change.payload.get("require_initramfs_integration") is not True or change.payload.get("require_boot_integration") is not True:
            return ChangeStatus.FAIL, "Initramfs and boot integration verification are mandatory for immutable runtime plans."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Immutable runtime plans must keep the selected ISO read-only and preserve unrelated content."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 31 immutable runtime plans must remain staging-only."
        return ChangeStatus.PASS, "Immutable runtime plan is source-hash locked, read-only-rootfs bound, volatile OverlayFS/tmpfs explicit, reboot-survival explicit, integration-gated and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "controlled_persistence":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Controlled persistence plan is not locked to a valid source SHA-256."
        base_layer = str(change.payload.get("base_layer", "")).strip()
        if not base_layer.startswith("/") or not base_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Controlled persistence plan is not tied to an explicit SquashFS base layer."
        if str(change.payload.get("runtime_mode", "")) != "volatile_overlay_with_controlled_persistence" or str(change.payload.get("writable_layer", "")) != "tmpfs":
            return ChangeStatus.FAIL, "Controlled persistence must retain the volatile OverlayFS/tmpfs runtime model."
        if str(change.payload.get("persistence_policy", "")) != "selected_directories":
            return ChangeStatus.FAIL, "Only selected-directory persistence is supported at this gate."
        directories = change.payload.get("persistent_directories")
        if not isinstance(directories, list) or not directories:
            return ChangeStatus.FAIL, "At least one controlled persistent directory is required."
        blocked = ("/proc", "/sys", "/dev", "/run", "/boot", "/efi")
        seen: set[str] = set()
        for raw in directories:
            path = str(raw).strip()
            if not path.startswith("/") or any(ch in path for ch in ("\r", "\n", "\x00")):
                return ChangeStatus.FAIL, "Persistent directories must be absolute Linux paths without control characters."
            parts = [part for part in path.split("/") if part]
            if ".." in parts or path == "/" or any(path == prefix or path.startswith(prefix + "/") for prefix in blocked):
                return ChangeStatus.FAIL, "Persistent directory list contains an unsafe root, boot, pseudo-filesystem or traversal path."
            if path in seen:
                return ChangeStatus.FAIL, "Persistent directory list contains duplicate paths."
            seen.add(path)
        if change.payload.get("selected_directories_survive_reboot") is not True or change.payload.get("unlisted_runtime_changes_survive_reboot") is not False:
            return ChangeStatus.FAIL, "Reboot survival semantics must be explicit: selected directories persist and unlisted runtime changes do not."
        if str(change.payload.get("backing_storage", "")) != "dedicated_volume" or str(change.payload.get("volume_scope", "")) != "target_system":
            return ChangeStatus.FAIL, "Controlled persistence must use an explicit dedicated target-system volume plan."
        size = change.payload.get("volume_size_mib")
        if not isinstance(size, int) or isinstance(size, bool) or not 256 <= size <= 1048576:
            return ChangeStatus.FAIL, "Persistent volume size must be between 256 MiB and 1 TiB."
        if str(change.payload.get("filesystem", "")) != "ext4":
            return ChangeStatus.FAIL, "Alpha 32 controlled persistence supports only explicitly staged ext4 volumes."
        label = str(change.payload.get("volume_label", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,15}", label):
            return ChangeStatus.FAIL, "Persistent volume label must be a safe 1–16 character ASCII label."
        mechanism = str(change.payload.get("initramfs_mechanism", "")).strip()
        if mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "No supported distro-native initramfs mechanism was identified."
        if change.payload.get("require_initramfs_integration") is not True or change.payload.get("require_boot_integration") is not True or change.payload.get("require_mount_verification") is not True:
            return ChangeStatus.FAIL, "Initramfs, boot and mount verification are mandatory for controlled persistence."
        if change.payload.get("do_not_repartition_source_iso") is not True or change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Controlled persistence must not repartition the source ISO and must preserve unrelated source content."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 32 controlled persistence plans must remain staging-only."
        return ChangeStatus.PASS, "Controlled persistence plan is source-hash locked, selected-directory scoped, target-volume bounded, reboot-survival explicit, integration-gated and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "runtime_integration":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Runtime integration plan is not locked to a valid source SHA-256."
        base_layer = str(change.payload.get("base_layer", "")).strip()
        if not base_layer.startswith("/") or not base_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Runtime integration plan is not tied to an explicit SquashFS base layer."
        target = str(change.payload.get("integration_target", "")).strip()
        if target not in {"volatile_overlay", "controlled_persistence"}:
            return ChangeStatus.FAIL, "Runtime integration target is not one of the supported explicit modes."
        for field, label in (("boot_config_files", "boot configuration"), ("kernel_images", "kernel"), ("initramfs_images", "initramfs")):
            values = change.payload.get(field)
            if not isinstance(values, list) or not values:
                return ChangeStatus.FAIL, f"Runtime integration plan has no explicit {label} evidence."
            for raw in values:
                path = str(raw).strip()
                if not path.startswith("/") or any(ch in path for ch in ("\r", "\n", "\x00")) or ".." in [part for part in path.split("/") if part]:
                    return ChangeStatus.FAIL, f"Runtime integration plan contains unsafe {label} path evidence."
        mechanism = str(change.payload.get("initramfs_mechanism", "")).strip()
        if mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "No supported distro-native initramfs mechanism was identified."
        if str(change.payload.get("boot_policy", "")) != "preserve_detected_boot_structure" or change.payload.get("require_boot_config_reverification") is not True:
            return ChangeStatus.FAIL, "Detected boot structure preservation and boot-config re-verification are mandatory."
        if change.payload.get("require_kernel_binding") is not True:
            return ChangeStatus.FAIL, "Runtime integration must remain bound to the explicitly detected kernel evidence."
        if str(change.payload.get("initramfs_policy", "")) != "verify_hook_then_regenerate":
            return ChangeStatus.FAIL, "Runtime integration must verify the initramfs hook before regeneration."
        if change.payload.get("require_initramfs_hook_verification") is not True or change.payload.get("require_initramfs_regeneration") is not True:
            return ChangeStatus.FAIL, "Initramfs hook verification and regeneration are mandatory."
        if target == "volatile_overlay":
            if str(change.payload.get("mount_policy", "")) != "none" or change.payload.get("require_mount_verification") is not False:
                return ChangeStatus.FAIL, "Volatile OverlayFS integration must not invent a persistent mount."
            if change.payload.get("runtime_changes_survive_reboot") is not False:
                return ChangeStatus.FAIL, "Volatile integration must state that runtime changes do not survive reboot."
        else:
            if str(change.payload.get("mount_policy", "")) != "resolve_label_or_uuid_before_persistent_binds" or change.payload.get("require_mount_verification") is not True:
                return ChangeStatus.FAIL, "Controlled persistence requires label/UUID mount resolution and verification before persistent binds."
            if change.payload.get("selected_persistence_only") is not True:
                return ChangeStatus.FAIL, "Controlled persistence integration must remain limited to explicitly selected persistent data."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Runtime integration must keep the selected ISO read-only and preserve unrelated source content."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 33 runtime integration plans must remain staging-only."
        return ChangeStatus.PASS, "Runtime integration plan is source-hash locked, exact-evidence bound, boot-preserving, initramfs-regeneration gated, mount-policy explicit and staging-only."
    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_locale":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Locale/language plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_locale_verified") is not True:
            return ChangeStatus.FAIL, "Locale/language plan lacks verified rootfs locale evidence."
        if str(change.payload.get("operation", "")) != "configure_lang":
            return ChangeStatus.FAIL, "Unsupported locale/language operation."
        target = str(change.payload.get("target_lang", "")).strip()
        locale_re = r"(?:C|POSIX|C\.UTF-8|[A-Za-z]{2,3}_[A-Za-z]{2}(?:\.[A-Za-z0-9_-]+)?(?:@[A-Za-z0-9_-]+)?)"
        if not re.fullmatch(locale_re, target):
            return ChangeStatus.FAIL, "Target LANG value is not a safe locale identifier."
        config_path = str(change.payload.get("locale_config_path", "")).strip()
        if config_path not in {"/etc/default/locale", "/etc/locale.conf", "/etc/locale.gen"}:
            return ChangeStatus.FAIL, "Locale/language plan is not bound to supported rootfs locale evidence."
        evidence_layer = str(change.payload.get("locale_config_layer", "")).strip()
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Locale/language plan is not bound to explicit SquashFS locale evidence."
        if change.payload.get("require_locale_availability_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target locale availability must be verified again before apply."
        if change.payload.get("preserve_language_and_lc_overrides") is not True:
            return ChangeStatus.FAIL, "Alpha 40 must preserve LANGUAGE/LC_* overrides unless separately configured later."
        if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Locale/language plan must not read or stage credential secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Locale/language plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 40 locale/language plans must remain staging-only."
        return ChangeStatus.PASS, "Locale/language plan is source-hash locked, rootfs-evidence bound, locale-availability gated, override-preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_keyboard":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Keyboard layout plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_keyboard_verified") is not True:
            return ChangeStatus.FAIL, "Keyboard layout plan lacks verified rootfs keyboard evidence."
        if str(change.payload.get("operation", "")) != "configure_layout":
            return ChangeStatus.FAIL, "Unsupported keyboard layout operation."
        target = str(change.payload.get("target_layout", "")).strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", target):
            return ChangeStatus.FAIL, "Target keyboard layout is not a safe XKB layout identifier."
        config_path = str(change.payload.get("keyboard_config_path", "")).strip()
        if config_path not in {"/etc/default/keyboard", "/etc/vconsole.conf"}:
            return ChangeStatus.FAIL, "Keyboard layout plan is not bound to supported rootfs keyboard evidence."
        evidence_layer = str(change.payload.get("keyboard_config_layer", "")).strip()
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Keyboard layout plan is not bound to explicit SquashFS keyboard evidence."
        if change.payload.get("require_layout_availability_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target keyboard layout availability must be verified again before apply."
        if change.payload.get("preserve_model_variant_options") is not True:
            return ChangeStatus.FAIL, "Keyboard layout plan must preserve existing model/variant/options at this gate."
        if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Keyboard layout plan must not read or stage credential secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Keyboard layout plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 41 keyboard layout plans must remain staging-only."
        return ChangeStatus.PASS, "Keyboard layout plan is source-hash locked, rootfs-evidence bound, layout-availability gated, model/variant/options-preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_timezone":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Timezone plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_timezone_verified") is not True:
            return ChangeStatus.FAIL, "Timezone plan lacks verified rootfs timezone evidence."
        if str(change.payload.get("operation", "")) != "configure_timezone":
            return ChangeStatus.FAIL, "Unsupported timezone operation."
        target = str(change.payload.get("target_timezone", "")).strip()
        if (not target or len(target) > 128 or target.startswith("/") or
                not re.fullmatch(r"[A-Za-z0-9._+\-/]+", target) or
                any(part in {"", ".", ".."} for part in target.split("/"))):
            return ChangeStatus.FAIL, "Target timezone is not a safe IANA-style identifier."
        config_path = str(change.payload.get("timezone_config_path", "")).strip()
        if config_path not in {"/etc/timezone", "/etc/default/timezone", "/etc/localtime"}:
            return ChangeStatus.FAIL, "Timezone plan is not bound to supported rootfs timezone evidence."
        evidence_layer = str(change.payload.get("timezone_config_layer", "")).strip()
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Timezone plan is not bound to explicit SquashFS timezone evidence."
        if change.payload.get("require_zoneinfo_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target zoneinfo availability must be verified again before apply."
        if change.payload.get("preserve_hwclock_rtc_policy") is not True:
            return ChangeStatus.FAIL, "Timezone plan must preserve RTC/hardware-clock policy at this gate."
        if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Timezone plan must not read or stage credential secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Timezone plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 42 timezone plans must remain staging-only."
        return ChangeStatus.PASS, "Timezone plan is source-hash locked, rootfs-evidence bound, zoneinfo-verification gated, RTC-policy preserving and staging-only."


    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_network_dns":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Networking plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_network_dns_verified") is not True:
            return ChangeStatus.FAIL, "Networking plan lacks verified target-rootfs network evidence."

        gate_version = str(change.payload.get("gate_version", "")).strip().casefold()
        if gate_version == "alpha51":
            for forbidden_key in ("password", "password_hash", "secret", "token", "wifi_password", "vpn_password", "psk", "private_key", "recovery_secret"):
                if change.payload.get(forbidden_key) not in (None, "", False, [], {}):
                    return ChangeStatus.FAIL, "Networking plan must never serialize credential/secret material."
            supported_states = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
            capability = str(change.payload.get("capability_status", "UNKNOWN"))
            if capability not in supported_states:
                return ChangeStatus.FAIL, f"Networking capability is {capability}; fail-closed."
            if str(change.payload.get("analysis_scope", "")) != "target_iso_rootfs":
                return ChangeStatus.FAIL, "Networking plan is not scoped exclusively to the target ISO rootfs."
            backend = str(change.payload.get("network_backend", "")).strip()
            if backend not in {"NetworkManager", "netplan", "ifupdown", "systemd-networkd"}:
                return ChangeStatus.FAIL, "Networking plan is not bound to a supported verified target backend."
            backend_path = str(change.payload.get("backend_config_path", "")).strip()
            backend_layer = str(change.payload.get("backend_config_layer", "")).strip()
            managed_path = str(change.payload.get("managed_config_path", "")).strip()
            if not backend_path.startswith("/") or not managed_path.startswith("/"):
                return ChangeStatus.FAIL, "Networking plan lacks explicit target-rootfs backend/managed paths."
            if not backend_layer.startswith("/") or not backend_layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "Networking plan is not bound to an explicit SquashFS backend evidence layer."
            if change.payload.get("require_backend_specific_apply_verification") is not True:
                return ChangeStatus.FAIL, "Backend-specific apply verification is mandatory."
            if change.payload.get("require_target_path_reverification_before_apply") is not True:
                return ChangeStatus.FAIL, "Managed network target path must be re-verified before apply."
            if change.payload.get("require_syntax_validation_before_apply") is not True:
                return ChangeStatus.FAIL, "Generated network syntax must be validated before apply."
            if change.payload.get("host_network_accessed") is not False:
                return ChangeStatus.FAIL, "Windows/WSL host networking must never be used as target-network evidence."
            if change.payload.get("connection_profiles_inspected") is not False or change.payload.get("connection_profile_contents_read") is not False:
                return ChangeStatus.FAIL, "Existing NetworkManager profile contents must remain unread at this gate."
            if change.payload.get("wifi_vpn_secrets_read") is not False:
                return ChangeStatus.FAIL, "Wi-Fi/VPN credentials must never be read."
            if change.payload.get("credential_secret_read") is not False or change.payload.get("credential_secret_staged") is not False:
                return ChangeStatus.FAIL, "Credential secrets must not be read or staged."
            if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
                return ChangeStatus.FAIL, "Networking plan contains or reports secret material."
            if change.payload.get("ipv6_exposed") is not False or change.payload.get("ipv6_supported_by_gate") is not False:
                return ChangeStatus.FAIL, "Alpha 51 must keep IPv6 controls blocked until separately implemented and validated."
            if change.payload.get("preserve_existing_profiles") is not True or change.payload.get("preserve_unrelated_routes") is not True or change.payload.get("preserve_hostname") is not True:
                return ChangeStatus.FAIL, "Networking plan must preserve unrelated profiles, routes and hostname."
            if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
                return ChangeStatus.FAIL, "Networking plan must keep the source ISO read-only and preserve unrelated configuration."
            if change.payload.get("stage_only") is not True:
                return ChangeStatus.FAIL, "Alpha 51 networking plans must remain staging-only."

            operation = str(change.payload.get("operation", "")).strip()
            allowed = {str(x) for x in (change.payload.get("supported_operations") or []) if str(x).strip()}
            if operation not in allowed:
                return ChangeStatus.FAIL, "Requested networking operation is not in the target capability set."

            profile_name = str(change.payload.get("target_profile_name", "")).strip()
            interface_name = str(change.payload.get("target_interface", "")).strip()
            if interface_name and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface_name):
                return ChangeStatus.FAIL, "Invalid target interface name."
            if backend == "NetworkManager" and operation in {"configure_dns_servers", "configure_dhcp_ipv4", "configure_static_ipv4", "create_networkmanager_profile"}:
                if not profile_name or len(profile_name) > 64 or any(ch in profile_name for ch in ("/", "\\", "\r", "\n", "\x00", ":")):
                    return ChangeStatus.FAIL, "NetworkManager operation lacks a safe managed profile name."

            servers = change.payload.get("target_dns_servers")
            if not isinstance(servers, list) or len(servers) > 4:
                return ChangeStatus.FAIL, "Networking plan DNS list is malformed."
            normalized: list[str] = []
            try:
                for raw in servers:
                    address = ipaddress.ip_address(str(raw).strip())
                    if address.version != 4:
                        return ChangeStatus.FAIL, "IPv6 is not supported by the Alpha 51 configuration gate."
                    value = str(address)
                    if value in normalized:
                        return ChangeStatus.FAIL, "Networking plan contains duplicate DNS servers."
                    normalized.append(value)
            except ValueError:
                return ChangeStatus.FAIL, "Networking plan contains an invalid DNS server IP address."

            if operation == "configure_dns_servers":
                if str(change.payload.get("dns_status", "UNKNOWN")) not in supported_states or not normalized:
                    return ChangeStatus.FAIL, "DNS configuration is not capability-verified or has no DNS servers."
                if str(change.payload.get("ipv4_method", "")) != "preserve":
                    return ChangeStatus.FAIL, "DNS-only operation must preserve IPv4 addressing mode."
            elif operation == "configure_dhcp_ipv4":
                if str(change.payload.get("addressing_status", "UNKNOWN")) not in supported_states:
                    return ChangeStatus.FAIL, "DHCP capability is not verified."
                if str(change.payload.get("ipv4_method", "")) != "auto":
                    return ChangeStatus.FAIL, "DHCP plan must explicitly request automatic IPv4."
                if change.payload.get("target_ipv4_address") or change.payload.get("target_gateway"):
                    return ChangeStatus.FAIL, "DHCP plan must not carry static address/gateway values."
            elif operation == "configure_static_ipv4":
                if str(change.payload.get("addressing_status", "UNKNOWN")) not in supported_states:
                    return ChangeStatus.FAIL, "Static IPv4 capability is not verified."
                if str(change.payload.get("ipv4_method", "")) != "manual":
                    return ChangeStatus.FAIL, "Static IPv4 plan must explicitly request manual addressing."
                try:
                    addr = ipaddress.ip_interface(str(change.payload.get("target_ipv4_address", "")).strip())
                    gateway = ipaddress.ip_address(str(change.payload.get("target_gateway", "")).strip())
                except ValueError:
                    return ChangeStatus.FAIL, "Static IPv4 address/prefix or gateway is invalid."
                if addr.version != 4 or gateway.version != 4:
                    return ChangeStatus.FAIL, "IPv6 is not supported by the Alpha 51 configuration gate."
            elif operation == "create_networkmanager_profile":
                if backend != "NetworkManager" or str(change.payload.get("networkmanager_profile_status", "UNKNOWN")) not in supported_states:
                    return ChangeStatus.FAIL, "NetworkManager profile creation is not capability-verified."
                if str(change.payload.get("profile_connection_type", "")) != "802-3-ethernet":
                    return ChangeStatus.FAIL, "Alpha 51 creates only credential-free Ethernet profiles."
                if str(change.payload.get("ipv4_method", "")) != "auto":
                    return ChangeStatus.FAIL, "Managed NetworkManager profile creation must start with DHCP IPv4 at this gate."
                if not isinstance(change.payload.get("autoconnect_enabled"), bool):
                    return ChangeStatus.FAIL, "Managed NetworkManager profile must explicitly state autoconnect policy."
            elif operation == "set_networkmanager_autoconnect":
                if backend != "NetworkManager" or str(change.payload.get("networkmanager_profile_status", "UNKNOWN")) not in supported_states:
                    return ChangeStatus.FAIL, "NetworkManager profile autoconnect is not capability-verified."
                filename = str(change.payload.get("existing_profile_filename", "")).strip()
                if not filename.endswith(".nmconnection") or "/" in filename or "\\" in filename:
                    return ChangeStatus.FAIL, "Autoconnect plan is not bound to a safe existing NetworkManager profile filename."
                if change.payload.get("require_profile_reverification_before_apply") is not True:
                    return ChangeStatus.FAIL, "Existing NetworkManager profile must be re-verified before apply."
                if not isinstance(change.payload.get("autoconnect_enabled"), bool):
                    return ChangeStatus.FAIL, "Autoconnect plan lacks an explicit boolean policy."
            else:
                return ChangeStatus.FAIL, "Unsupported Alpha 51 networking operation."

            return ChangeStatus.PASS, "Networking / NetworkManager / DNS plan is source-hash locked, target-rootfs capability bound, syntax/apply-verification gated, host-network isolated, secret-preserving and staging-only."

        # Alpha 43 compatibility: retain the previously verified DNS-only plan contract.
        if str(change.payload.get("operation", "")) != "configure_dns_servers":
            return ChangeStatus.FAIL, "Unsupported networking/DNS operation."
        backend = str(change.payload.get("network_backend", "")).strip()
        if backend not in {"NetworkManager", "ifupdown", "systemd-networkd"}:
            return ChangeStatus.FAIL, "Networking/DNS plan is not bound to a supported verified network backend."
        backend_path = str(change.payload.get("backend_config_path", "")).strip()
        if backend_path not in {"/etc/NetworkManager/NetworkManager.conf", "/etc/network/interfaces", "/etc/systemd/networkd.conf"}:
            return ChangeStatus.FAIL, "Networking/DNS plan is not bound to explicit safe backend evidence."
        backend_layer = str(change.payload.get("backend_config_layer", "")).strip()
        resolver_path = str(change.payload.get("resolver_path", "")).strip()
        resolver_layer = str(change.payload.get("resolver_layer", "")).strip()
        if not backend_layer.startswith("/") or not backend_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Networking/DNS plan is not bound to explicit SquashFS backend evidence."
        if resolver_path not in {"/etc/systemd/resolved.conf", "/etc/resolv.conf"}:
            return ChangeStatus.FAIL, "Networking/DNS plan lacks safe resolver path evidence."
        if not resolver_layer.startswith("/") or not resolver_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Networking/DNS plan is not bound to explicit SquashFS resolver evidence."
        servers = change.payload.get("target_dns_servers")
        if not isinstance(servers, list) or not (1 <= len(servers) <= 4):
            return ChangeStatus.FAIL, "Networking/DNS plan must contain 1–4 DNS server IP addresses."
        normalized: list[str] = []
        try:
            for raw in servers:
                value = str(ipaddress.ip_address(str(raw).strip()))
                if value in normalized:
                    return ChangeStatus.FAIL, "Networking/DNS plan contains duplicate DNS servers."
                normalized.append(value)
        except ValueError:
            return ChangeStatus.FAIL, "Networking/DNS plan contains an invalid DNS server IP address."
        if change.payload.get("require_backend_specific_apply_verification") is not True:
            return ChangeStatus.FAIL, "Networking/DNS apply mapping must be re-verified for the detected backend."
        if change.payload.get("preserve_connection_profiles") is not True or change.payload.get("preserve_ip_dhcp_routes") is not True:
            return ChangeStatus.FAIL, "Networking/DNS plan must preserve connection profiles, addressing and routes at this gate."
        if change.payload.get("connection_profiles_inspected") is not False or change.payload.get("wifi_vpn_secrets_read") is not False:
            return ChangeStatus.FAIL, "Networking/DNS evidence must not inspect connection profiles or Wi-Fi/VPN secrets."
        if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Networking/DNS plan must not read or stage credential secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Networking/DNS plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 43 networking/DNS plans must remain staging-only."
        return ChangeStatus.PASS, "Networking / DNS plan is source-hash locked, rootfs-evidence bound, backend-apply-verification gated, connection-profile/secret preserving and staging-only."


    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_services":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Services/systemd plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_services_verified") is not True:
            return ChangeStatus.FAIL, "Services/systemd plan lacks verified rootfs systemd evidence."
        if str(change.payload.get("init_system", "")).strip() != "systemd":
            return ChangeStatus.FAIL, "Services/systemd plan is not bound to a verified systemd rootfs."
        operation = str(change.payload.get("operation", "")).strip()
        if operation not in {"enable_service", "disable_service"}:
            return ChangeStatus.FAIL, "Unsupported services/systemd operation."
        unit = str(change.payload.get("service_unit", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,120}\.service", unit) or "/" in unit:
            return ChangeStatus.FAIL, "Target service unit name is unsafe or unsupported."
        vendor_path = str(change.payload.get("vendor_unit_path", "")).strip()
        if vendor_path not in {"/usr/lib/systemd/system", "/lib/systemd/system"}:
            return ChangeStatus.FAIL, "Services/systemd plan is not bound to supported vendor-unit evidence."
        vendor_layer = str(change.payload.get("vendor_unit_layer", "")).strip()
        if not vendor_layer.startswith("/") or not vendor_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Services/systemd plan is not bound to explicit SquashFS unit-directory evidence."
        if change.payload.get("require_target_unit_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target service unit existence must be verified again before apply."
        if change.payload.get("preserve_unit_file_contents") is not True or change.payload.get("preserve_timers_targets") is not True:
            return ChangeStatus.FAIL, "Services/systemd plan must preserve unit contents, timers and targets at this gate."
        if change.payload.get("unit_contents_read") is not False or change.payload.get("enablement_links_read") is not False:
            return ChangeStatus.FAIL, "Services/systemd evidence must not read unit contents or enablement symlink targets at this gate."
        if change.payload.get("service_secrets_read") is not False or change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Services/systemd plan must not read or stage service credentials or secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Services/systemd plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 44 services/systemd plans must remain staging-only."
        return ChangeStatus.PASS, "Services / systemd plan is source-hash locked, rootfs-evidence bound, target-unit-verification gated, unit-content preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_timers":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Timers/systemd plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_timers_verified") is not True:
            return ChangeStatus.FAIL, "Timers/systemd plan lacks verified rootfs systemd evidence."
        if str(change.payload.get("init_system", "")).strip() != "systemd":
            return ChangeStatus.FAIL, "Timers/systemd plan is not bound to a verified systemd rootfs."
        operation = str(change.payload.get("operation", "")).strip()
        if operation not in {"enable_timer", "disable_timer"}:
            return ChangeStatus.FAIL, "Unsupported timers/systemd operation."
        unit = str(change.payload.get("timer_unit", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,120}\.timer", unit) or "/" in unit:
            return ChangeStatus.FAIL, "Target timer unit name is unsafe or unsupported."
        vendor_path = str(change.payload.get("vendor_unit_path", "")).strip()
        if vendor_path not in {"/usr/lib/systemd/system", "/lib/systemd/system"}:
            return ChangeStatus.FAIL, "Timers/systemd plan is not bound to supported vendor-unit evidence."
        vendor_layer = str(change.payload.get("vendor_unit_layer", "")).strip()
        if not vendor_layer.startswith("/") or not vendor_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Timers/systemd plan is not bound to explicit SquashFS unit-directory evidence."
        if change.payload.get("require_target_timer_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target timer unit existence must be verified again before apply."
        if change.payload.get("preserve_timer_file_contents") is not True or change.payload.get("preserve_services_targets") is not True:
            return ChangeStatus.FAIL, "Timers/systemd plan must preserve timer contents, services and targets at this gate."
        if change.payload.get("timer_contents_read") is not False or change.payload.get("enablement_links_read") is not False:
            return ChangeStatus.FAIL, "Timers/systemd evidence must not read timer contents or enablement symlink targets at this gate."
        if change.payload.get("service_secrets_read") is not False or change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Timers/systemd plan must not read or stage service credentials or secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Timers/systemd plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 45 timers/systemd plans must remain staging-only."
        return ChangeStatus.PASS, "Timers / systemd plan is source-hash locked, rootfs-evidence bound, target-timer-verification gated, timer-content preserving and staging-only."


    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_targets":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Targets/startup plan requires a valid source SHA-256."
        if change.payload.get("rootfs_targets_verified") is not True:
            return ChangeStatus.FAIL, "Targets/startup plan requires verified read-only systemd rootfs evidence."
        if str(change.payload.get("init_system", "")).strip() != "systemd":
            return ChangeStatus.FAIL, "Targets/startup plan is not bound to verified systemd evidence."
        operation = str(change.payload.get("operation", "")).strip()
        if operation != "set_default_target":
            return ChangeStatus.FAIL, "Unsupported targets/startup operation."
        unit = str(change.payload.get("target_unit", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,120}\.target", unit) or "/" in unit:
            return ChangeStatus.FAIL, "Target must be a safe systemd .target unit name."
        vendor_path = str(change.payload.get("vendor_unit_path", "")).strip()
        vendor_layer = str(change.payload.get("vendor_unit_layer", "")).strip()
        if vendor_path not in {"/usr/lib/systemd/system", "/lib/systemd/system"}:
            return ChangeStatus.FAIL, "Targets/startup plan lacks supported systemd vendor-unit evidence."
        if not vendor_layer.startswith("/") or not vendor_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Targets/startup plan is not bound to explicit SquashFS systemd evidence."
        if change.payload.get("require_target_unit_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target .target unit existence must be verified again before apply."
        if change.payload.get("preserve_services_timers") is not True or change.payload.get("preserve_unit_file_contents") is not True:
            return ChangeStatus.FAIL, "Targets/startup plan must preserve services, timers and unit contents at this gate."
        if change.payload.get("target_contents_read") is not False or change.payload.get("default_target_symlink_read") is not False:
            return ChangeStatus.FAIL, "Targets/startup evidence must not read target contents or the default.target symlink target at this gate."
        if change.payload.get("service_secrets_read") is not False or change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "Targets/startup plan must not read or stage service credentials or secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Targets/startup plan must preserve the source and unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 46 targets/startup plans must remain staging-only."
        return ChangeStatus.PASS, "Targets / startup plan is source-hash locked, rootfs-evidence bound, target-unit-verification gated, service/timer preserving and staging-only."


    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_firewall":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Firewall plan requires a valid source SHA-256."
        if change.payload.get("rootfs_firewall_verified") is not True:
            return ChangeStatus.FAIL, "Firewall plan requires verified read-only rootfs firewall evidence."
        backend = str(change.payload.get("backend", "")).strip().casefold()
        if backend not in {"ufw", "firewalld", "nftables"}:
            return ChangeStatus.FAIL, "Firewall plan is not bound to a supported verified firewall backend."
        evidence_path = str(change.payload.get("backend_path", "")).strip()
        evidence_layer = str(change.payload.get("backend_layer", "")).strip()
        if not evidence_path.startswith("/") or not evidence_path:
            return ChangeStatus.FAIL, "Firewall plan lacks explicit backend path evidence."
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Firewall plan is not bound to explicit SquashFS backend evidence."
        operation = str(change.payload.get("operation", "")).strip()
        if operation not in {"enable_firewall", "disable_firewall"}:
            return ChangeStatus.FAIL, "Unsupported firewall operation."
        if change.payload.get("require_backend_apply_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Firewall backend/apply semantics must be verified again before apply."
        if change.payload.get("preserve_rule_contents") is not True or change.payload.get("preserve_ports_services_profiles") is not True:
            return ChangeStatus.FAIL, "Firewall plan must preserve existing rule contents and ports/services/application-profile policy at this gate."
        for key in ("rule_contents_read", "ports_services_policy_read", "application_profiles_read", "firewall_secrets_read", "secret_read", "secret_staged"):
            if change.payload.get(key) is not False:
                return ChangeStatus.FAIL, "Firewall plan must not read or stage firewall rules, policy details or secrets at this gate."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Firewall plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 47 firewall plans must remain staging-only."
        return ChangeStatus.PASS, "Firewall plan is source-hash locked, rootfs-evidence bound, backend-apply-verification gated, rule-content preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "firewall_rule" and str(change.payload.get("gate_version", "")) == "alpha60":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Firewall-rules plan is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_rootfs" or payload.get("rootfs_firewall_rules_verified") is not True:
            return ChangeStatus.FAIL, "Firewall-rules plan lacks verified target-rootfs capability evidence."
        if str(payload.get("capability_status") or "UNKNOWN") not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, "Firewall-rules capability is not safely verified for this target image."
        backend = str(payload.get("firewall_backend") or "").casefold()
        adapter = str(payload.get("rule_adapter") or "")
        expected_adapter = {"ufw": "ufw-additive-cli", "firewalld": "firewalld-permanent-cli"}.get(backend)
        if expected_adapter is None or adapter != expected_adapter:
            return ChangeStatus.FAIL, "Firewall-rules plan is not bound to a verified persistent additive firewall adapter."
        command_path = str(payload.get("rule_command_path") or "")
        command_layer = str(payload.get("rule_command_layer") or "")
        if not command_path.startswith("/") or not command_layer.startswith("/") or not command_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Firewall-rules plan lacks explicit target command-path/SquashFS evidence."
        if str(payload.get("operation") or "") != "deny_inbound_tcp_port":
            return ChangeStatus.FAIL, "Alpha 60 is limited to one explicit inbound TCP-port deny rule."
        port = payload.get("tcp_port")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            return ChangeStatus.FAIL, "Firewall-rules TCP port must be an integer from 1 through 65535."
        if str(payload.get("protocol") or "") != "tcp" or str(payload.get("direction") or "") != "in" or str(payload.get("action") or "") != "deny":
            return ChangeStatus.FAIL, "Alpha 60 firewall-rule scope must remain inbound TCP deny only."
        if str(payload.get("rule_scope") or "") != "single_inbound_tcp_port_deny":
            return ChangeStatus.FAIL, "Alpha 60 firewall-rule scope is broader than one inbound TCP-port deny."
        for key in ("existing_rule_contents_read", "ports_services_policy_read", "application_profiles_read", "firewall_secrets_read", "host_firewall_accessed"):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, "Firewall-rules planning must not read rule/policy/secrets or host firewall state."
        for key in (
            "preserve_existing_rules", "preserve_default_policy", "preserve_unrelated_firewall_policy",
            "requires_apply_time_conflict_check", "requires_backend_state_reverification",
            "require_rule_command_reverification_before_apply", "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"Firewall-rules safety requirement missing: {key}."
        return ChangeStatus.PASS, "Firewall rules plan is source-hash locked, target-backend/command-evidence bound, single-port scoped, conflict-reverification gated, host/secret isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_apparmor":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "AppArmor plan requires a valid source SHA-256."
        if change.payload.get("rootfs_apparmor_verified") is not True:
            return ChangeStatus.FAIL, "AppArmor plan requires verified read-only rootfs AppArmor evidence."
        backend = str(change.payload.get("backend", "")).strip().casefold()
        if backend != "apparmor":
            return ChangeStatus.FAIL, "AppArmor plan is not bound to verified AppArmor component evidence."
        evidence_path = str(change.payload.get("evidence_path", "")).strip()
        evidence_layer = str(change.payload.get("evidence_layer", "")).strip()
        if not evidence_path.startswith("/") or not evidence_path:
            return ChangeStatus.FAIL, "AppArmor plan lacks explicit component path evidence."
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "AppArmor plan is not bound to explicit SquashFS component evidence."
        operation = str(change.payload.get("operation", "")).strip()
        if operation not in {"enable_apparmor", "disable_apparmor"}:
            return ChangeStatus.FAIL, "Unsupported AppArmor operation."
        if change.payload.get("require_backend_apply_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "AppArmor boot/apply semantics must be verified again before apply."
        if change.payload.get("preserve_profiles") is not True or change.payload.get("preserve_parser_config") is not True:
            return ChangeStatus.FAIL, "AppArmor plan must preserve existing profiles and parser configuration at this gate."
        for key in ("profile_contents_read", "parser_config_read", "abstractions_tunables_read", "apparmor_secrets_read", "secret_read", "secret_staged"):
            if change.payload.get(key) is not False:
                return ChangeStatus.FAIL, "AppArmor plan must not read or stage policy/profile contents or secrets at this gate."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "AppArmor plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 48 AppArmor plans must remain staging-only."
        return ChangeStatus.PASS, "AppArmor plan is source-hash locked, rootfs-evidence bound, backend-apply-verification gated, profile-content preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_selinux":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "SELinux plan requires a valid source SHA-256."
        if change.payload.get("gate_version") != "alpha52" or change.payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "SELinux plan is not bound to the Alpha 52 target-ISO capability model."
        capability = str(change.payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"SELinux capability is {capability}; fail-closed staging is required."
        if change.payload.get("rootfs_selinux_verified") is not True:
            return ChangeStatus.FAIL, "SELinux plan requires verified target-rootfs capability evidence."
        if str(change.payload.get("operation") or "") != "set_selinux_mode":
            return ChangeStatus.FAIL, "Unsupported SELinux operation."
        target_mode = str(change.payload.get("target_mode") or "").casefold()
        if target_mode not in {"enforcing", "permissive", "disabled"}:
            return ChangeStatus.FAIL, "SELinux target mode must be enforcing, permissive or disabled."
        config_path = str(change.payload.get("config_path") or "")
        if config_path != "/etc/selinux/config":
            return ChangeStatus.FAIL, "SELinux plan must target the verified standard /etc/selinux/config path."
        config_layer = str(change.payload.get("config_layer") or "")
        package_install_required = change.payload.get("package_install_required") is True
        if config_layer and (not config_layer.startswith("/") or not config_layer.casefold().endswith(".squashfs")):
            return ChangeStatus.FAIL, "SELinux configuration evidence layer is not a valid target SquashFS layer."
        config_creation_required = change.payload.get("config_creation_required") is True
        if not config_layer and not package_install_required and not config_creation_required:
            return ChangeStatus.FAIL, "SELinux plan lacks an existing config layer and has no verified package/config creation requirement."

        packages = change.payload.get("required_packages")
        if not isinstance(packages, list):
            return ChangeStatus.FAIL, "SELinux package requirements must be an explicit list."
        if package_install_required:
            manager = str(change.payload.get("package_manager") or "").casefold()
            if manager not in {"apt", "dnf", "yum", "pacman"}:
                return ChangeStatus.FAIL, "SELinux package addition is not bound to a verified target package manager."
            if not packages or change.payload.get("package_requirements_staged") is not True:
                return ChangeStatus.FAIL, "SELinux package additions must be explicit and staged as requirements."
            if change.payload.get("require_signed_repository_metadata") is not True or change.payload.get("require_dependency_resolution") is not True:
                return ChangeStatus.FAIL, "SELinux package additions require signed metadata and dependency resolution before apply."
        elif change.payload.get("package_requirements_staged") not in {False, None} and not packages:
            return ChangeStatus.FAIL, "SELinux package staging flags are inconsistent."

        part3_requirements = change.payload.get("part3_requirements")
        if not isinstance(part3_requirements, list):
            return ChangeStatus.FAIL, "SELinux boot/kernel requirements must be represented as an explicit Part 3 dependency list."
        if change.payload.get("dependencies_visible") is not True or change.payload.get("dependencies_staged") is not True:
            return ChangeStatus.FAIL, "SELinux dependencies must be visible and staged in the central plan."
        if change.payload.get("delegate_boot_kernel_to_part3") is not True:
            return ChangeStatus.FAIL, "SELinux boot/kernel handling must be delegated to the existing Part 3 model."
        if any(change.payload.get(key) is not False for key in ("direct_boot_mutation", "direct_kernel_mutation", "direct_initramfs_mutation")):
            return ChangeStatus.FAIL, "SELinux Part 4 staging must not perform ad-hoc boot/kernel/initramfs mutation."
        if any(key in change.payload for key in ("kernel_args_append", "boot_file_write", "grub_write", "direct_boot_args")):
            return ChangeStatus.FAIL, "SELinux Part 4 payload contains forbidden direct boot-manipulation fields."
        if change.payload.get("part3_dependency_required") is True:
            if not part3_requirements or not any(str(item.get("model", "")).startswith("part3") for item in part3_requirements if isinstance(item, dict)):
                return ChangeStatus.FAIL, "SELinux plan declares a Part 3 dependency without explicit Part 3 requirements."

        configured = str(change.payload.get("configured_mode") or "unknown").casefold()
        relabel_required = change.payload.get("relabel_required") is True
        if target_mode in {"enforcing", "permissive"} and configured in {"disabled", "unknown"} and not relabel_required:
            return ChangeStatus.FAIL, "Enabling SELinux from disabled/unknown state requires an explicit relabel plan."
        if target_mode == "enforcing" and relabel_required and change.payload.get("relabel_before_enforcing") is not True:
            return ChangeStatus.FAIL, "SELinux enforcing activation must require relabel before enforcement when relabeling is needed."
        if change.payload.get("reboot_required") is not True or change.payload.get("require_post_boot_verification") is not True:
            return ChangeStatus.FAIL, "SELinux persistent mode changes require reboot and post-boot verification."

        if change.payload.get("preserve_existing_policies") is not True or change.payload.get("custom_policy_preserved") is not True:
            return ChangeStatus.FAIL, "Existing/custom SELinux policy must be preserved."
        if change.payload.get("policy_contents_read") is not False:
            return ChangeStatus.FAIL, "SELinux policy contents must not be read by the Alpha 52 capability gate."
        if change.payload.get("host_selinux_accessed") is not False or change.payload.get("host_security_state_accessed") is not False:
            return ChangeStatus.FAIL, "SELinux staging must not use Windows/WSL host SELinux state."
        if change.payload.get("secret_read") is not False or change.payload.get("secret_staged") is not False:
            return ChangeStatus.FAIL, "SELinux plan must not read or stage secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "SELinux plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 52 SELinux plans must remain staging-only."
        return ChangeStatus.PASS, "SELinux plan is source-hash locked, capability-driven, policy-preserving, dependency-explicit, Part-3 delegated, host-isolated and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_sysctl":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "sysctl plan requires a valid source SHA-256."
        if change.payload.get("rootfs_sysctl_verified") is not True:
            return ChangeStatus.FAIL, "sysctl plan requires verified read-only rootfs sysctl evidence."
        backend = str(change.payload.get("backend", "")).strip().casefold()
        if backend != "procps-sysctl":
            return ChangeStatus.FAIL, "sysctl plan is not bound to verified sysctl infrastructure evidence."
        evidence_path = str(change.payload.get("evidence_path", "")).strip()
        evidence_layer = str(change.payload.get("evidence_layer", "")).strip()
        if not evidence_path.startswith("/") or not evidence_path:
            return ChangeStatus.FAIL, "sysctl plan lacks explicit infrastructure path evidence."
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "sysctl plan is not bound to explicit SquashFS infrastructure evidence."
        operation = str(change.payload.get("operation", "")).strip()
        if operation != "set_integer_sysctl":
            return ChangeStatus.FAIL, "Unsupported sysctl operation."
        key = str(change.payload.get("sysctl_key", "")).strip()
        value = str(change.payload.get("sysctl_value", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", key) or "." not in key:
            return ChangeStatus.FAIL, "sysctl key is not a safe dotted kernel parameter name."
        if not re.fullmatch(r"-?[0-9]{1,10}", value):
            return ChangeStatus.FAIL, "Alpha 49 accepts only a single integer sysctl value."
        if change.payload.get("require_target_key_apply_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "sysctl target-key/apply semantics must be verified again before apply."
        if change.payload.get("preserve_existing_sysctl_config") is not True or change.payload.get("use_managed_dropin_on_apply") is not True:
            return ChangeStatus.FAIL, "sysctl plan must preserve existing configuration and use a managed drop-in on later apply."
        for key_name in ("config_contents_read", "runtime_values_read", "sysctl_secrets_read", "secret_read", "secret_staged"):
            if change.payload.get(key_name) is not False:
                return ChangeStatus.FAIL, "sysctl plan must not read existing sysctl values/config contents or stage secrets at this gate."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "sysctl plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 49 sysctl plans must remain staging-only."
        return ChangeStatus.PASS, "sysctl plan is source-hash locked, rootfs-evidence bound, target-key/apply-verification gated, existing-config preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_security_defaults":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Security defaults plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha53" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Security defaults plan is not bound to the Alpha 53 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Security defaults capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_security_defaults_verified") is not True:
            return ChangeStatus.FAIL, "Security defaults plan requires verified target-rootfs login security evidence."
        if str(payload.get("operation") or "") != "set_default_umask":
            return ChangeStatus.FAIL, "Unsupported Alpha 53 security-default operation."
        target_umask = str(payload.get("target_umask") or "")
        supported_umasks = {str(x) for x in (payload.get("supported_umasks") or [])}
        if target_umask not in {"022", "027", "077"} or target_umask not in supported_umasks:
            return ChangeStatus.FAIL, "Default login UMASK must be one of the verified allowlisted values 022, 027 or 077."
        if str(payload.get("backend") or "") != "shadow-utils-login.defs":
            return ChangeStatus.FAIL, "Security defaults plan is not bound to the verified login.defs backend."
        if str(payload.get("config_path") or "") != "/etc/login.defs":
            return ChangeStatus.FAIL, "Security defaults plan must target the verified /etc/login.defs path."
        layer = str(payload.get("config_layer") or "")
        if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Security defaults plan is not bound to explicit target SquashFS evidence."
        metadata = {str(x) for x in (payload.get("metadata_keys_read") or [])}
        if metadata != {"UMASK", "USERGROUPS_ENAB"}:
            return ChangeStatus.FAIL, "Alpha 53 may expose only allowlisted UMASK/USERGROUPS_ENAB metadata."
        if payload.get("require_target_directive_reverification_before_apply") is not True or payload.get("require_effective_session_semantics_verification_before_apply") is not True:
            return ChangeStatus.FAIL, "Security-default target directive and effective login/session semantics must be re-verified before apply."
        if payload.get("preserve_login_defs_unrelated") is not True or payload.get("preserve_pam_configuration") is not True or payload.get("preserve_account_policy") is not True:
            return ChangeStatus.FAIL, "Security defaults plan must preserve unrelated login.defs, PAM and account policy."
        for key in ("full_config_exposed", "credential_secret_read", "credential_secret_staged", "host_security_state_accessed", "secret_read", "secret_staged"):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, "Security defaults plan must not expose full configuration, credentials, secrets or host security state."
        if payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Security defaults plan must keep the source ISO read-only and preserve unrelated configuration."
        if payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 53 security-default plans must remain staging-only."
        return ChangeStatus.PASS, "Security defaults plan is source-hash locked, target-rootfs-evidence bound, UMASK-allowlisted, host-isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_config_overlay":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "System configuration overlay plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha54" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "System configuration overlay plan is not bound to the Alpha 54 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"System configuration overlay capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_overlay_verified") is not True or payload.get("profile_d_sourcing_verified") is not True:
            return ChangeStatus.FAIL, "System configuration overlay plan requires verified target profile.d sourcing evidence."
        if str(payload.get("backend") or "") != "profile.d":
            return ChangeStatus.FAIL, "System configuration overlay plan is not bound to the verified profile.d backend."
        if str(payload.get("profile_path") or "") != "/etc/profile" or str(payload.get("target_directory") or "") != "/etc/profile.d":
            return ChangeStatus.FAIL, "System configuration overlay plan must remain bound to /etc/profile and /etc/profile.d."
        for key in ("profile_layer", "target_directory_layer"):
            layer = str(payload.get(key) or "")
            if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "System configuration overlay plan is not bound to explicit target SquashFS evidence."
        if str(payload.get("operation") or "") != "add_managed_environment_overlay":
            return ChangeStatus.FAIL, "Unsupported Alpha 54 system-configuration overlay operation."
        overlay_name = str(payload.get("overlay_name") or "")
        variable = str(payload.get("environment_variable") or "")
        value = str(payload.get("public_nonsecret_value") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", overlay_name):
            return ChangeStatus.FAIL, "Overlay name is not a safe managed identifier."
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", variable):
            return ChangeStatus.FAIL, "Environment variable is not a safe uppercase identifier."
        if any(word in variable for word in ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH", "PRIVATE_KEY", "API_KEY")):
            return ChangeStatus.FAIL, "Secret/credential-like variables are not permitted in the public overlay gate."
        if not re.fullmatch(r"[A-Za-z0-9._:/@%+,-]{1,128}", value):
            return ChangeStatus.FAIL, "Overlay value must be a short non-secret literal without shell metacharacters."
        target_filename = str(payload.get("target_filename") or "")
        expected_filename = f"99-chromapress-{overlay_name}.sh"
        if target_filename != expected_filename:
            return ChangeStatus.FAIL, "Managed overlay filename does not match the Alpha 54 naming policy."
        existing = {str(x) for x in (payload.get("existing_entry_names") or [])}
        if target_filename in existing:
            return ChangeStatus.FAIL, "Managed overlay target already exists; preservation-first policy blocks overwrite."
        if payload.get("content_classification") != "public_nonsecret" or payload.get("generated_content_only") is not True or payload.get("arbitrary_shell_content_allowed") is not False:
            return ChangeStatus.FAIL, "Alpha 54 accepts only deterministic generated non-secret overlay content, never arbitrary shell text."
        if payload.get("require_target_file_absence_reverification_before_apply") is not True:
            return ChangeStatus.FAIL, "Target overlay filename absence must be re-verified before apply."
        if payload.get("preserve_existing_profile") is not True or payload.get("preserve_existing_dropins") is not True:
            return ChangeStatus.FAIL, "Existing /etc/profile and profile.d drop-ins must be preserved."
        for key in ("existing_dropin_contents_read", "host_configuration_accessed", "secret_read", "secret_staged"):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, "Overlay plan must not read existing drop-in contents, use host configuration, or read/stage secrets."
        if payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "System configuration overlay plan must keep the source ISO read-only and preserve unrelated configuration."
        if payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 54 system-configuration overlay plans must remain staging-only."
        return ChangeStatus.PASS, "System configuration overlay plan is source-hash locked, target-rootfs-evidence bound, managed-file collision checked, non-secret input validated, host-isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_autologin":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Autologin plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_autologin_verified") is not True:
            return ChangeStatus.FAIL, "Autologin plan lacks verified rootfs display-manager evidence."
        display_manager = str(change.payload.get("display_manager", "")).strip().casefold()
        if display_manager not in {"sddm", "lightdm", "gdm", "gdm3"}:
            return ChangeStatus.FAIL, "Autologin plan is not bound to a supported verified display manager."
        evidence_layer = str(change.payload.get("display_manager_layer", "")).strip()
        if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Autologin plan is not bound to explicit SquashFS display-manager evidence."
        operation = str(change.payload.get("operation", ""))
        if operation not in {"enable_autologin", "disable_autologin"}:
            return ChangeStatus.FAIL, "Unsupported autologin operation."
        target_user = str(change.payload.get("target_user", "")).strip()
        if operation == "enable_autologin":
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", target_user):
                return ChangeStatus.FAIL, "Autologin target user is not a safe Linux account name."
            if change.payload.get("require_target_user_verification_before_apply") is not True:
                return ChangeStatus.FAIL, "Autologin enablement must verify the target user again before apply."
        elif target_user:
            return ChangeStatus.FAIL, "Disable-autologin plans must not stage a target username."
        if change.payload.get("credential_secret_staged") is not False or change.payload.get("credential_secret_read") is not False:
            return ChangeStatus.FAIL, "Autologin plan must not read or stage password/token/credential secrets."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Autologin plan must keep the source ISO read-only and preserve unrelated login configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 39 autologin plans must remain staging-only."
        return ChangeStatus.PASS, "Autologin plan is source-hash locked, display-manager-evidence bound, credential-secret free, target-user verification gated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_machine_identity":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Hostname/machine identity plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_machine_identity_verified") is not True:
            return ChangeStatus.FAIL, "Hostname/machine identity plan lacks verified rootfs evidence."
        if str(change.payload.get("operation", "")) != "configure_hostname":
            return ChangeStatus.FAIL, "Unsupported hostname/machine identity operation."
        hostname = str(change.payload.get("target_hostname", "")).strip()
        if len(hostname) > 253 or not hostname:
            return ChangeStatus.FAIL, "Target hostname is empty or too long."
        labels = hostname.split(".")
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            return ChangeStatus.FAIL, "Target hostname is not a safe lowercase Linux hostname."
        hostname_layer = str(change.payload.get("hostname_layer", "")).strip()
        if not hostname_layer.startswith("/") or not hostname_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Hostname plan is not bound to explicit SquashFS hostname evidence."
        machine_policy = str(change.payload.get("machine_id_policy", ""))
        if machine_policy not in {"preserve", "regenerate_on_first_boot"}:
            return ChangeStatus.FAIL, "Machine-id policy is not supported."
        if change.payload.get("machine_id_value_staged") is not False:
            return ChangeStatus.FAIL, "Machine-id value must never be staged in the plan."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Hostname/machine identity plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 38 hostname/machine identity plans must remain staging-only."
        return ChangeStatus.PASS, "Hostname/machine identity plan is source-hash locked, rootfs-evidence bound, machine-id-value free, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_identity" and str(change.payload.get("gate_version", "")) == "alpha50":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Users/groups/password-policy plan is not locked to a valid source SHA-256."
        if payload.get("rootfs_identity_verified") is not True or str(payload.get("analysis_scope", "")) != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Users/groups/password-policy plan lacks verified target-rootfs account evidence."
        supported = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        if str(payload.get("capability_status", "UNKNOWN")) not in supported:
            return ChangeStatus.FAIL, "Users/groups capability is not supported/verified for this target image."
        for key in ("users_groups_status", "uid_gid_status", "group_membership_status"):
            if str(payload.get(key, "UNKNOWN")) not in supported:
                return ChangeStatus.FAIL, f"{key} capability is not supported/verified for this target image."
        if payload.get("host_accounts_touched") is not False:
            return ChangeStatus.FAIL, "Host Windows/WSL accounts must never be used or modified by target-ISO account planning."
        for key in ("shadow_read", "credential_secret_read", "credential_secret_staged", "secret_read", "secret_staged"):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, "Users/groups/password-policy plans must not read or stage credential secrets."
        forbidden_secret_keys = {"password", "password_hash", "passwd_hash", "secret", "token", "recovery_secret", "credential_value"}
        def contains_forbidden(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if str(k).casefold() in forbidden_secret_keys:
                        return True
                    if contains_forbidden(v):
                        return True
            elif isinstance(value, (list, tuple)):
                return any(contains_forbidden(v) for v in value)
            return False
        if contains_forbidden(payload):
            return ChangeStatus.FAIL, "Credential secret material is forbidden in users/groups/password-policy payloads."
        if str(payload.get("credential_policy", "")) != "deferred_secure_verified_apply":
            return ChangeStatus.FAIL, "Credential assignment must remain deferred to a secure verified apply gate."
        uid_min = payload.get("uid_min")
        if not isinstance(uid_min, int) or isinstance(uid_min, bool) or not 100 <= uid_min <= 60000:
            return ChangeStatus.FAIL, "Target UID_MIN evidence is invalid."
        for key in ("passwd_layer", "group_layer"):
            layer = str(payload.get(key, "")).strip()
            if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "Plan is not bound to explicit SquashFS account evidence."
        operation = str(payload.get("operation", ""))
        if operation == "create_group":
            if str(payload.get("control_depth", "")) not in {"advanced", "expert"}:
                return ChangeStatus.FAIL, "Group creation requires Advanced/Expert control depth."
            group_name = str(payload.get("target_group", "")).strip()
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", group_name):
                return ChangeStatus.FAIL, "Target group name is not a safe Linux group name."
            if group_name in {str(x) for x in payload.get("available_groups", [])}:
                return ChangeStatus.FAIL, "Create-group plan targets a group that already exists."
            group_gid = payload.get("group_gid")
            if group_gid is not None:
                if not isinstance(group_gid, int) or isinstance(group_gid, bool) or not 1 <= group_gid <= 60000:
                    return ChangeStatus.FAIL, "Explicit group GID is outside the supported range."
                if group_gid in set(payload.get("existing_group_gids", [])):
                    return ChangeStatus.FAIL, "Explicit group GID conflicts with target-rootfs evidence."
        elif operation in {"configure_default_user", "create_user", "modify_user"}:
            username = str(payload.get("username", "")).strip()
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
                return ChangeStatus.FAIL, "Username is not a safe Linux account name."
            display_name = str(payload.get("display_name", ""))
            if len(display_name) > 128 or any(ch in display_name for ch in ("\r", "\n", "\x00", ":")):
                return ChangeStatus.FAIL, "Display/full name contains unsupported data."
            existing_users = {str(x) for x in payload.get("existing_regular_users", [])}
            if operation == "create_user" and username in existing_users:
                return ChangeStatus.FAIL, "Create-user plan targets an already existing user."
            if operation == "modify_user" and username not in existing_users:
                return ChangeStatus.FAIL, "Modify-user plan targets a user not verified in the target rootfs."
            role = str(payload.get("account_role", ""))
            if role not in {"preserve", "standard", "administrator"}:
                return ChangeStatus.FAIL, "Account role is not supported."
            if role == "preserve" and not bool(payload.get("target_exists")):
                return ChangeStatus.FAIL, "New users require an explicit Standard user or Administrator role."
            admin_group = str(payload.get("admin_group", "")).strip()
            available_groups = {str(x) for x in payload.get("available_groups", [])}
            if role == "administrator" and (admin_group not in {"sudo", "wheel"} or admin_group not in available_groups):
                return ChangeStatus.FAIL, "Administrator plan is not bound to a verified target-rootfs admin group."
            if role in {"preserve", "standard"} and admin_group:
                return ChangeStatus.FAIL, "Non-administrator plans must not stage administrative group membership."
            display_name_mode = str(payload.get("display_name_mode", ""))
            if display_name_mode not in {"preserve", "set"}:
                return ChangeStatus.FAIL, "Display-name preservation mode is invalid."
            if not bool(payload.get("target_exists")) and display_name_mode == "preserve":
                return ChangeStatus.FAIL, "New users cannot preserve a non-existent display name."
            for mode_key in ("uid_mode", "primary_gid_mode"):
                if str(payload.get(mode_key, "")) not in {"preserve", "automatic", "set"}:
                    return ChangeStatus.FAIL, f"{mode_key} is invalid."
            uid = payload.get("uid")
            if uid is not None:
                if not isinstance(uid, int) or isinstance(uid, bool) or not uid_min <= uid <= 60000:
                    return ChangeStatus.FAIL, "Explicit UID is outside the verified regular-user range."
                if operation == "create_user" and uid in set(payload.get("existing_user_uids", [])):
                    return ChangeStatus.FAIL, "Explicit UID conflicts with target-rootfs evidence."
            primary_gid = payload.get("primary_gid")
            if primary_gid is not None:
                if not isinstance(primary_gid, int) or isinstance(primary_gid, bool) or not 1 <= primary_gid <= 60000:
                    return ChangeStatus.FAIL, "Explicit primary GID is outside the supported range."
                if primary_gid not in set(payload.get("existing_group_gids", [])):
                    return ChangeStatus.FAIL, "Explicit primary GID is not a verified target-rootfs group."
            memberships = [str(x) for x in payload.get("supplementary_groups", [])]
            if any(not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", x) for x in memberships):
                return ChangeStatus.FAIL, "Supplementary group list contains an invalid group name."
            if any(x not in available_groups for x in memberships):
                return ChangeStatus.FAIL, "Supplementary group list contains an unverified target-rootfs group."
            if str(payload.get("group_membership_mode", "")) not in {"preserve", "set"}:
                return ChangeStatus.FAIL, "Group-membership policy is invalid."
            password_policy = dict(payload.get("password_policy") or {})
            policy_mode = str(password_policy.get("mode", "preserve"))
            if policy_mode not in {"preserve", "configure"}:
                return ChangeStatus.FAIL, "Password-policy mode is invalid."
            if policy_mode == "configure":
                if str(payload.get("password_policy_status", "UNKNOWN")) not in supported:
                    return ChangeStatus.FAIL, "Password-policy capability is not verified for this target image."
                values = [password_policy.get("min_days"), password_policy.get("max_days"), password_policy.get("warn_days")]
                if any(not isinstance(x, int) or isinstance(x, bool) for x in values):
                    return ChangeStatus.FAIL, "Password-aging policy requires integer min/max/warn values."
                min_days, max_days, warn_days = values
                if not (0 <= min_days <= 99999 and 1 <= max_days <= 99999 and 0 <= warn_days <= 99999 and min_days <= max_days):
                    return ChangeStatus.FAIL, "Password-aging policy values are outside the supported range."
                if payload.get("require_password_policy_reverification_before_apply") is not True:
                    return ChangeStatus.FAIL, "Password-policy changes must be re-verified before apply."
            if payload.get("require_uid_gid_conflict_check_before_apply") is not True or payload.get("require_group_reverification_before_apply") is not True:
                return ChangeStatus.FAIL, "UID/GID and group membership must be re-verified before apply."
        else:
            return ChangeStatus.FAIL, "Unsupported Alpha 50 users/groups operation."
        if payload.get("preserve_autologin") is not True:
            return ChangeStatus.FAIL, "Users/groups plan must preserve the separate autologin policy."
        if payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Users/groups/password-policy plan must keep source ISO read-only and preserve unrelated configuration."
        if payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 50 users/groups/password-policy plans must remain staging-only."
        return ChangeStatus.PASS, "Users / groups / password policy plan is source-hash locked, target-rootfs-evidence bound, capability-gated, credential-secret free, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "dedicated_kiosk_user":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha55" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan is not bound to the Alpha 55 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Dedicated kiosk-user capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_account_verified") is not True:
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan requires verified target account evidence."
        for key in ("passwd_layer", "group_layer"):
            layer = str(payload.get(key, "")).strip()
            if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "Dedicated kiosk-user plan is not bound to explicit target SquashFS account evidence."
        if str(payload.get("operation") or "") != "create_dedicated_non_admin_kiosk_user":
            return ChangeStatus.FAIL, "Unsupported Alpha 55 dedicated kiosk-user operation."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            return ChangeStatus.FAIL, "Dedicated kiosk username is not a safe Linux account name."
        if username in {str(x) for x in (payload.get("existing_regular_users") or [])}:
            return ChangeStatus.FAIL, "Dedicated kiosk username already exists in target evidence."
        display_name = str(payload.get("display_name") or "")
        if not display_name or len(display_name) > 128 or any(ch in display_name for ch in ("\r", "\n", "\x00", ":")):
            return ChangeStatus.FAIL, "Dedicated kiosk display name is invalid."
        if str(payload.get("account_role") or "") != "dedicated_non_admin_kiosk":
            return ChangeStatus.FAIL, "Alpha 55 account role must remain dedicated non-admin kiosk."
        if str(payload.get("uid_mode") or "") != "automatic" or str(payload.get("primary_gid_mode") or "") != "automatic":
            return ChangeStatus.FAIL, "Alpha 55 uses automatic UID/GID allocation only."
        if payload.get("supplementary_groups") not in ([], tuple()):
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan must not stage supplementary groups."
        if payload.get("administrative_groups") not in ([], tuple()):
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan must never stage administrative membership."
        if payload.get("create_home") is not True:
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan requires an explicit home-directory intent."
        if str(payload.get("credential_policy") or "") != "deferred_to_later_verified_gate":
            return ChangeStatus.FAIL, "Credential policy must remain deferred to a later verified gate."
        if any(payload.get(k) is not False for k in ("credential_secret_read", "credential_secret_staged", "shadow_read", "host_accounts_touched")):
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan must not read/stage credentials, shadow data, or host accounts."
        if payload.get("login_policy_deferred_to_later_gate") is not True or payload.get("session_policy_deferred_to_later_gate") is not True or payload.get("autologin_policy_preserved") is not True:
            return ChangeStatus.FAIL, "Login/session/autologin policy must remain preserved and delegated to later Part 4 gates."
        if payload.get("require_user_absence_reverification_before_apply") is not True:
            return ChangeStatus.FAIL, "Kiosk username absence must be re-verified before apply."
        if payload.get("preserve_existing_users_groups") is not True or payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Dedicated kiosk-user plan must preserve existing accounts/unrelated configuration and source ISO bytes."
        if payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 55 dedicated kiosk-user plans must remain staging-only."
        return ChangeStatus.PASS, "Dedicated non-admin kiosk user plan is source-hash locked, target-account-evidence bound, admin/credential free, later-login/session-policy preserving and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "restricted_login":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Restricted-login plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha56" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Restricted-login plan is not bound to the Alpha 56 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Restricted-login capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_login_restriction_verified") is not True:
            return ChangeStatus.FAIL, "Restricted-login plan requires verified target login-restriction evidence."
        tool = str(payload.get("management_tool_path") or "")
        layer = str(payload.get("management_tool_layer") or "")
        if tool not in {"/usr/sbin/usermod", "/usr/bin/passwd"} or not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Restricted-login plan is not bound to a verified target-rootfs password-lock tool."
        for key in ("passwd_layer", "group_layer"):
            evidence_layer = str(payload.get(key, "")).strip()
            if not evidence_layer.startswith("/") or not evidence_layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "Restricted-login plan is not bound to explicit target account evidence."
        if str(payload.get("operation") or "") != "lock_password_authentication":
            return ChangeStatus.FAIL, "Unsupported Alpha 56 restricted-login operation."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            return ChangeStatus.FAIL, "Restricted-login target username is not a safe Linux account name."
        if username == "root" or username in {str(x) for x in (payload.get("admin_users") or [])}:
            return ChangeStatus.FAIL, "Restricted-login plan must not lock root or a verified administrative user."
        existing = {str(x) for x in (payload.get("existing_regular_users") or [])}
        dependency = str(payload.get("account_dependency") or "")
        if username in existing:
            if dependency != "verified_existing_target_user":
                return ChangeStatus.FAIL, "Existing restricted-login target must use verified-existing-user dependency semantics."
        elif dependency != "alpha55_dedicated_non_admin_kiosk_user":
            return ChangeStatus.FAIL, "Missing target account requires an explicit Alpha 55 dedicated-kiosk-user dependency."
        if str(payload.get("restriction_scope") or "") != "password_authentication_only":
            return ChangeStatus.FAIL, "Alpha 56 is limited to password-authentication restriction only."
        if str(payload.get("password_authentication") or "") != "locked":
            return ChangeStatus.FAIL, "Restricted-login plan must explicitly stage password authentication as locked."
        if any(payload.get(k) is not False for k in ("credential_secret_read", "credential_secret_staged", "shadow_read", "host_login_state_accessed", "pam_contents_read", "ssh_config_read")):
            return ChangeStatus.FAIL, "Restricted-login plan must not read/stage secrets, shadow contents, host login state, PAM contents or SSH configuration."
        if any(payload.get(k) is not True for k in ("preserve_autologin", "preserve_session_policy", "preserve_ssh_configuration", "preserve_pam_configuration")):
            return ChangeStatus.FAIL, "Restricted-login plan must preserve autologin, session, SSH and PAM policy for their own gates."
        if payload.get("require_account_dependency_reverification_before_apply") is not True:
            return ChangeStatus.FAIL, "Restricted-login account existence/dependency must be re-verified before apply."
        if payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Restricted-login plan must preserve source ISO bytes and unrelated login configuration."
        if payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 56 restricted-login plans must remain staging-only."
        return ChangeStatus.PASS, "Restricted login plan is source-hash locked, target-account/tool-evidence bound, password-lock scoped, secret/host isolated, dependency-explicit, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "restricted_session":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Restricted-session plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha57" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Restricted-session plan is not bound to the Alpha 57 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Restricted-session capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_restricted_session_verified") is not True:
            return ChangeStatus.FAIL, "Restricted-session plan requires verified target session evidence."
        if str(payload.get("backend") or "") != "sddm-autologin-session-dropin" or str(payload.get("display_manager") or "").casefold() != "sddm":
            return ChangeStatus.FAIL, "Alpha 57 currently requires the verified SDDM fixed-session backend."
        dm_layer = str(payload.get("display_manager_layer") or "")
        config_layer = str(payload.get("target_config_directory_layer") or "")
        if any(not layer.startswith("/") or not layer.casefold().endswith(".squashfs") for layer in (dm_layer, config_layer)):
            return ChangeStatus.FAIL, "Restricted-session plan is not bound to explicit target SquashFS evidence."
        if str(payload.get("target_config_directory") or "") != "/etc/sddm.conf.d":
            return ChangeStatus.FAIL, "Restricted-session target directory is not the verified SDDM drop-in directory."
        if str(payload.get("managed_target_path") or "") != "/etc/sddm.conf.d/99-chromapress-kiosk-session.conf" or payload.get("managed_target_present") is not False:
            return ChangeStatus.FAIL, "Restricted-session managed target path is not collision-free."
        if str(payload.get("operation") or "") != "bind_kiosk_autologin_session":
            return ChangeStatus.FAIL, "Unsupported Alpha 57 restricted-session operation."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            return ChangeStatus.FAIL, "Restricted-session kiosk username is not a safe Linux account name."
        if username == "root" or username in {str(x) for x in (payload.get("admin_users") or [])}:
            return ChangeStatus.FAIL, "Restricted-session plan must not target root or a verified administrative user."
        existing = {str(x) for x in (payload.get("existing_regular_users") or [])}
        dependency = str(payload.get("account_dependency") or "")
        if username in existing:
            if dependency != "verified_existing_target_user":
                return ChangeStatus.FAIL, "Existing restricted-session target must use verified-existing-user dependency semantics."
        elif dependency != "alpha55_dedicated_non_admin_kiosk_user":
            return ChangeStatus.FAIL, "Missing restricted-session account requires an explicit Alpha 55 kiosk-user dependency."
        session_name = str(payload.get("session_name") or "")
        if not re.fullmatch(r"[A-Za-z0-9._+-]{1,128}\.desktop", session_name):
            return ChangeStatus.FAIL, "Restricted-session descriptor filename is not safe."
        sessions = [x for x in (payload.get("verified_sessions") or []) if isinstance(x, dict)]
        selected = [x for x in sessions if str(x.get("name") or "") == session_name and str(x.get("kind") or "") in {"x11", "wayland"}]
        if not selected:
            return ChangeStatus.FAIL, "Restricted-session selection is not present in verified target session metadata."
        if str(payload.get("session_kind") or "") != str(selected[0].get("kind") or ""):
            return ChangeStatus.FAIL, "Restricted-session kind does not match verified target session evidence."
        if str(payload.get("restriction_scope") or "") != "fixed_autologin_session_selection_only":
            return ChangeStatus.FAIL, "Alpha 57 is limited to fixed autologin-session selection only."
        if str(payload.get("sddm_section") or "") != "Autologin" or str(payload.get("sddm_key") or "") != "Session":
            return ChangeStatus.FAIL, "Restricted-session plan must use the structured SDDM Autologin/Session setting."
        if str(payload.get("restricted_login_dependency") or "") != "alpha56_restricted_login_required":
            return ChangeStatus.FAIL, "Restricted-session plan requires the Alpha 56 restricted-login dependency."
        if str(payload.get("autologin_dependency") or "") != "alpha39_autologin_same_user_required":
            return ChangeStatus.FAIL, "Restricted-session plan requires same-user Alpha 39 autologin dependency."
        if any(payload.get(k) is not False for k in (
            "session_file_contents_read", "display_manager_config_contents_read", "credential_secret_read",
            "credential_secret_staged", "host_session_state_accessed", "pam_contents_read", "ssh_config_read",
        )):
            return ChangeStatus.FAIL, "Restricted-session plan must not read/stage session contents, display-manager config contents, secrets, host session state, PAM or SSH contents."
        if any(payload.get(k) is not True for k in (
            "preserve_existing_session_descriptors", "preserve_existing_display_manager_config",
            "preserve_other_users_sessions", "preserve_pam_configuration", "preserve_ssh_configuration",
            "require_managed_target_absence_reverification_before_apply", "require_dependencies_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        )):
            return ChangeStatus.FAIL, "Restricted-session plan must preserve existing session/display-manager configuration, re-verify dependencies/target absence, and remain staging-only."
        return ChangeStatus.PASS, "Restricted session plan is source-hash locked, target-session/SDDM-evidence bound, fixed-session scoped, dependency-explicit, secret/host isolated, preservation-first and staging-only."


    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "service_lockdown":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Service-lockdown plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha58" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Service-lockdown plan is not bound to the Alpha 58 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Service-lockdown capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_service_lockdown_verified") is not True:
            return ChangeStatus.FAIL, "Service-lockdown plan requires verified target systemd service metadata."
        if str(payload.get("backend") or "") != "systemd-disable-mask-intent" or str(payload.get("init_system") or "") != "systemd":
            return ChangeStatus.FAIL, "Alpha 58 requires the verified systemd disable+mask backend."
        vendor_path = str(payload.get("vendor_unit_path") or "")
        vendor_layer = str(payload.get("vendor_unit_layer") or "")
        if vendor_path not in {"/usr/lib/systemd/system", "/lib/systemd/system"}:
            return ChangeStatus.FAIL, "Service-lockdown plan is not bound to a supported target systemd vendor-unit path."
        if not vendor_layer.startswith("/") or not vendor_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Service-lockdown plan is not bound to explicit target SquashFS unit evidence."
        if str(payload.get("operation") or "") != "disable_and_mask_verified_service":
            return ChangeStatus.FAIL, "Unsupported Alpha 58 service-lockdown operation."
        unit = str(payload.get("service_unit") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,120}\.service", unit) or "/" in unit:
            return ChangeStatus.FAIL, "Service-lockdown target is not a safe systemd .service unit name."
        available = [x for x in (payload.get("available_lockdown_units") or []) if isinstance(x, dict)]
        matched = [x for x in available if str(x.get("name") or "") == unit]
        if not matched:
            return ChangeStatus.FAIL, "Service-lockdown target is not present in the verified non-protected target service set."
        protected = {str(x) for x in (payload.get("protected_service_units") or [])}
        if unit in protected:
            return ChangeStatus.FAIL, "Service-lockdown target is protected by ChromaPress safety policy."
        if str(payload.get("lockdown_scope") or "") != "single_verified_noncritical_systemd_service":
            return ChangeStatus.FAIL, "Alpha 58 is limited to one verified non-critical systemd service at a time."
        if any(payload.get(k) is not False for k in (
            "unit_contents_read", "enablement_links_read", "enablement_link_targets_read",
            "environment_files_read", "service_secrets_read", "credential_secret_read", "host_service_state_accessed",
        )):
            return ChangeStatus.FAIL, "Service-lockdown plan must not read unit contents, link targets, environment files, secrets or host service state."
        if any(payload.get(k) is not True for k in (
            "preserve_unit_file_contents", "preserve_timer_socket_units", "preserve_unrelated_services",
            "require_target_unit_reverification_before_apply", "require_systemd_apply_verification",
            "source_read_only", "preserve_unrelated", "stage_only",
        )):
            return ChangeStatus.FAIL, "Service-lockdown plan must preserve unit data/unrelated policy, re-verify apply prerequisites and remain staging-only."
        return ChangeStatus.PASS, "Service lockdown plan is source-hash locked, verified-target-unit bound, protected-unit filtered, host/secret isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "network_restriction":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Network-restriction plan requires a valid source SHA-256."
        if payload.get("gate_version") != "alpha59" or payload.get("analysis_scope") != "target_iso_rootfs":
            return ChangeStatus.FAIL, "Network-restriction plan is not bound to the Alpha 59 target-ISO capability model."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Network-restriction capability is {capability}; fail-closed staging is required."
        if payload.get("rootfs_network_restriction_verified") is not True:
            return ChangeStatus.FAIL, "Network-restriction plan requires verified target NetworkManager/polkit metadata."
        if str(payload.get("backend") or "") != "NetworkManager-polkit-managed-rule" or str(payload.get("network_backend") or "") != "NetworkManager":
            return ChangeStatus.FAIL, "Alpha 59 requires the verified NetworkManager + polkit managed-rule backend."
        if str(payload.get("operation") or "") != "restrict_kiosk_networkmanager_control":
            return ChangeStatus.FAIL, "Unsupported Alpha 59 network-restriction operation."
        username = str(payload.get("username") or "").strip()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            return ChangeStatus.FAIL, "Network-restriction kiosk username is not a safe Linux account name."
        if str(payload.get("kiosk_user_dependency") or "") != "alpha55_dedicated_non_admin_kiosk_user_required":
            return ChangeStatus.FAIL, "Alpha 59 requires the explicit Alpha 55 dedicated non-admin kiosk-user dependency."
        rules_dir = str(payload.get("polkit_rules_directory") or "")
        rules_layer = str(payload.get("polkit_rules_directory_layer") or "")
        policy_path = str(payload.get("networkmanager_policy_path") or "")
        policy_layer = str(payload.get("networkmanager_policy_layer") or "")
        managed_name = str(payload.get("managed_rule_name") or "")
        managed_path = str(payload.get("managed_rule_path") or "")
        if rules_dir != "/etc/polkit-1/rules.d" or not rules_layer.startswith("/") or not rules_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Network-restriction plan is not bound to verified target polkit rules.d evidence."
        if policy_path != "/usr/share/polkit-1/actions/org.freedesktop.NetworkManager.policy" or not policy_layer.startswith("/") or not policy_layer.casefold().endswith(".squashfs"):
            return ChangeStatus.FAIL, "Network-restriction plan is not bound to verified NetworkManager polkit action metadata."
        if managed_name != "49-chromapress-kiosk-network.rules" or managed_path != "/etc/polkit-1/rules.d/49-chromapress-kiosk-network.rules":
            return ChangeStatus.FAIL, "Alpha 59 managed polkit target is not the reserved ChromaPress path."
        existing = {str(x) for x in (payload.get("existing_rule_names") or [])}
        if payload.get("managed_target_present") is not False or managed_name in existing:
            return ChangeStatus.FAIL, "Network-restriction managed polkit target collides with existing target configuration."
        actions = [str(x) for x in (payload.get("restricted_actions") or [])]
        required_actions = {
            "org.freedesktop.NetworkManager.enable-disable-network",
            "org.freedesktop.NetworkManager.enable-disable-wifi",
            "org.freedesktop.NetworkManager.enable-disable-wwan",
            "org.freedesktop.NetworkManager.settings.modify.system",
        }
        if set(actions) != required_actions:
            return ChangeStatus.FAIL, "Alpha 59 NetworkManager control-action allowlist is incomplete or unexpected."
        if str(payload.get("restriction_scope") or "") != "kiosk_networkmanager_control_only":
            return ChangeStatus.FAIL, "Alpha 59 is limited to kiosk NetworkManager control restriction only."
        if any(payload.get(k) is not False for k in (
            "traffic_blocking_claimed", "firewall_rules_read", "firewall_rules_staged",
            "networkmanager_profile_contents_read", "polkit_policy_contents_read", "existing_rule_contents_read",
            "credential_secret_read", "host_network_accessed",
        )):
            return ChangeStatus.FAIL, "Network-restriction plan must not claim traffic blocking or read/stage firewall/profile/polkit contents, secrets or host networking."
        if any(payload.get(k) is not True for k in (
            "preserve_existing_network_profiles", "preserve_existing_polkit_rules", "preserve_firewall_policy",
            "preserve_other_users_network_control", "require_managed_target_absence_reverification_before_apply",
            "require_networkmanager_polkit_reverification_before_apply", "require_kiosk_user_dependency_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        )):
            return ChangeStatus.FAIL, "Network-restriction plan must preserve profiles/polkit/firewall/other users, re-verify prerequisites and remain staging-only."
        return ChangeStatus.PASS, "Network restrictions plan is source-hash locked, target NetworkManager/polkit-evidence bound, kiosk-user dependency explicit, non-traffic-blocking, host/secret isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "persistence_policy" and str(change.payload.get("gate_version", "")) == "alpha61":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Persistence-policy plan is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_metadata" or payload.get("rootfs_persistence_policy_verified") is not True:
            return ChangeStatus.FAIL, "Persistence-policy plan lacks verified target metadata capability evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Persistence-policy capability is {capability}; fail-closed staging is required."
        operation = str(payload.get("operation") or "")
        expected = {
            "require_volatile_kiosk_runtime": ("volatile", "immutable_runtime"),
            "require_controlled_kiosk_persistence": ("selected_directories", "controlled_persistence"),
        }.get(operation)
        if expected is None:
            return ChangeStatus.FAIL, "Unsupported Alpha 61 persistence-policy operation."
        if str(payload.get("policy_scope") or "") != "kiosk_session_runtime_only":
            return ChangeStatus.FAIL, "Alpha 61 persistence policy must remain limited to kiosk session runtime."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "Persistence-policy kiosk username is unsafe."
        if username in {str(x).casefold() for x in (payload.get("admin_users") or [])}:
            return ChangeStatus.FAIL, "Persistence-policy plan must not target a verified administrative user."
        if str(payload.get("account_dependency") or "") not in {"verified_existing_target_user", "alpha55_dedicated_non_admin_kiosk_user"}:
            return ChangeStatus.FAIL, "Persistence-policy account dependency is not explicit."
        if str(payload.get("persistence_policy") or "") != expected[0] or str(payload.get("part3_dependency") or "") != expected[1]:
            return ChangeStatus.FAIL, "Persistence-policy mode does not match its required Part 3 dependency."
        dirs = [str(x) for x in (payload.get("persistent_directories") or [])]
        if operation == "require_volatile_kiosk_runtime":
            if dirs or payload.get("selected_directories_survive_reboot") is not False:
                return ChangeStatus.FAIL, "Volatile kiosk policy must not stage persistent directories."
        else:
            if not dirs or len(dirs) > 8:
                return ChangeStatus.FAIL, "Controlled kiosk persistence requires 1–8 explicit directories."
            prefix = f"/home/{username}/"
            for path in dirs:
                if not path.startswith(prefix) or ".." in path.split("/") or not re.fullmatch(r"/[A-Za-z0-9._+@/-]{1,240}", path):
                    return ChangeStatus.FAIL, "Controlled persistent directory is outside the explicit kiosk-home scope or unsafe."
            if payload.get("selected_directories_survive_reboot") is not True:
                return ChangeStatus.FAIL, "Controlled persistence must explicitly state that selected directories survive reboot."
        if payload.get("runtime_changes_survive_reboot") is not False or payload.get("unlisted_runtime_changes_survive_reboot") is not False:
            return ChangeStatus.FAIL, "Alpha 61 requires unselected runtime changes to remain volatile."
        rootfs = [str(x) for x in (payload.get("rootfs_layers") or [])]
        boot_files = [str(x) for x in (payload.get("boot_config_files") or [])]
        mechanism = str(payload.get("initramfs_mechanism") or "")
        if not rootfs or not all(x.startswith("/") and x.casefold().endswith(".squashfs") for x in rootfs):
            return ChangeStatus.FAIL, "Persistence-policy plan lacks explicit target rootfs evidence."
        if not boot_files or mechanism not in {"update-initramfs", "dracut", "mkinitcpio"}:
            return ChangeStatus.FAIL, "Persistence-policy Part 3 dependency lacks boot/initramfs evidence."
        for key in (
            "existing_persistence_policy_read", "persistent_data_contents_read", "mount_configuration_contents_read",
            "host_storage_accessed", "host_mount_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, "Persistence-policy staging must not read existing persistence/data/mount contents or host storage state."
        for key in (
            "require_part3_dependency_before_apply", "require_part3_dependency_reverification_before_apply",
            "require_account_dependency_reverification_before_apply", "preserve_existing_persistence_configuration",
            "preserve_unselected_user_data", "do_not_stage_mount_or_volume_changes", "source_read_only",
            "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"Persistence-policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "Persistence policy plan is source-hash locked, target-metadata bound, kiosk-scoped, Part-3 delegated, host/data isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "administrator_recovery_policy" and str(change.payload.get("gate_version", "")) == "alpha62":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Administrator/recovery policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_rootfs" or payload.get("rootfs_admin_recovery_verified") is not True:
            return ChangeStatus.FAIL, "Administrator/recovery policy lacks verified target account/autologin evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Administrator/recovery capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "require_dedicated_recovery_administrator":
            return ChangeStatus.FAIL, "Unsupported Alpha 62 administrator/recovery operation."
        if str(payload.get("policy_scope") or "") != "separate_non_autologin_recovery_administrator":
            return ChangeStatus.FAIL, "Alpha 62 recovery policy must remain limited to one separate non-autologin administrator role."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "Recovery administrator username is unsafe or root."
        admin_group = str(payload.get("admin_group") or "")
        verified_admin_groups = {str(x) for x in (payload.get("verified_admin_groups") or [])}
        if admin_group not in {"sudo", "wheel"} or admin_group not in verified_admin_groups:
            return ChangeStatus.FAIL, "Recovery administrator group is not a verified supported target administrator group."
        existing = {str(x).casefold() for x in (payload.get("existing_regular_users") or [])}
        admins = {str(x).casefold() for x in (payload.get("existing_admin_users") or [])}
        if username in existing and username not in admins:
            return ChangeStatus.FAIL, "Existing non-admin accounts cannot be silently promoted by Alpha 62."
        dependency = str(payload.get("account_dependency") or "")
        if dependency == "verified_existing_admin_user":
            if username not in admins:
                return ChangeStatus.FAIL, "Existing-admin dependency does not match verified target administrator membership."
        elif dependency == "alpha50_create_administrator":
            if username in existing:
                return ChangeStatus.FAIL, "Alpha 50 create-administrator dependency requires a target username that does not already exist."
        else:
            return ChangeStatus.FAIL, "Administrator/recovery account dependency is not explicit."
        current_autologin = str(payload.get("current_autologin_user") or "").strip().casefold()
        if current_autologin and username == current_autologin:
            return ChangeStatus.FAIL, "Recovery administrator must not be the explicitly configured autologin user."
        if payload.get("recovery_account_must_be_distinct_from_kiosk") is not True:
            return ChangeStatus.FAIL, "Recovery administrator must remain explicitly separate from the kiosk role."
        if payload.get("recovery_account_must_not_autologin") is not True or payload.get("allow_root_as_recovery_administrator") is not False:
            return ChangeStatus.FAIL, "Recovery administrator must be non-root and non-autologin."
        if str(payload.get("credential_policy") or "") != "deferred_secure_verified_apply":
            return ChangeStatus.FAIL, "Recovery credentials must be deferred to secure verified apply."
        if str(payload.get("authentication_factor_policy") or "") != "deferred_to_fido2_webauthn_security_key_tpm_gates":
            return ChangeStatus.FAIL, "Alpha 62 must not pre-empt later authenticator gates."
        for key in (
            "shadow_read", "credential_secret_read", "credential_secret_staged",
            "recovery_secret_read", "recovery_secret_staged", "pam_contents_read",
            "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
            "host_accounts_touched", "host_login_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"Administrator/recovery plan must not read/stage protected login/recovery state: {key}."
        for key in (
            "preserve_existing_administrators", "preserve_root_account_policy",
            "preserve_rescue_boot_configuration", "preserve_pam_configuration",
            "preserve_ssh_configuration", "do_not_stage_authenticator_changes",
            "require_admin_membership_reverification_before_apply",
            "require_autologin_reverification_before_apply",
            "require_recovery_kiosk_separation_reverification_before_apply",
            "require_account_dependency_before_apply", "require_account_dependency_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"Administrator/recovery safety requirement missing: {key}."
        return ChangeStatus.PASS, "Administrator/recovery policy is source-hash locked, target-account/autologin-evidence bound, recovery-role separated, secret/authenticator isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "fido2_policy" and str(change.payload.get("gate_version", "")) == "alpha63":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "FIDO2 policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_package_manifest" or payload.get("fido2_policy_verified") is not True:
            return ChangeStatus.FAIL, "FIDO2 policy lacks verified target package-manifest evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"FIDO2 capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "require_fido2_second_factor_for_recovery_admin":
            return ChangeStatus.FAIL, "Unsupported Alpha 63 FIDO2 operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_fido2_second_factor":
            return ChangeStatus.FAIL, "Alpha 63 FIDO2 policy must remain limited to a second factor for the recovery administrator."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "FIDO2 recovery-administrator username is unsafe or root."
        if payload.get("alpha62_dependency_verified") is not True or str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy":
            return ChangeStatus.FAIL, "Alpha 63 requires the verified Alpha 62 administrator/recovery-policy dependency."
        autologin_user = str(payload.get("current_autologin_user") or "").strip().casefold()
        if autologin_user and username == autologin_user:
            return ChangeStatus.FAIL, "FIDO2 recovery administrator must not be the explicit autologin user."
        pam_packages = [str(x) for x in (payload.get("pam_fido2_packages") or []) if str(x).strip()]
        lib_packages = [str(x) for x in (payload.get("libfido2_packages") or []) if str(x).strip()]
        if not pam_packages or not lib_packages:
            return ChangeStatus.FAIL, "FIDO2 policy requires positively verified PAM-FIDO2 and libfido2 package evidence."
        if str(payload.get("authentication_composition") or "") != "existing_primary_plus_fido2_second_factor":
            return ChangeStatus.FAIL, "Alpha 63 must stage FIDO2 only as an additional second factor."
        for key in (
            "pam_contents_read", "pam_contents_modified_during_analysis", "authenticator_devices_enumerated",
            "usb_hid_state_accessed", "credential_ids_read", "credential_secret_read",
            "credential_secret_staged", "authenticator_enrollment_performed", "webauthn_capability_claimed",
            "security_key_presence_claimed", "yubikey_capability_claimed", "platform_authenticator_claimed",
            "tpm_capability_claimed", "host_authenticator_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"FIDO2 plan must not inspect/enroll/claim protected authenticator state: {key}."
        for key in (
            "preserve_existing_primary_authentication", "preserve_pam_contents_during_analysis_and_staging",
            "require_pam_integration_verification_before_apply", "require_alpha62_dependency_before_apply",
            "require_alpha62_dependency_reverification_before_apply", "require_target_package_reverification_before_apply",
            "require_recovery_username_reverification_before_apply", "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"FIDO2 policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "FIDO2 policy is source-hash locked, target package-evidence bound, Alpha 62 recovery-role dependent, authenticator/credential isolated, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "webauthn_policy" and str(change.payload.get("gate_version", "")) == "alpha64":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "WebAuthn policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_package_manifest" or payload.get("webauthn_policy_verified") is not True:
            return ChangeStatus.FAIL, "WebAuthn policy lacks verified target package-manifest evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"WebAuthn capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "allow_webauthn_for_recovery_web_workflows":
            return ChangeStatus.FAIL, "Unsupported Alpha 64 WebAuthn operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_browser_webauthn":
            return ChangeStatus.FAIL, "Alpha 64 WebAuthn policy must remain limited to browser-mediated recovery workflows."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "WebAuthn recovery-administrator username is unsafe or root."
        if payload.get("alpha62_dependency_verified") is not True or str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy":
            return ChangeStatus.FAIL, "Alpha 64 requires the verified Alpha 62 administrator/recovery-policy dependency."
        autologin_user = str(payload.get("current_autologin_user") or "").strip().casefold()
        if autologin_user and username == autologin_user:
            return ChangeStatus.FAIL, "WebAuthn recovery administrator must not be the explicit autologin user."
        browser_packages = [str(x) for x in (payload.get("browser_packages") or []) if str(x).strip()]
        browser_package = str(payload.get("browser_package") or "").strip()
        if not browser_packages or browser_package not in browser_packages:
            return ChangeStatus.FAIL, "WebAuthn policy requires one browser package bound to positively verified target package evidence."
        if payload.get("webauthn_runtime_verified") is not False or payload.get("relying_party_verified") is not False or payload.get("origin_verified") is not False:
            return ChangeStatus.FAIL, "Alpha 64 must not claim runtime WebAuthn, relying-party or origin verification during analysis/staging."
        for key in (
            "browser_config_contents_read", "relying_party_config_read", "origin_config_read",
            "authenticator_devices_enumerated", "usb_hid_state_accessed", "credential_ids_read",
            "credential_secret_read", "credential_secret_staged", "authenticator_enrollment_performed",
            "security_key_presence_claimed", "yubikey_capability_claimed", "platform_authenticator_claimed",
            "tpm_capability_claimed", "host_browser_state_accessed", "host_authenticator_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"WebAuthn plan must not inspect/enroll/claim protected browser/authenticator state: {key}."
        for key in (
            "preserve_existing_primary_authentication", "preserve_browser_configuration_during_analysis_and_staging",
            "require_browser_runtime_verification_before_apply", "require_relying_party_and_origin_verification_before_use",
            "require_alpha62_dependency_before_apply", "require_alpha62_dependency_reverification_before_apply",
            "require_target_package_reverification_before_apply", "require_recovery_username_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"WebAuthn policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "WebAuthn policy is source-hash locked, target browser-package evidence bound, Alpha 62 recovery-role dependent, runtime/RP/origin/authenticator claims deferred, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "security_key_policy" and str(change.payload.get("gate_version", "")) == "alpha65":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Security-key policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_package_manifest" or payload.get("security_key_policy_verified") is not True:
            return ChangeStatus.FAIL, "Security-key policy lacks verified target package-manifest evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Security-key capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "allow_external_fido2_security_key_for_recovery_admin":
            return ChangeStatus.FAIL, "Unsupported Alpha 65 security-key operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_external_security_key":
            return ChangeStatus.FAIL, "Alpha 65 scope must remain a recovery-administrator external security key."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "Security-key recovery username is unsafe or root."
        if username == str(payload.get("current_autologin_user") or "").strip().casefold() and username:
            return ChangeStatus.FAIL, "Security-key recovery administrator must not be the explicit autologin user."
        if str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy" or payload.get("alpha62_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 65 requires verified Alpha 62 recovery-policy evidence."
        if str(payload.get("fido2_dependency") or "") != "alpha63_fido2_policy" or payload.get("alpha63_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 65 requires the verified Alpha 63 FIDO2 dependency."
        if not [x for x in (payload.get("security_key_tool_packages") or []) if str(x).strip()] or not [x for x in (payload.get("libfido2_packages") or []) if str(x).strip()]:
            return ChangeStatus.FAIL, "Security-key policy requires verified target FIDO2 tooling and libfido2 package evidence."
        for key in (
            "physical_security_key_enumerated", "security_key_presence_claimed", "security_key_compatibility_claimed",
            "credential_ids_read", "credential_secret_read", "credential_secret_staged", "authenticator_enrollment_performed",
            "usb_hid_state_accessed", "yubikey_capability_claimed", "platform_authenticator_claimed",
            "tpm_capability_claimed", "host_authenticator_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"Security-key plan must not inspect/enroll/claim protected device state: {key}."
        for key in (
            "preserve_existing_primary_authentication", "require_physical_key_verification_before_apply",
            "require_key_compatibility_verification_before_apply", "require_explicit_enrollment_before_use",
            "require_recovery_username_reverification_before_apply", "require_target_package_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"Security-key policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "Security-key policy is source-hash locked, Alpha 62/63 dependency bound, target-tooling verified, physical-key/enrollment/credential claims deferred, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "yubikey_policy" and str(change.payload.get("gate_version", "")) == "alpha66":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "YubiKey-class policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_package_manifest" or payload.get("yubikey_policy_verified") is not True:
            return ChangeStatus.FAIL, "YubiKey-class policy lacks verified target package-manifest evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"YubiKey-class capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "allow_yubikey_class_authenticator_for_recovery_admin":
            return ChangeStatus.FAIL, "Unsupported Alpha 66 YubiKey-class operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_yubikey_class":
            return ChangeStatus.FAIL, "Alpha 66 scope must remain a recovery-administrator YubiKey-class policy."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "YubiKey recovery username is unsafe or root."
        if username == str(payload.get("current_autologin_user") or "").strip().casefold() and username:
            return ChangeStatus.FAIL, "YubiKey recovery administrator must not be the explicit autologin user."
        if str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy" or payload.get("alpha62_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 66 requires verified Alpha 62 recovery-policy evidence."
        if not [x for x in (payload.get("yubikey_packages") or []) if str(x).strip()]:
            return ChangeStatus.FAIL, "YubiKey-class policy requires positively verified target vendor-class tooling."
        for key in (
            "physical_yubikey_enumerated", "yubikey_presence_claimed", "serial_number_read", "otp_secret_read", "pin_secret_read",
            "credential_ids_read", "credential_secret_read", "credential_secret_staged", "authenticator_enrollment_performed",
            "usb_hid_state_accessed", "platform_authenticator_claimed", "tpm_capability_claimed", "host_authenticator_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"YubiKey-class plan must not inspect/enroll/claim protected vendor/device state: {key}."
        for key in (
            "preserve_existing_primary_authentication", "require_physical_yubikey_verification_before_apply",
            "require_vendor_mode_compatibility_verification_before_apply", "require_explicit_enrollment_before_use",
            "require_recovery_username_reverification_before_apply", "require_target_package_reverification_before_apply",
            "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"YubiKey-class policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "YubiKey-class policy is source-hash locked, target vendor-tooling bound, physical-device/serial/PIN/OTP/enrollment claims deferred, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "platform_authenticator_policy" and str(change.payload.get("gate_version", "")) == "alpha67":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Platform-authenticator policy is not locked to a valid source SHA-256."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"Platform-authenticator capability is {capability}; runtime/hardware verification is required and staging is fail-closed."
        if str(payload.get("analysis_scope") or "") != "verified_target_runtime_and_hardware" or payload.get("platform_authenticator_policy_verified") is not True:
            return ChangeStatus.FAIL, "Platform-authenticator policy requires separately verified target runtime and hardware evidence."
        if payload.get("platform_authenticator_runtime_verified") is not True or payload.get("platform_authenticator_hardware_verified") is not True:
            return ChangeStatus.FAIL, "Platform-authenticator runtime and hardware must both be positively verified."
        if str(payload.get("operation") or "") != "allow_verified_platform_authenticator_for_recovery_workflows":
            return ChangeStatus.FAIL, "Unsupported Alpha 67 platform-authenticator operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_platform_authenticator":
            return ChangeStatus.FAIL, "Alpha 67 scope must remain recovery-administrator platform authentication."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "Platform-authenticator recovery username is unsafe or root."
        if username == str(payload.get("current_autologin_user") or "").strip().casefold() and username:
            return ChangeStatus.FAIL, "Platform-authenticator recovery administrator must not be the explicit autologin user."
        if str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy" or payload.get("alpha62_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 67 requires verified Alpha 62 recovery-policy evidence."
        if payload.get("alpha64_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 67 requires verified Alpha 64 WebAuthn prerequisite evidence."
        for key in (
            "biometric_capability_claimed", "tpm_capability_claimed", "credential_ids_read", "credential_secret_read",
            "credential_secret_staged", "authenticator_enrollment_performed", "host_authenticator_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"Platform-authenticator plan must not infer biometrics/TPM or inspect/enroll credentials during staging: {key}."
        for key in (
            "preserve_existing_primary_authentication", "require_runtime_reverification_before_apply",
            "require_hardware_reverification_before_apply", "require_explicit_enrollment_before_use",
            "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"Platform-authenticator policy safety requirement missing: {key}."
        return ChangeStatus.PASS, "Platform-authenticator policy is separately runtime/hardware verified, does not infer biometrics or TPM, preserves primary authentication and remains staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "tpm_key_protection" and str(change.payload.get("gate_version", "")) == "alpha68":
        payload = change.payload
        source_sha = str(payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "TPM key-protection policy is not locked to a valid source SHA-256."
        if str(payload.get("analysis_scope") or "") != "target_iso_package_manifest" or payload.get("tpm_key_protection_verified") is not True:
            return ChangeStatus.FAIL, "TPM key-protection policy lacks verified target package-manifest evidence."
        capability = str(payload.get("capability_status") or "UNKNOWN")
        if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
            return ChangeStatus.FAIL, f"TPM key-protection capability is {capability}; fail-closed staging is required."
        if str(payload.get("operation") or "") != "require_tpm_backed_recovery_key_protection":
            return ChangeStatus.FAIL, "Unsupported Alpha 68 TPM key-protection operation."
        if str(payload.get("policy_scope") or "") != "recovery_administrator_tpm_backed_key_protection":
            return ChangeStatus.FAIL, "Alpha 68 scope must remain recovery-administrator TPM-backed key protection."
        username = str(payload.get("username") or "").strip().casefold()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root":
            return ChangeStatus.FAIL, "TPM recovery username is unsafe or root."
        if username == str(payload.get("current_autologin_user") or "").strip().casefold() and username:
            return ChangeStatus.FAIL, "TPM recovery administrator must not be the explicit autologin user."
        if str(payload.get("administrator_recovery_dependency") or "") != "alpha62_administrator_recovery_policy" or payload.get("alpha62_dependency_verified") is not True:
            return ChangeStatus.FAIL, "Alpha 68 requires verified Alpha 62 recovery-policy evidence."
        if not [x for x in (payload.get("tpm_tool_packages") or []) if str(x).strip()] or not [x for x in (payload.get("tss_packages") or []) if str(x).strip()]:
            return ChangeStatus.FAIL, "TPM policy requires verified TPM2 tooling and TSS2 package evidence."
        for key in (
            "tpm_hardware_enumerated", "tpm_hardware_verified", "tpm_presence_claimed", "tpm_ownership_state_read",
            "pcr_values_read", "key_material_generated", "key_material_read", "key_material_staged", "key_material_sealed",
            "credential_secret_read", "credential_secret_staged", "biometric_capability_claimed",
            "platform_authenticator_claimed", "host_tpm_state_accessed",
        ):
            if payload.get(key) is not False:
                return ChangeStatus.FAIL, f"TPM staging must not claim/inspect hardware, PCRs, key material, biometrics or platform-authenticator state: {key}."
        for key in (
            "preserve_existing_primary_authentication", "require_tpm_hardware_verification_before_apply",
            "require_tpm_ownership_verification_before_apply", "require_pcr_policy_review_before_sealing",
            "require_key_generation_and_sealing_only_at_verified_apply", "require_recovery_username_reverification_before_apply",
            "require_target_package_reverification_before_apply", "source_read_only", "preserve_unrelated", "stage_only",
        ):
            if payload.get(key) is not True:
                return ChangeStatus.FAIL, f"TPM key-protection safety requirement missing: {key}."
        return ChangeStatus.PASS, "TPM key-protection policy is source-hash locked, target TPM2/TSS2 package-evidence bound, hardware/ownership/PCR/key operations deferred, biometric/platform-authenticator claims excluded, preservation-first and staging-only."

    if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type", "")) == "system_identity":
        source_sha = str(change.payload.get("source_sha256", "")).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            return ChangeStatus.FAIL, "Identity/account plan is not locked to a valid source SHA-256."
        if change.payload.get("rootfs_identity_verified") is not True:
            return ChangeStatus.FAIL, "Identity/account plan lacks verified rootfs account evidence."
        if change.payload.get("shadow_read") is not False or change.payload.get("credential_secret_staged") is not False:
            return ChangeStatus.FAIL, "Identity/account plan must not read shadow credentials or stage credential secrets."
        if str(change.payload.get("credential_policy", "")) != "deferred_secure_verified_apply":
            return ChangeStatus.FAIL, "Credential handling must remain deferred to a later secure verified apply gate."
        if str(change.payload.get("operation", "")) != "configure_default_user":
            return ChangeStatus.FAIL, "Unsupported identity/account operation."
        username = str(change.payload.get("username", "")).strip()
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            return ChangeStatus.FAIL, "Username is not a safe Linux account name."
        display_name = str(change.payload.get("display_name", ""))
        if len(display_name) > 128 or any(ch in display_name for ch in ("\r", "\n", "\x00", ":")):
            return ChangeStatus.FAIL, "Display/full name contains unsupported data."
        role = str(change.payload.get("account_role", ""))
        if role not in {"standard", "administrator"}:
            return ChangeStatus.FAIL, "Account role is not supported."
        admin_group = str(change.payload.get("admin_group", "")).strip()
        if role == "administrator" and admin_group not in {"sudo", "wheel"}:
            return ChangeStatus.FAIL, "Administrator plans require an explicitly verified distro admin group."
        if role == "standard" and admin_group:
            return ChangeStatus.FAIL, "Standard-user plans must not stage administrative group membership."
        uid_min = change.payload.get("uid_min")
        if not isinstance(uid_min, int) or isinstance(uid_min, bool) or not 100 <= uid_min <= 60000:
            return ChangeStatus.FAIL, "Identity/account UID_MIN evidence is invalid."
        for key in ("passwd_layer", "group_layer"):
            layer = str(change.payload.get(key, "")).strip()
            if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
                return ChangeStatus.FAIL, "Identity/account plan is not bound to explicit SquashFS account evidence."
        if change.payload.get("source_read_only") is not True or change.payload.get("preserve_unrelated") is not True:
            return ChangeStatus.FAIL, "Identity/account plan must keep the source ISO read-only and preserve unrelated configuration."
        if change.payload.get("stage_only") is not True:
            return ChangeStatus.FAIL, "Alpha 37 identity/account plans must remain staging-only."
        return ChangeStatus.PASS, "Identity/account plan is source-hash locked, rootfs-evidence bound, credential-secret free, preservation-first and staging-only."
    return ChangeStatus.UNVERIFIED, "No preflight is implemented for this change type yet."
