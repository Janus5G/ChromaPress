from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlparse

SUPPORTED = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}

_INSTALLER_MAP = {
    "Anaconda/Kickstart": ("kickstart", "RHEL / Rocky / Alma / Oracle native Kickstart"),
    "Subiquity/Autoinstall": ("autoinstall", "Ubuntu Subiquity Autoinstall / cloud-init YAML"),
    "Debian Installer/Preseed": ("preseed", "Debian Installer Preseed"),
}

_DESKTOP_SIGNATURES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("KDE Plasma", ("plasma-desktop", "plasma-workspace"), "kde-config"),
    ("GNOME", ("gnome-shell",), "gsettings"),
    ("LXQt", ("lxqt-session", "lxqt-panel"), "lxqt-config"),
    ("XFCE", ("xfce4-session", "xfce4-panel"), "xfconf"),
    ("Cinnamon", ("cinnamon", "cinnamon-session"), "gsettings"),
    ("MATE", ("mate-session-manager", "mate-panel"), "gsettings"),
)

_BROWSER_SIGNATURES = (
    "firefox", "firefox-esr", "chromium", "chromium-browser", "google-chrome-stable",
)


def _matches_package(packages: Iterable[str], signature: str) -> bool:
    s = signature.casefold()
    return any(p.casefold() == s or p.casefold().startswith(s + "-") for p in packages)


def installer_capability(installer: str, package_format: str, evidence: list[dict[str, Any]], configs: list[str]) -> dict[str, Any]:
    family = str(installer or "unknown")
    generator, description = _INSTALLER_MAP.get(family, ("", ""))
    if generator:
        status = "SUPPORTED_WITH_REQUIREMENTS"
        reason = (
            f"Verified {family} evidence permits a structured {generator} template. "
            "Credential material and native installer-tool validation remain deferred to verified apply."
        )
    elif family in {"Calamares", "Ubiquity"}:
        status = "UNSUPPORTED"
        reason = (
            f"{family} is positively identified, but Part 5 native generation is intentionally limited to "
            "Kickstart, Subiquity Autoinstall and Debian Preseed. Existing installer configuration is preserved."
        )
    else:
        status = "UNKNOWN"
        reason = "No supported native installer family was positively verified; structured installer staging is fail-closed."
    return {
        "schema": 1,
        "part": 5,
        "analysis_scope": "target_iso_installer_evidence",
        "capability_status": status,
        "installer_family": family,
        "native_generator": generator,
        "native_generator_description": description,
        "package_format": str(package_format or ""),
        "supported_settings": [
            "username", "display_name", "groups", "admin", "credential_policy", "hostname",
            "language", "locale", "keyboard", "timezone", "network", "dns", "package_selections",
            "installer_profile", "installation_behavior", "partitioning_advanced_expert",
        ],
        "installer_evidence_count": len(evidence or []),
        "installer_config_paths": [str(x) for x in (configs or [])],
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "native_tool_validation_performed": False,
        "require_native_tool_validation_before_apply": True,
        "require_secure_credential_material_before_apply": True,
        "source_read_only": True,
        "stage_only": True,
        "reason": reason,
    }


def desktop_capability(manifest_versions: dict[str, str]) -> dict[str, Any]:
    packages = sorted(str(k) for k in manifest_versions)
    detected: list[dict[str, Any]] = []
    for name, signatures, adapter in _DESKTOP_SIGNATURES:
        hits = [sig for sig in signatures if _matches_package(packages, sig)]
        if hits:
            detected.append({"desktop": name, "adapter": adapter, "package_signatures": hits})
    if len(detected) == 1:
        status = "SUPPORTED_WITH_REQUIREMENTS"
        active = detected[0]
        reason = f"{active['desktop']} package signatures were verified; native adapter changes require target-path re-verification before apply."
    elif len(detected) > 1:
        status = "BLOCKED"
        active = {}
        reason = "Multiple desktop families were detected; ChromaPress will not guess which desktop owns the default session."
    else:
        status = "UNKNOWN"
        active = {}
        reason = "No supported desktop family signature was positively verified. Desktop controls remain hidden/disabled."
    return {
        "schema": 1,
        "part": 5,
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": status,
        "detected_desktops": detected,
        "active_desktop": str(active.get("desktop") or ""),
        "native_adapter": str(active.get("adapter") or ""),
        "supported_controls": [
            "wallpaper", "themes", "icons", "fonts", "panels", "menus", "shortcuts", "favorites",
            "desktop_icons", "autostart", "default_applications", "mime_associations", "display_manager",
            "login_behavior", "default_user_desktop_layout",
        ],
        "desktop_config_contents_read": False,
        "host_desktop_state_accessed": False,
        "source_read_only": True,
        "stage_only": True,
        "reason": reason,
    }


def custom_content_capability(rootfs: list[str]) -> dict[str, Any]:
    verified = bool(rootfs)
    return {
        "schema": 1,
        "part": 5,
        "analysis_scope": "target_iso_rootfs_metadata",
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS" if verified else "UNKNOWN",
        "rootfs_verified": verified,
        "default_user_target": "/etc/skel/",
        "system_overlay_supported": verified,
        "supported_inputs": ["file", "multiple_files", "folder", "drag_drop", "tar.gz"],
        "conflict_policies": ["PRESERVE", "REPLACE", "SKIP"],
        "archive_contents_read_only_when_user_selected": True,
        "source_image_contents_overwritten": False,
        "require_archive_inspection": True,
        "require_path_symlink_conflict_review": True,
        "source_read_only": True,
        "stage_only": True,
        "reason": (
            "Target rootfs metadata is present; custom content may be staged only after source/archive inspection and conflict review."
            if verified else "No target rootfs was verified; custom-content staging is fail-closed."
        ),
    }


def kiosk_capability(manifest_versions: dict[str, str], desktop: dict[str, Any]) -> dict[str, Any]:
    packages = sorted(str(k) for k in manifest_versions)
    weston = _matches_package(packages, "weston")
    browsers = [b for b in _BROWSER_SIGNATURES if _matches_package(packages, b)]
    desktop_ok = str(desktop.get("capability_status") or "") in SUPPORTED
    modes = []
    if desktop_ok:
        modes.extend(["full_desktop", "restricted_desktop", "custom_application_kiosk"])
    if weston:
        modes.extend(["minimal_wayland_weston", "custom_application_kiosk"])
    if browsers and (desktop_ok or weston):
        modes.append("browser_kiosk")
    modes = list(dict.fromkeys(modes))
    status = "SUPPORTED_WITH_REQUIREMENTS" if modes else "UNKNOWN"
    return {
        "schema": 1,
        "part": 5,
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": status,
        "supported_modes": modes,
        "weston_verified": weston,
        "browser_packages": browsers,
        "desktop_dependency_verified": desktop_ok,
        "provider_or_website_hardcoded": False,
        "require_part4_restricted_session_review_before_apply": True,
        "require_part4_recovery_escape_review_before_apply": True,
        "host_session_state_accessed": False,
        "source_read_only": True,
        "stage_only": True,
        "reason": (
            "Generic kiosk modes are exposed only from verified desktop/Weston/browser package evidence. Runtime session validation remains required."
            if modes else "No supported generic kiosk runtime combination was positively verified."
        ),
    }


def validate_linux_username(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", str(value or "").strip()))


def validate_hostname(value: str) -> bool:
    value = str(value or "").strip()
    if len(value) > 253 or not value:
        return False
    return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part or "") for part in value.split("."))


def validate_locale(value: str) -> bool:
    return bool(re.fullmatch(r"(?:C|POSIX|C\.UTF-8|[A-Za-z]{2,3}_[A-Za-z]{2}(?:\.[A-Za-z0-9_-]+)?(?:@[A-Za-z0-9_-]+)?)", str(value or "").strip()))


def validate_keyboard(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(value or "").strip()))


def validate_timezone(value: str) -> bool:
    value = str(value or "").strip()
    return bool(value and len(value) <= 128 and ".." not in value and re.fullmatch(r"[A-Za-z0-9_+\-/]+", value))


def _yaml_q(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _safe_list(raw: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and re.fullmatch(r"[A-Za-z0-9_.+@:/-]{1,128}", text):
            out.append(text)
    return list(dict.fromkeys(out))


def generate_installer_template(payload: dict[str, Any]) -> str:
    """Generate an inspectable credential-free native-family template.

    The placeholder is intentionally not a real credential. Apply must replace it
    through the secure credential channel and run the distro-native validator.
    """
    generator = str(payload.get("native_generator") or "")
    username = str(payload.get("username") or "").strip()
    full_name = str(payload.get("display_name") or "").strip()
    hostname = str(payload.get("hostname") or "").strip()
    locale = str(payload.get("locale") or "").strip()
    keyboard = str(payload.get("keyboard") or "").strip()
    timezone = str(payload.get("timezone") or "").strip()
    groups = _safe_list(payload.get("groups") or [])
    packages = _safe_list(payload.get("package_selections") or [])
    admin = bool(payload.get("admin"))
    network_mode = str(payload.get("network_mode") or "dhcp")
    dns = _safe_list(payload.get("dns_servers") or [])
    credential = "${CHROMAPRESS_PASSWORD_HASH}"
    partition = str(payload.get("partitioning") or "preserve_installer_default")

    if generator == "kickstart":
        group_values = list(groups)
        if admin and "wheel" not in group_values:
            group_values.append("wheel")
        lines = [
            "# Generated by ChromaPress — staged template; secure credential injection + ksvalidator required before apply",
            f"lang {locale}", f"keyboard {keyboard}", f"timezone {timezone} --utc",
            f"network --bootproto={'dhcp' if network_mode == 'dhcp' else 'static'} --hostname={hostname}",
        ]
        if network_mode == "static":
            lines[-1] += f" --ip={payload.get('ipv4_address','')} --gateway={payload.get('gateway','')}"
            if dns:
                lines[-1] += " --nameserver=" + ",".join(dns)
        user = f"user --name={username} --password={credential} --iscrypted"
        if full_name:
            user += f" --gecos={full_name!r}"
        if group_values:
            user += " --groups=" + ",".join(group_values)
        lines.append(user)
        if partition == "guided_use_entire_disk":
            lines.extend(["clearpart --all --initlabel", "autopart"])
        if packages:
            lines.extend(["%packages", *packages, "%end"])
        return "\n".join(lines) + "\n"

    if generator == "autoinstall":
        lines = [
            "#cloud-config",
            "# Generated by ChromaPress — staged template; secure credential injection + native schema validation required before apply",
            "autoinstall:", "  version: 1", "  identity:",
            f"    hostname: {_yaml_q(hostname)}", f"    username: {_yaml_q(username)}",
            f"    password: {_yaml_q(credential)}", f"    realname: {_yaml_q(full_name or username)}",
            f"  locale: {_yaml_q(locale)}", "  keyboard:", f"    layout: {_yaml_q(keyboard)}",
            f"  timezone: {_yaml_q(timezone)}",
        ]
        if packages:
            lines.append("  packages:")
            lines.extend(f"    - {_yaml_q(p)}" for p in packages)
        if partition == "guided_use_entire_disk":
            lines.extend(["  storage:", "    layout:", "      name: direct"])
        return "\n".join(lines) + "\n"

    if generator == "preseed":
        lines = [
            "# Generated by ChromaPress — staged template; secure credential injection + debconf validation required before apply",
            f"d-i debian-installer/locale string {locale}",
            f"d-i keyboard-configuration/xkb-keymap select {keyboard}",
            f"d-i time/zone string {timezone}",
            f"d-i netcfg/get_hostname string {hostname}",
            f"d-i passwd/user-fullname string {full_name or username}",
            f"d-i passwd/username string {username}",
            f"d-i passwd/user-password-crypted password {credential}",
        ]
        if packages:
            lines.append("d-i pkgsel/include string " + " ".join(packages))
        if partition == "guided_use_entire_disk":
            lines.extend([
                "d-i partman-auto/method string regular",
                "d-i partman-auto/choose_recipe select atomic",
            ])
        return "\n".join(lines) + "\n"
    raise ValueError("unsupported native installer generator")


def validate_installer_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    generator = str(payload.get("native_generator") or "")
    if generator not in {"kickstart", "autoinstall", "preseed"}:
        return False, "unsupported native installer generator"
    family = str(payload.get("installer_family") or "")
    expected_generator = (_INSTALLER_MAP.get(family) or ("", ""))[0]
    if expected_generator != generator:
        return False, "native installer generator does not match verified installer family"
    if str(payload.get("capability_status") or "") not in SUPPORTED:
        return False, "installer capability is not supported"
    if not validate_linux_username(str(payload.get("username") or "")):
        return False, "invalid username"
    if not validate_hostname(str(payload.get("hostname") or "")):
        return False, "invalid hostname"
    if not validate_locale(str(payload.get("locale") or "")):
        return False, "invalid locale"
    if not validate_keyboard(str(payload.get("keyboard") or "")):
        return False, "invalid keyboard layout"
    if not validate_timezone(str(payload.get("timezone") or "")):
        return False, "invalid timezone"
    if str(payload.get("credential_policy") or "") != "secure_hash_deferred_to_verified_apply":
        return False, "credential policy must defer secrets to verified apply"
    for secret_key in ("password", "password_hash", "credential", "credential_secret"):
        if str(payload.get(secret_key) or ""):
            return False, "credential secrets must not be present in staged payload"
    if str(payload.get("network_mode") or "") not in {"dhcp", "static"}:
        return False, "unsupported network mode"
    if payload.get("network_mode") == "static":
        try:
            ipaddress.ip_interface(str(payload.get("ipv4_address") or ""))
            ipaddress.ip_address(str(payload.get("gateway") or ""))
            for value in payload.get("dns_servers") or []:
                ipaddress.ip_address(str(value))
        except ValueError:
            return False, "invalid static IPv4/DNS configuration"
    partition = str(payload.get("partitioning") or "")
    if partition not in {"preserve_installer_default", "guided_use_entire_disk"}:
        return False, "unsupported partitioning intent"
    if partition == "guided_use_entire_disk" and payload.get("destructive_partitioning_confirmed") is not True:
        return False, "destructive partitioning requires explicit confirmation"
    if payload.get("native_tool_validation_performed") is not False or payload.get("require_native_tool_validation_before_apply") is not True:
        return False, "native validation must remain a verified-apply requirement"
    if payload.get("source_read_only") is not True or payload.get("stage_only") is not True:
        return False, "installer plan must remain source-read-only and staging-only"
    try:
        template = generate_installer_template(payload)
    except Exception as exc:
        return False, str(exc)
    if "${CHROMAPRESS_PASSWORD_HASH}" not in template:
        return False, "generated template lost the secure credential placeholder"
    return True, "structured installer template validated; native tool and secure credential injection remain required before apply"


def _safe_archive_member(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return False
    return True


def _safe_symlink(member_name: str, linkname: str) -> bool:
    if not linkname or "\x00" in linkname or linkname.startswith("/") or "\\" in linkname:
        return False
    base = PurePosixPath(member_name).parent
    target = base.joinpath(PurePosixPath(linkname))
    depth = 0
    for part in target.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        else:
            depth += 1
    return True


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_custom_content(paths: Iterable[str], *, max_entries: int = 5000) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    total = 0
    for raw in paths:
        p = Path(str(raw)).expanduser()
        if not p.exists():
            raise ValueError(f"custom-content source does not exist: {p}")
        if p.is_symlink():
            raise ValueError(f"top-level symlink source is not accepted: {p}")
        if p.is_file() and (p.name.casefold().endswith(".tar.gz") or p.suffix.casefold() == ".tgz"):
            archive_members: list[dict[str, Any]] = []
            with tarfile.open(p, "r:gz") as tf:
                members = tf.getmembers()
                if len(members) > max_entries:
                    raise ValueError("archive contains too many entries")
                for m in members:
                    if not _safe_archive_member(m.name):
                        raise ValueError(f"unsafe archive path: {m.name}")
                    if (m.issym() or m.islnk()) and not _safe_symlink(m.name, m.linkname):
                        raise ValueError(f"unsafe archive symlink: {m.name} -> {m.linkname}")
                    if m.ischr() or m.isblk() or m.isfifo():
                        raise ValueError(f"special archive node is not accepted: {m.name}")
                    archive_members.append({
                        "path": m.name,
                        "type": "symlink" if (m.issym() or m.islnk()) else "dir" if m.isdir() else "file",
                        "size": int(m.size or 0),
                        "mode": oct(int(m.mode or 0) & 0o777),
                        "uid": int(m.uid or 0),
                        "gid": int(m.gid or 0),
                        "link_target": m.linkname if (m.issym() or m.islnk()) else "",
                    })
            total += len(archive_members)
            entries.append({"source": str(p.resolve()), "kind": "tar.gz", "sha256": _file_sha(p), "members": archive_members})
        elif p.is_file():
            st = p.stat()
            total += 1
            entries.append({
                "source": str(p.resolve()), "kind": "file", "sha256": _file_sha(p), "size": int(st.st_size),
                "mode": oct(st.st_mode & 0o777), "members": [{"path": p.name, "type": "file", "size": int(st.st_size), "mode": oct(st.st_mode & 0o777)}],
            })
        elif p.is_dir():
            members: list[dict[str, Any]] = []
            root = p.resolve()
            for current, dirs, files in os.walk(root, followlinks=False):
                cur = Path(current)
                for name in list(dirs) + list(files):
                    q = cur / name
                    rel = q.relative_to(root).as_posix()
                    if len(members) >= max_entries:
                        raise ValueError("folder contains too many entries")
                    if q.is_symlink():
                        target = os.readlink(q)
                        if not _safe_symlink(rel, target):
                            raise ValueError(f"unsafe folder symlink: {rel} -> {target}")
                        members.append({"path": rel, "type": "symlink", "size": 0, "mode": oct(q.lstat().st_mode & 0o777), "link_target": target})
                    elif q.is_dir():
                        members.append({"path": rel, "type": "dir", "size": 0, "mode": oct(q.stat().st_mode & 0o777)})
                    elif q.is_file():
                        members.append({"path": rel, "type": "file", "size": int(q.stat().st_size), "mode": oct(q.stat().st_mode & 0o777)})
            total += len(members)
            entries.append({"source": str(root), "kind": "folder", "members": members})
        else:
            raise ValueError(f"unsupported custom-content source: {p}")
    if not entries:
        raise ValueError("select at least one file, folder or .tar.gz archive")
    return {"entries": entries, "entry_count": total, "archive_inspected": True, "safe_paths_verified": True, "symlinks_validated": True}


def validate_custom_content_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if str(payload.get("capability_status") or "") not in SUPPORTED:
        return False, "custom-content capability is not supported"
    target_kind = str(payload.get("target_kind") or "")
    if target_kind not in {"default_user_content", "system_overlay"}:
        return False, "unsupported custom-content target"
    target = str(payload.get("target_root") or "")
    if target_kind == "default_user_content":
        parts = PurePosixPath(target).parts
        if not target.startswith("/etc/skel/") or ".." in parts:
            return False, "default-user content must stay under /etc/skel/"
    if target_kind == "system_overlay":
        if not target.startswith("/") or ".." in PurePosixPath(target).parts or target in {"/", "/proc", "/sys", "/dev", "/run", "/boot", "/efi"}:
            return False, "unsafe system overlay target"
    if str(payload.get("conflict_policy") or "") not in {"PRESERVE", "REPLACE", "SKIP"}:
        return False, "unsupported conflict policy"
    if payload.get("conflict_policy") == "REPLACE" and payload.get("replace_unknown_content_confirmed") is not True:
        return False, "REPLACE requires explicit review/confirmation"
    if not isinstance(payload.get("entries"), list) or not payload.get("entries"):
        return False, "no inspected custom-content entries were staged"
    for key in ("archive_inspected", "safe_paths_verified", "symlinks_validated", "show_target_paths", "show_conflicts", "show_ownership", "show_permissions", "require_review_before_apply", "require_target_conflict_review_before_apply", "source_read_only", "preserve_unrelated", "stage_only"):
        if payload.get(key) is not True:
            return False, f"custom-content safety requirement missing: {key}"
    return True, "custom content is inspected, path/symlink reviewed, conflict-policy explicit and staging-only"


def validate_desktop_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if str(payload.get("capability_status") or "") not in SUPPORTED:
        return False, "desktop capability is not supported"
    if not str(payload.get("active_desktop") or "") or not str(payload.get("native_adapter") or ""):
        return False, "desktop-native adapter evidence is missing"
    controls = payload.get("controls")
    if not isinstance(controls, dict) or not controls:
        return False, "at least one desktop control is required"
    allowed = {
        "wallpaper", "theme", "icons", "font", "panels", "menus", "shortcuts", "favorites", "desktop_icons",
        "autostart", "default_applications", "mime_associations", "display_manager", "login_behavior", "default_user_desktop_layout",
    }
    if any(str(k) not in allowed for k in controls):
        return False, "desktop plan contains an unsupported control"
    for value in controls.values():
        if isinstance(value, str) and ("\x00" in value or "\n" in value or len(value) > 2048):
            return False, "desktop control contains unsafe text"
    for key in ("desktop_config_contents_read", "host_desktop_state_accessed"):
        if payload.get(key) is not False:
            return False, f"desktop staging must not use protected state: {key}"
    for key in ("require_native_adapter_reverification_before_apply", "preserve_unrelated_desktop_configuration", "source_read_only", "stage_only"):
        if payload.get(key) is not True:
            return False, f"desktop safety requirement missing: {key}"
    return True, "desktop plan is native-adapter bound, preservation-first and staging-only"


def validate_kiosk_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if str(payload.get("capability_status") or "") not in SUPPORTED:
        return False, "kiosk capability is not supported"
    mode = str(payload.get("mode") or "")
    if mode not in set(str(x) for x in payload.get("supported_modes") or []):
        return False, "kiosk mode is not positively supported by target evidence"
    target = str(payload.get("target") or "").strip()
    if mode == "browser_kiosk":
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "browser kiosk requires an explicit http/https URL"
    if mode in {"custom_application_kiosk", "minimal_wayland_weston"}:
        if not target.startswith("/") or ".." in PurePosixPath(target).parts:
            return False, "application kiosk target must be an absolute safe target-system path"
    if mode == "minimal_wayland_weston" and payload.get("weston_verified") is not True:
        return False, "Weston mode requires verified Weston package evidence"
    if payload.get("provider_or_website_hardcoded") is not False:
        return False, "kiosk configuration must remain generic"
    for key in ("fullscreen", "autostart", "restricted_session_controls", "controlled_recovery_escape", "require_runtime_session_validation_before_apply", "require_part4_security_review_before_apply", "source_read_only", "stage_only"):
        if payload.get(key) is not True:
            return False, f"kiosk safety requirement missing: {key}"
    return True, "generic kiosk plan is evidence-bound, runtime-validation gated, recovery-aware and staging-only"
