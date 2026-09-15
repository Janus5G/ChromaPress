from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from chromapress.services.part5 import installer_capability, desktop_capability, custom_content_capability, kiosk_capability


def _run(args: list[str]) -> str:
    cp = subprocess.run(args, text=True, capture_output=True, check=False)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or f"command exited {cp.returncode}").strip())
    return cp.stdout


def _optional_run(args: list[str]) -> str:
    """Best-effort read-only probe used for optional source metadata."""
    try:
        cp = subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError:
        return ""
    if cp.returncode != 0:
        return ""
    return (cp.stdout or "") + (("\n" + cp.stderr) if cp.stderr else "")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iso_files(path: Path) -> list[str]:
    listing = _run(["xorriso", "-indev", str(path), "-find", "/", "-type", "f"])
    files: list[str] = []
    for raw in listing.splitlines():
        item = raw.strip().strip("'\"")
        if item.startswith("/"):
            files.append(item)
    return sorted(set(files))


def _rootfs_layers(files: list[str]) -> list[str]:
    candidates = [
        x for x in files
        if x.lower().endswith(".squashfs")
        and any(part in x.lower() for part in ("/casper/", "/live/", "/liveos/"))
    ]

    def order(member: str) -> tuple[int, int, str]:
        name = Path(member).name.lower()
        # Ubuntu/Lubuntu layered Casper: base -> standard -> standard.live.
        if name == "minimal.squashfs":
            rank = 10
        elif name == "minimal.standard.squashfs":
            rank = 20
        elif name == "minimal.standard.live.squashfs":
            rank = 30
        elif name == "filesystem.squashfs":
            rank = 40
        else:
            rank = 50
        return (rank, name.count("."), name)

    return sorted(candidates, key=order)


def _boot_source_metadata(files: list[str], el_torito_report: str = "", system_area_report: str = "") -> dict:
    """Derive conservative boot/kernel metadata from ISO-visible evidence only."""
    low_files = [x.lower() for x in files]
    file_set = set(files)

    bootloaders: list[str] = []
    if any("/grub/" in x or "grubx64.efi" in x or "grubaa64.efi" in x for x in low_files):
        bootloaders.append("GRUB")
    if any("isolinux" in x or "syslinux" in x for x in low_files):
        bootloaders.append("Syslinux/ISOLINUX")
    if any("systemd-boot" in x or "/efi/systemd/" in x or "loader/loader.conf" in x for x in low_files):
        bootloaders.append("systemd-boot")

    boot_catalog = ""
    for member in files:
        name = Path(member).name.lower()
        if name in {"boot.catalog", "boot.cat"} or name.endswith(".catalog"):
            boot_catalog = member
            break

    boot_config_names = {"grub.cfg", "isolinux.cfg", "syslinux.cfg", "loader.conf", "grub.conf"}
    boot_configs = sorted(
        member for member in files
        if Path(member).name.lower() in boot_config_names
        or ("/loader/entries/" in member.lower() and member.lower().endswith(".conf"))
    )

    efi_images = sorted(
        member for member in files
        if member.lower().endswith(".efi") or Path(member).name.lower() in {"efi.img", "efiboot.img"}
    )
    kernel_images = sorted(
        member for member in files
        if Path(member).name.lower().startswith(("vmlinuz", "vmlinux"))
        or Path(member).name.lower() in {"linux", "linuxefi"}
    )
    initramfs_images = sorted(
        member for member in files
        if Path(member).name.lower().startswith(("initrd", "initramfs"))
    )

    firmware_hints = sorted(
        member for member in files
        if "firmware" in member.lower() and not member.lower().endswith((".md", ".txt"))
    )[:50]

    if not boot_catalog:
        boot_catalog = _catalog_from_el_torito_report(el_torito_report)

    el_low = el_torito_report.lower()
    sys_low = system_area_report.lower()
    el_torito = bool(el_torito_report.strip()) or bool(boot_catalog)
    bios = any("isolinux" in x or "syslinux" in x for x in low_files)
    uefi = any("/efi/boot/" in x or x.endswith("efi.img") or x.endswith("efiboot.img") for x in low_files)
    if el_low:
        bios = bios or "bios" in el_low
        uefi = uefi or "uefi" in el_low or "platform 0xef" in el_low or "platform_id 0xef" in el_low
    hybrid = any(token in sys_low for token in ("isohybrid", "mbr", "gpt", "apm"))

    return {
        "bios_boot": bios,
        "uefi_boot": uefi,
        "el_torito_boot": el_torito,
        "hybrid_boot": hybrid,
        "bootloaders": bootloaders,
        "boot_catalog": boot_catalog,
        "boot_config_files": boot_configs,
        "efi_images": efi_images,
        "kernel_images": kernel_images,
        "initramfs_images": initramfs_images,
        "firmware_hints": firmware_hints,
    }



def _catalog_from_el_torito_report(report: str) -> str:
    """Return catalog evidence from xorriso without inventing a filesystem path."""
    for raw in report.splitlines():
        line = raw.strip()
        low = line.lower()
        if "cat path" in low and ":" in line:
            value = line.split(":", 1)[1].strip().strip("'\"")
            if value:
                return value
    for raw in report.splitlines():
        line = raw.strip()
        low = line.lower()
        if "el torito catalog" in low and ":" in line:
            value = line.split(":", 1)[1].strip()
            if value:
                return f"xorriso catalog evidence: {value}"
    return ""


def _parse_boot_config_text(member: str, text: str) -> dict[str, list[object]]:
    """Parse only explicit declarations from bootloader configuration text."""
    entries: list[dict[str, str]] = []
    defaults: list[str] = []
    timeouts: list[str] = []
    kernel_arguments: list[dict[str, str]] = []
    source = member
    current_label = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # GRUB menuentry 'Title' ... / menuentry "Title" ...
        m = re.match(r"^menuentry\s+(['\"])(.*?)\1", line, re.I)
        if m:
            entries.append({"source": source, "title": m.group(2).strip(), "id": ""})
            continue

        # Syslinux/ISOLINUX LABEL followed by optional MENU LABEL.
        m = re.match(r"^label\s+(\S+)", line, re.I)
        if m:
            current_label = m.group(1)
            entries.append({"source": source, "title": current_label, "id": current_label})
            continue
        m = re.match(r"^menu\s+label\s+(.+)$", line, re.I)
        if m and current_label and entries:
            entries[-1]["title"] = m.group(1).strip().lstrip("^-")
            continue

        # systemd-boot entry files use 'title'.
        if "/loader/entries/" in source.lower():
            m = re.match(r"^title\s+(.+)$", line, re.I)
            if m:
                entries.append({"source": source, "title": m.group(1).strip(), "id": Path(source).stem})
                continue

        # Defaults and timeouts are displayed as declarations, not claimed active.
        m = re.match(r"^(?:set\s+)?default\s*=\s*['\"]?([^'\"\s]+)", line, re.I)
        if not m:
            m = re.match(r"^default\s+(.+)$", line, re.I)
        if m:
            value = m.group(1).strip().strip("'\"")
            defaults.append(f"{value} ({source})")
            continue

        m = re.match(r"^(?:set\s+)?timeout\s*=\s*['\"]?([^'\"\s]+)", line, re.I)
        if m:
            timeouts.append(f"{m.group(1)} s ({source})")
            continue
        m = re.match(r"^timeout\s+(\d+)\s*$", line, re.I)
        if m:
            # Syslinux TIMEOUT is in tenths of a second.
            seconds = int(m.group(1)) / 10.0
            timeouts.append(f"{seconds:g} s ({source}; Syslinux TIMEOUT={m.group(1)})")
            continue

        # Kernel command lines. Preserve exact args after the kernel path.
        m = re.match(r"^(?:linux|linuxefi|linux16)\s+\S+\s*(.*)$", line, re.I)
        if m:
            args = m.group(1).strip()
            if args:
                kernel_arguments.append({"source": source, "args": args})
            continue
        m = re.match(r"^append\s+(.+)$", line, re.I)
        if m:
            kernel_arguments.append({"source": source, "args": m.group(1).strip()})

    # De-duplicate while keeping source evidence and order.
    def unique_strings(values: list[str]) -> list[str]:
        seen: set[str] = set(); out: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value); out.append(value)
        return out

    def unique_dicts(values: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, str]]:
        seen: set[tuple[str, ...]] = set(); out: list[dict[str, str]] = []
        for value in values:
            key = tuple(value.get(k, "") for k in keys)
            if key not in seen:
                seen.add(key); out.append(value)
        return out

    return {
        "boot_entries": unique_dicts(entries, ("source", "title", "id"))[:100],
        "boot_defaults": unique_strings(defaults)[:25],
        "boot_timeouts": unique_strings(timeouts)[:25],
        "kernel_arguments": unique_dicts(kernel_arguments, ("source", "args"))[:100],
    }


def _boot_config_readonly_details(iso: Path, configs: list[str]) -> dict[str, list[object]]:
    result: dict[str, list[object]] = {
        "boot_entries": [], "boot_defaults": [], "boot_timeouts": [], "kernel_arguments": [],
    }
    if not configs:
        return result
    with tempfile.TemporaryDirectory(prefix="chromapress-boot-config-") as td:
        work = Path(td)
        for index, member in enumerate(configs[:50]):
            target = work / f"config-{index}.txt"
            try:
                _extract_iso_member(iso, member, target)
            except RuntimeError:
                continue
            parsed = _parse_boot_config_text(member, target.read_text(encoding="utf-8", errors="ignore"))
            for key in result:
                result[key].extend(parsed[key])
    # Cross-file de-duplication.
    result["boot_defaults"] = list(dict.fromkeys(result["boot_defaults"]))[:25]
    result["boot_timeouts"] = list(dict.fromkeys(result["boot_timeouts"]))[:25]
    for key, fields in (("boot_entries", ("source", "title", "id")), ("kernel_arguments", ("source", "args"))):
        seen = set(); deduped = []
        for item in result[key]:
            marker = tuple(str(item.get(field, "")) for field in fields)
            if marker not in seen:
                seen.add(marker); deduped.append(item)
        result[key] = deduped[:100]
    return result


def _hardware_package_hints(versions: dict[str, str]) -> list[dict[str, str]]:
    """Classify only package names explicitly present in source manifests."""
    hints: list[dict[str, str]] = []
    for package, version in sorted(versions.items()):
        low = package.casefold()
        kind = ""
        if low.startswith(("linux-image", "linux-modules", "linux-generic", "kernel-core", "kernel-modules")) or low == "kernel":
            kind = "Kernel"
        elif low == "linux-firmware" or low.startswith("firmware-") or "microcode" in low:
            kind = "Firmware / microcode"
        elif low == "dkms" or low.endswith("-dkms") or low.startswith(("nvidia-driver", "xserver-xorg-video-")) or low in {"mesa-vulkan-drivers"}:
            kind = "Driver / DKMS"
        if kind:
            hints.append({"package": package, "version": version, "kind": kind})
    return hints[:150]


def _component_inventory(versions: dict[str, str]) -> list[dict[str, object]]:
    """Build a target-image component inventory from authoritative manifest names.

    Categories and protection flags are conservative classifications of package
    names already present in the selected image. No host package database, web
    metadata, invented descriptions or repository claims are used.
    """
    protected_exact = {
        "apt", "dpkg", "rpm", "dnf", "pacman", "zypper",
        "systemd", "systemd-sysv", "init", "base-files", "base-passwd",
        "passwd", "login", "sudo", "coreutils", "bash", "grub-pc",
        "grub-efi-amd64", "grub2", "shim-signed", "shim",
    }

    def category_for(package: str) -> str:
        low = package.casefold()
        if low == "kernel" or low.startswith(("linux-image", "linux-modules", "linux-headers", "linux-generic", "kernel-")):
            return "Kernel"
        if low == "linux-firmware" or low.startswith(("firmware-", "nvidia-", "xserver-xorg-video-")) or "microcode" in low or low.endswith("-dkms") or low == "dkms":
            return "Driver / firmware"
        if low.startswith(("python", "perl", "ruby", "nodejs", "openjdk", "default-jre", "default-jdk", "dotnet", "mono-")):
            return "Runtime"
        if low.startswith(("language-pack", "language-selector", "hunspell-", "aspell-", "myspell-")) or low in {"locales", "tzdata", "keyboard-configuration"}:
            return "Language / locale"
        if low in {"systemd", "systemd-sysv", "dbus", "cron", "cron-daemon-common", "network-manager", "openssh-server", "cups"} or low.endswith(("-daemon", "-service")):
            return "Service"
        if low.startswith(("plasma-", "kde-", "lxqt-", "gnome-", "xfce4", "mate-", "cinnamon")) or low in {"sddm", "lightdm", "gdm3", "gdm"}:
            return "Desktop component"
        if low.startswith("lib"):
            return "Library"
        if low.endswith(("-common", "-data")):
            return "Dependency"
        if low in {"curl", "wget", "rsync", "zip", "unzip", "tar", "gzip", "xz-utils", "bzip2", "nano", "vim", "less"}:
            return "Utility"
        return "System component"

    def protection_for(package: str, category: str) -> tuple[bool, str]:
        low = package.casefold()
        if category == "Kernel":
            return True, "Kernel packages are protected here; ChromaPress must preserve a viable bootable kernel."
        if low in protected_exact or low.startswith(("libc6", "glibc", "grub-", "shim-")):
            return True, "Core boot, package-management or base-system component; direct removal is blocked."
        return False, "Removal requires dependency/dependent analysis and normal Changes preflight."

    inventory: list[dict[str, object]] = []
    for package, version in sorted(versions.items(), key=lambda pair: pair[0].casefold()):
        category = category_for(package)
        protected, reason = protection_for(package, category)
        inventory.append({
            "display_name": package,
            "package": package,
            "version": version,
            "category": category,
            "state": "Installed",
            "source": "selected-image manifest",
            "protected": protected,
            "protection_reason": reason,
        })
    return inventory


def _system_config_evidence(versions: dict[str, str]) -> dict[str, object]:
    """Classify only package names explicitly present in source manifests.

    Part 4 configuration state itself is intentionally not inferred from package
    presence. Enabled services, users, network profiles and policies require
    rootfs-level verification in a later gate.
    """
    evidence: list[dict[str, str]] = []

    def matches(low: str, exact: tuple[str, ...] = (), prefixes: tuple[str, ...] = ()) -> bool:
        return low in exact or any(low.startswith(prefix) for prefix in prefixes)

    for package, version in sorted(versions.items()):
        low = package.casefold()
        area = ""
        if matches(low, ("passwd", "login", "sudo", "accountsservice"), ("libpam-",)):
            area = "Identity / accounts"
        elif matches(low, ("locales", "tzdata", "keyboard-configuration", "console-setup")):
            area = "Locale / keyboard / timezone"
        elif matches(low, ("network-manager", "netplan.io", "resolvconf", "systemd-resolved", "ifupdown"), ("network-manager-",)):
            area = "Networking / DNS"
        elif matches(low, ("sddm", "lightdm", "gdm3", "gdm")):
            area = "Display manager / autologin"
        elif matches(low, ("systemd", "systemd-sysv"), ("systemd-",)):
            area = "Services / startup"
        elif matches(low, ("ufw", "firewalld", "nftables", "iptables")):
            area = "Firewall"
        elif matches(low, ("apparmor", "apparmor-utils"), ("libapparmor",)):
            area = "AppArmor"
        elif matches(low, ("selinux-basics", "policycoreutils"), ("selinux-policy", "libselinux")):
            area = "SELinux"
        elif matches(low, ("procps",)):
            area = "sysctl / kernel settings"
        elif matches(low, ("fido2-tools", "libfido2-1", "libpam-u2f", "pamu2fcfg", "yubikey-manager", "libpam-yubico", "yubikey-personalization"), ("libfido2", "yubikey-")):
            area = "FIDO2 / security keys"
        elif matches(low, ("tpm2-tools",), ("libtss2", "tpm2-")):
            area = "TPM-backed credentials"
        if area:
            evidence.append({"area": area, "package": package, "version": version})

    rootfs_verification = [
        "users/groups/default user + UID/GID/admin policy",
        "hostname/machine identity",
        "active locale/keyboard/timezone",
        "NetworkManager profiles + network restrictions",
        "systemd services enable/disable state + timers/targets/startup policy",
        "SELinux/sysctl policy",
        "login security defaults + system configuration overlays",
        "kiosk restrictions + persistence + administrator/recovery policy",
        "FIDO2/WebAuthn/security-key/platform-authenticator/TPM policy",
    ]
    return {
        "system_package_evidence": evidence[:250],
        "system_rootfs_verification": rootfs_verification,
    }


def _parse_login_defs_uid_min(text: str) -> int:
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "UID_MIN":
            try:
                value = int(fields[1])
            except ValueError:
                break
            if 100 <= value <= 60000:
                return value
    return 1000


def _parse_login_defs_password_policy(text: str) -> dict[str, int | str]:
    """Parse only non-secret password-aging defaults from /etc/login.defs."""
    wanted = {"PASS_MIN_DAYS", "PASS_MAX_DAYS", "PASS_WARN_AGE"}
    values: dict[str, int | str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 2 or fields[0] not in wanted | {"ENCRYPT_METHOD"}:
            continue
        key, value = fields[0], fields[1]
        if key == "ENCRYPT_METHOD":
            # Algorithm name only; never password/hash material.
            values["encrypt_method"] = value[:32]
            continue
        try:
            number = int(value)
        except ValueError:
            continue
        if 0 <= number <= 99999:
            values[{"PASS_MIN_DAYS": "min_days", "PASS_MAX_DAYS": "max_days", "PASS_WARN_AGE": "warn_days"}[key]] = number
    return values


def _parse_login_defs_security_defaults(text: str) -> dict[str, object]:
    """Parse only allowlisted non-secret login security metadata."""
    result: dict[str, object] = {"umask": "", "umask_present": False, "usergroups_enab": ""}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        key, value = fields[0], fields[1]
        if key == "UMASK" and re.fullmatch(r"0?[0-7]{3}", value):
            normalized = value[-3:]
            result["umask"] = normalized
            result["umask_present"] = True
        elif key == "USERGROUPS_ENAB" and value.casefold() in {"yes", "no"}:
            result["usergroups_enab"] = value.casefold()
    return result


def _parse_identity_rootfs(passwd_text: str, group_text: str, login_defs_text: str = "") -> dict[str, object]:
    """Parse target-rootfs users/groups without reading credential secrets.

    Alpha 50 deliberately reads only /etc/passwd, /etc/group and the non-secret
    policy defaults in /etc/login.defs.  /etc/shadow is never requested and no
    Windows/WSL host account database is consulted.
    """
    uid_min = _parse_login_defs_uid_min(login_defs_text)
    passwd_rows: list[dict[str, object]] = []
    account_count = 0
    for raw in passwd_text.splitlines():
        fields = raw.split(":")
        if len(fields) < 7:
            continue
        account_count += 1
        username = fields[0].strip()
        try:
            uid = int(fields[2])
            gid = int(fields[3])
        except ValueError:
            continue
        shell = fields[6].strip()
        shell_fold = shell.casefold()
        if uid >= uid_min and uid != 65534 and shell_fold not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}:
            passwd_rows.append({
                "username": username,
                "uid": uid,
                "gid": gid,
                "display_name": fields[4].split(",", 1)[0].strip()[:128],
                "home": fields[5].strip()[:256],
                "shell": shell[:128],
            })

    raw_groups: list[dict[str, object]] = []
    group_name_by_gid: dict[int, str] = {}
    for raw in group_text.splitlines():
        fields = raw.split(":")
        if len(fields) < 3 or not fields[0].strip():
            continue
        try:
            gid = int(fields[2])
        except ValueError:
            continue
        name = fields[0].strip()
        members = [x.strip() for x in (fields[3] if len(fields) >= 4 else "").split(",") if x.strip()]
        raw_groups.append({"name": name, "gid": gid, "members": members})
        group_name_by_gid.setdefault(gid, name)

    regular_names = {str(row["username"]) for row in passwd_rows}
    membership: dict[str, set[str]] = {name: set() for name in regular_names}
    for row in passwd_rows:
        primary = group_name_by_gid.get(int(row["gid"]))
        if primary:
            membership[str(row["username"])].add(primary)
            row["primary_group"] = primary
        else:
            row["primary_group"] = ""
    for group in raw_groups:
        for member in group["members"]:
            if member in membership:
                membership[member].add(str(group["name"]))

    user_records: list[dict[str, object]] = []
    for row in passwd_rows:
        row = dict(row)
        row["groups"] = sorted(membership.get(str(row["username"]), set()))
        user_records.append(row)
    user_records.sort(key=lambda item: (int(item["uid"]), str(item["username"])))

    # Preserve only regular-user membership detail in returned group records.
    # System/service-account memberships are unnecessary for this planning gate.
    group_records = [
        {
            "name": str(group["name"]),
            "gid": int(group["gid"]),
            "members": sorted(member for member in group["members"] if member in regular_names),
        }
        for group in raw_groups
    ]
    group_records.sort(key=lambda item: (int(item["gid"]), str(item["name"])))
    all_groups = [str(item["name"]) for item in group_records]
    admin_groups = [name for name in ("sudo", "wheel") if name in all_groups]
    password_policy = _parse_login_defs_password_policy(login_defs_text)
    security_defaults = _parse_login_defs_security_defaults(login_defs_text)

    return {
        "uid_min": uid_min,
        "account_count": account_count,
        "regular_users": [str(item["username"]) for item in user_records],
        "user_records": user_records,
        "group_records": group_records,
        "groups": all_groups,
        "admin_groups": admin_groups,
        "default_user_candidate": user_records[0]["username"] if len(user_records) == 1 else "",
        "password_policy": password_policy,
        "security_defaults": security_defaults,
    }


def _system_security_defaults_evidence(identity: dict[str, object]) -> dict[str, object]:
    """Alpha 53 security-settings gate derived only from verified target login.defs evidence."""
    base: dict[str, object] = {
        "gate_version": "alpha53",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "",
        "config_path": "/etc/login.defs",
        "config_layer": "",
        "current_umask": "",
        "umask_directive_present": False,
        "usergroups_enab": "",
        "metadata_keys_read": ["UMASK", "USERGROUPS_ENAB"],
        "supported_umasks": [],
        "supported_operations": [],
        "full_config_exposed": False,
        "credential_secret_read": False,
        "host_security_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — target login security defaults have not been verified.",
    }
    if identity.get("verified") is not True:
        base["reason"] = "UNKNOWN — target account/rootfs evidence is not verified; security-default staging stays blocked."
        return base
    if identity.get("login_defs_present") is not True:
        base["reason"] = "UNKNOWN — /etc/login.defs was not verified in the target rootfs; absence is not treated as unsupported."
        return base
    layer = str(identity.get("login_defs_layer") or "")
    if not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
        base["reason"] = "UNKNOWN — /etc/login.defs is not bound to an explicit target SquashFS layer."
        return base
    metadata = dict(identity.get("security_defaults") or {})
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "backend": "shadow-utils-login.defs",
        "config_layer": layer,
        "current_umask": str(metadata.get("umask") or ""),
        "umask_directive_present": metadata.get("umask_present") is True,
        "usergroups_enab": str(metadata.get("usergroups_enab") or ""),
        "supported_umasks": ["022", "027", "077"],
        "supported_operations": ["set_default_umask"],
        "reason": (
            "PASS — target /etc/login.defs security metadata verified read-only. Only UMASK and USERGROUPS_ENAB metadata are exposed; "
            "credentials and host security state are not read. Effective session semantics must be re-verified before apply."
        ),
    })
    return base


def _system_kiosk_user_evidence(identity: dict[str, object]) -> dict[str, object]:
    """Alpha 55 capability for a dedicated non-admin kiosk account.

    The gate is derived exclusively from Alpha 50 target-rootfs account evidence.
    It does not inspect host accounts, /etc/shadow, credentials, login restrictions,
    session policy, autologin, or desktop/kiosk configuration.
    """
    base: dict[str, object] = {
        "gate_version": "alpha55",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "passwd-group",
        "passwd_layer": "",
        "group_layer": "",
        "uid_min": 1000,
        "existing_regular_users": [],
        "existing_user_uids": [],
        "available_groups": [],
        "admin_groups": [],
        "supported_operations": [],
        "shadow_read": False,
        "credential_secret_read": False,
        "host_accounts_touched": False,
        "login_policy_inspected": False,
        "session_policy_inspected": False,
        "source_read_only": True,
        "reason": "UNKNOWN — dedicated kiosk-account capability has not been verified from the target rootfs.",
    }
    if identity.get("verified") is not True:
        base["reason"] = "UNKNOWN — target users/groups evidence is not verified; dedicated kiosk-user staging stays blocked."
        return base
    if str(identity.get("users_groups_status") or "UNKNOWN") not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = "UNKNOWN — target users/groups capability is not verified as safely stageable."
        return base
    passwd_layer = str(identity.get("passwd_layer") or "")
    group_layer = str(identity.get("group_layer") or "")
    if not (passwd_layer.startswith("/") and passwd_layer.casefold().endswith(".squashfs") and group_layer.startswith("/") and group_layer.casefold().endswith(".squashfs")):
        base["reason"] = "UNKNOWN — account databases are not bound to explicit target SquashFS layers."
        return base
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "passwd_layer": passwd_layer,
        "group_layer": group_layer,
        "uid_min": int(identity.get("uid_min") or 1000),
        "existing_regular_users": [str(x) for x in (identity.get("regular_users") or [])],
        "existing_user_uids": [int(x.get("uid")) for x in (identity.get("user_records") or []) if isinstance(x, dict) and isinstance(x.get("uid"), int)],
        "available_groups": [str(x) for x in (identity.get("groups") or [])],
        "admin_groups": [str(x) for x in (identity.get("admin_groups") or [])],
        "supported_operations": ["create_dedicated_non_admin_kiosk_user"],
        "reason": (
            "PASS — target /etc/passwd and /etc/group evidence supports staging a new dedicated non-admin kiosk account. "
            "Administrative membership is forbidden; credentials, restricted login, session policy and autologin are deliberately deferred to later gates."
        ),
    })
    return base


def _system_restricted_login_evidence(iso: Path, layers: list[str], identity: dict[str, object]) -> dict[str, object]:
    """Alpha 56 target-only capability for restricting kiosk password login.

    The gate verifies only that target account metadata and a target-rootfs account
    management tool capable of locking password authentication are present. It does
    not read /etc/shadow, PAM contents, SSH configuration, host account/login state,
    autologin policy or desktop/session policy.
    """
    base: dict[str, object] = {
        "gate_version": "alpha56",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "",
        "management_tool_path": "",
        "management_tool_layer": "",
        "passwd_layer": "",
        "group_layer": "",
        "existing_regular_users": [],
        "admin_users": [],
        "supported_operations": [],
        "restriction_scope": "password_authentication_only",
        "shadow_read": False,
        "credential_secret_read": False,
        "host_login_state_accessed": False,
        "pam_contents_read": False,
        "ssh_config_read": False,
        "autologin_policy_read": False,
        "session_policy_read": False,
        "source_read_only": True,
        "reason": "UNKNOWN — restricted-login capability has not been verified from the target rootfs.",
    }
    if identity.get("verified") is not True:
        base["reason"] = "UNKNOWN — target account evidence is not verified; restricted-login staging stays blocked."
        return base
    if str(identity.get("users_groups_status") or "UNKNOWN") not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = "UNKNOWN — target users/groups capability is not verified as safely stageable."
        return base
    passwd_layer = str(identity.get("passwd_layer") or "")
    group_layer = str(identity.get("group_layer") or "")
    if not (passwd_layer.startswith("/") and passwd_layer.casefold().endswith(".squashfs") and group_layer.startswith("/") and group_layer.casefold().endswith(".squashfs")):
        base["reason"] = "UNKNOWN — target account evidence is not bound to explicit SquashFS layers."
        return base

    regular_users = [str(x) for x in (identity.get("regular_users") or [])]
    admin_groups = {str(x) for x in (identity.get("admin_groups") or [])}
    admin_users: set[str] = set()
    for row in (identity.get("user_records") or []):
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "")
        groups = {str(x) for x in (row.get("groups") or [])}
        if username and groups.intersection(admin_groups):
            admin_users.add(username)

    base.update({
        "passwd_layer": passwd_layer,
        "group_layer": group_layer,
        "existing_regular_users": regular_users,
        "admin_users": sorted(admin_users),
    })
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; restricted-login support is not guessed from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
    except Exception:
        extents = {}
    if not extents:
        base["reason"] = "UNKNOWN — target SquashFS byte extents could not be verified; restricted-login staging stays blocked."
        return base

    candidates = (
        ("/usr/sbin/usermod", "shadow-utils-usermod"),
        ("/usr/bin/passwd", "passwd-lock"),
    )
    for tool_path, backend in candidates:
        try:
            present, layer = _inspect_overlay_member_presence(iso, layers, tool_path, extents)
        except Exception:
            present, layer = False, ""
        if present and layer:
            base.update({
                "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
                "verified": True,
                "backend": backend,
                "management_tool_path": tool_path,
                "management_tool_layer": layer,
                "supported_operations": ["lock_password_authentication"],
                "reason": (
                    "PASS — target account metadata and a target-rootfs password-lock management tool were verified read-only. "
                    "Alpha 56 may stage password-authentication locking for a non-admin kiosk account; /etc/shadow contents, PAM/SSH configuration, "
                    "autologin/session policy and Windows/WSL host login state were not read. Existing login mechanisms remain preservation-first."
                ),
            })
            return base

    base["reason"] = (
        "UNKNOWN — target account metadata is verified, but no target-rootfs usermod/passwd lock mechanism was verified. "
        "Mechanism capability therefore remains unverified rather than being inferred from absence."
    )
    return base


def _system_restricted_session_evidence(
    iso: Path,
    layers: list[str],
    autologin: dict[str, object],
    restricted_login: dict[str, object],
) -> dict[str, object]:
    """Alpha 57 target-only capability for a fixed kiosk autologin session.

    The first implemented backend is deliberately narrow: verified SDDM plus a
    verified target session descriptor and a collision-free managed SDDM drop-in.
    Session descriptor contents and existing SDDM drop-in contents are never read.
    The staged session selection requires the existing Alpha 39 autologin gate and
    Alpha 56 restricted-login gate for the same kiosk account; it does not claim to
    provide full desktop/service lockdown by itself.
    """
    base: dict[str, object] = {
        "gate_version": "alpha57",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "",
        "display_manager": str(autologin.get("display_manager") or ""),
        "display_manager_layer": str(autologin.get("display_manager_layer") or ""),
        "session_directories": [],
        "verified_sessions": [],
        "target_config_directory": "/etc/sddm.conf.d",
        "target_config_directory_layer": "",
        "managed_filename": "99-chromapress-kiosk-session.conf",
        "managed_target_path": "/etc/sddm.conf.d/99-chromapress-kiosk-session.conf",
        "managed_target_present": False,
        "existing_regular_users": [str(x) for x in (restricted_login.get("existing_regular_users") or [])],
        "admin_users": [str(x) for x in (restricted_login.get("admin_users") or [])],
        "supported_operations": [],
        "restriction_scope": "fixed_autologin_session_selection_only",
        "session_file_contents_read": False,
        "display_manager_config_contents_read": False,
        "credential_secret_read": False,
        "host_session_state_accessed": False,
        "pam_contents_read": False,
        "ssh_config_read": False,
        "source_read_only": True,
        "reason": "UNKNOWN — restricted-session capability has not been verified from the target rootfs.",
    }
    if autologin.get("verified") is not True:
        base["reason"] = "UNKNOWN — target display-manager/autologin evidence is not verified; restricted-session staging stays blocked."
        return base
    display_manager = str(autologin.get("display_manager") or "").casefold()
    dm_layer = str(autologin.get("display_manager_layer") or "")
    if display_manager != "sddm":
        base["reason"] = (
            f"UNKNOWN — verified default display manager is {display_manager or 'unknown'}, but Alpha 57 has not verified a safe user-scoped fixed-session mechanism for it."
        )
        return base
    if not dm_layer.startswith("/") or not dm_layer.casefold().endswith(".squashfs"):
        base["reason"] = "UNKNOWN — SDDM evidence is not bound to an explicit target SquashFS layer."
        return base
    if str(restricted_login.get("capability_status") or "UNKNOWN") not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = "UNKNOWN — Alpha 56 restricted-login capability is not verified for the target image; fixed kiosk-session staging stays blocked."
        return base
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; session support is not inferred from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
    except Exception:
        extents = {}
    if not extents:
        base["reason"] = "UNKNOWN — target SquashFS byte extents could not be verified; restricted-session staging stays blocked."
        return base

    sessions: list[dict[str, str]] = []
    session_dirs: list[dict[str, str]] = []
    for directory, kind in (("/usr/share/xsessions", "x11"), ("/usr/share/wayland-sessions", "wayland")):
        try:
            entries, layer = _list_overlay_directory_entries(iso, layers, directory, extents)
        except Exception:
            entries, layer = [], ""
        if not layer:
            continue
        session_dirs.append({"path": directory, "kind": kind, "layer": layer})
        for name in entries:
            safe = str(name)
            if re.fullmatch(r"[A-Za-z0-9._+-]{1,128}\.desktop", safe):
                sessions.append({"name": safe, "kind": kind, "layer": layer, "directory": directory})
    # Preserve stable order while removing duplicate basenames from layered/parallel dirs.
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in sessions:
        key = (row["name"], row["kind"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    base["session_directories"] = session_dirs
    base["verified_sessions"] = unique
    if not unique:
        base["reason"] = "UNKNOWN — SDDM is verified, but no target X11/Wayland session descriptor filename could be verified read-only."
        return base

    try:
        existing, config_layer = _list_overlay_directory_entries(iso, layers, "/etc/sddm.conf.d", extents)
    except Exception:
        existing, config_layer = [], ""
    if not config_layer:
        base["reason"] = "UNKNOWN — SDDM is verified, but /etc/sddm.conf.d could not be verified for collision-safe managed staging."
        return base
    base["target_config_directory_layer"] = config_layer
    managed = str(base["managed_filename"])
    if managed in {str(x) for x in existing}:
        base.update({
            "capability_status": "BLOCKED",
            "managed_target_present": True,
            "reason": (
                "BLOCKED — the managed Alpha 57 SDDM session drop-in filename already exists in the target image. "
                "Preservation-first policy forbids automatic overwrite or content inspection."
            ),
        })
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "backend": "sddm-autologin-session-dropin",
        "supported_operations": ["bind_kiosk_autologin_session"],
        "reason": (
            "PASS — SDDM, target session descriptor filenames and a collision-free /etc/sddm.conf.d target were verified read-only. "
            "Alpha 57 may stage only a fixed SDDM Autologin/Session selection for a kiosk account, with explicit Alpha 39 autologin and Alpha 56 restricted-login dependencies. "
            "Session descriptor contents, existing SDDM drop-in contents, credentials, PAM/SSH configuration and host session state were not read."
        ),
    })
    return base



def _system_service_lockdown_evidence(
    iso: Path,
    layers: list[str],
    services: dict[str, object],
) -> dict[str, object]:
    """Alpha 58 target-only capability for locking down one verified systemd service.

    Only immediate .service filenames are collected from verified target unit
    directories. Unit contents, enablement links/targets, environment files and
    credentials are never read. Critical/core units are excluded by ChromaPress'
    safety policy. The gate stages only an explicit disable+mask intent and leaves
    actual application to the verified systemd servicing path.
    """
    base: dict[str, object] = {
        "gate_version": "alpha58",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "",
        "init_system": str(services.get("init_system") or ""),
        "vendor_unit_path": str(services.get("vendor_unit_path") or ""),
        "vendor_unit_layer": str(services.get("vendor_unit_layer") or ""),
        "local_unit_path": str(services.get("local_unit_path") or ""),
        "local_unit_layer": str(services.get("local_unit_layer") or ""),
        "verified_service_units": [],
        "available_lockdown_units": [],
        "protected_service_units": [],
        "supported_operations": [],
        "lockdown_scope": "single_verified_noncritical_systemd_service",
        "unit_contents_read": False,
        "enablement_links_read": False,
        "enablement_link_targets_read": False,
        "environment_files_read": False,
        "service_secrets_read": False,
        "credential_secret_read": False,
        "host_service_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — service-lockdown capability has not been verified from the target rootfs.",
    }
    if services.get("verified") is not True or str(services.get("init_system") or "") != "systemd":
        base["reason"] = "UNKNOWN — verified target systemd service-directory evidence is unavailable; service-lockdown staging stays blocked."
        return base
    vendor = str(services.get("vendor_unit_path") or "")
    vendor_layer = str(services.get("vendor_unit_layer") or "")
    if vendor not in {"/usr/lib/systemd/system", "/lib/systemd/system"} or not vendor_layer.startswith("/") or not vendor_layer.casefold().endswith(".squashfs"):
        base["reason"] = "UNKNOWN — target systemd vendor-unit evidence is not bound to an explicit SquashFS layer."
        return base
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; service-lockdown support is not inferred from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
    except Exception:
        extents = {}
    if not extents:
        base["reason"] = "UNKNOWN — target SquashFS byte extents could not be verified; service-lockdown staging stays blocked."
        return base

    rows: list[dict[str, str]] = []
    for directory in (vendor, "/etc/systemd/system"):
        if directory == "/etc/systemd/system" and not str(services.get("local_unit_path") or ""):
            continue
        try:
            entries, layer = _list_overlay_directory_entries(iso, layers, directory, extents)
        except Exception:
            entries, layer = [], ""
        if not layer:
            continue
        for raw in entries:
            name = str(raw)
            if re.fullmatch(r"[A-Za-z0-9_.@:-]{1,120}\.service", name):
                rows.append({"name": name, "directory": directory, "layer": layer})

    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        name = row["name"]
        if name not in seen:
            seen.add(name)
            unique.append(row)
    base["verified_service_units"] = unique
    if not unique:
        base["reason"] = "UNKNOWN — systemd directories are verified, but no target .service unit filenames could be verified read-only."
        return base

    protected_exact = {
        "dbus.service", "polkit.service", "accounts-daemon.service",
        "display-manager.service", "sddm.service", "lightdm.service", "gdm.service",
        "NetworkManager.service", "systemd-networkd.service",
    }
    protected_prefixes = ("systemd-", "dbus.", "getty@", "serial-getty@", "user@")
    protected: list[str] = []
    available: list[dict[str, str]] = []
    for row in unique:
        name = row["name"]
        if name in protected_exact or name.startswith(protected_prefixes):
            protected.append(name)
        else:
            available.append(row)
    base["protected_service_units"] = sorted(protected)
    base["available_lockdown_units"] = available
    if not available:
        base.update({
            "capability_status": "BLOCKED",
            "reason": "BLOCKED — target systemd service units were verified, but all discovered units are protected by the Alpha 58 safety policy.",
        })
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "backend": "systemd-disable-mask-intent",
        "supported_operations": ["disable_and_mask_verified_service"],
        "reason": (
            "PASS — target systemd .service filenames were verified read-only and critical/core units were removed from the selectable lockdown set. "
            "Alpha 58 may stage disable+mask intent for one explicitly selected non-protected service. Unit contents, enablement-link targets, environment files, credentials and host service state were not read."
        ),
    })
    return base


def _system_network_restriction_evidence(
    iso: Path,
    layers: list[str],
    network: dict[str, object],
) -> dict[str, object]:
    """Alpha 59 target-only kiosk network-control restriction capability.

    This gate deliberately does *not* claim traffic isolation.  It verifies a
    NetworkManager + polkit target mechanism capable of preventing one kiosk
    account from changing system network state/settings through NetworkManager.
    Firewall traffic rules remain a separate Part 4 gate.

    Only path/directory-entry metadata is inspected.  NetworkManager profiles,
    polkit policy/rule contents, credentials and host/WSL networking are never read.
    """
    managed_name = "49-chromapress-kiosk-network.rules"
    base: dict[str, object] = {
        "gate_version": "alpha59",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "",
        "network_backend": str(network.get("backend") or ""),
        "polkit_rules_directory": "/etc/polkit-1/rules.d",
        "polkit_rules_directory_layer": "",
        "networkmanager_policy_path": "/usr/share/polkit-1/actions/org.freedesktop.NetworkManager.policy",
        "networkmanager_policy_layer": "",
        "managed_rule_name": managed_name,
        "managed_rule_path": f"/etc/polkit-1/rules.d/{managed_name}",
        "managed_target_present": False,
        "existing_rule_names": [],
        "supported_operations": [],
        "restricted_actions": [
            "org.freedesktop.NetworkManager.enable-disable-network",
            "org.freedesktop.NetworkManager.enable-disable-wifi",
            "org.freedesktop.NetworkManager.enable-disable-wwan",
            "org.freedesktop.NetworkManager.settings.modify.system",
        ],
        "restriction_scope": "kiosk_networkmanager_control_only",
        "traffic_blocking_claimed": False,
        "firewall_rules_read": False,
        "firewall_rules_staged": False,
        "networkmanager_profile_contents_read": False,
        "polkit_policy_contents_read": False,
        "existing_rule_contents_read": False,
        "credential_secret_read": False,
        "host_network_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — kiosk network-control restriction capability has not been verified from the target rootfs.",
    }
    if network.get("verified") is not True or str(network.get("capability_status") or "UNKNOWN") not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = "UNKNOWN — verified target networking capability is unavailable; network-restriction staging stays blocked."
        return base
    if str(network.get("backend") or "") != "NetworkManager":
        base["reason"] = (
            "UNKNOWN — the verified target network backend is not NetworkManager. "
            "ChromaPress does not infer an equivalent user-control restriction mechanism for another backend."
        )
        return base
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; network restrictions are not inferred from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
    except Exception:
        extents = {}
    if not extents:
        base["reason"] = "UNKNOWN — target SquashFS byte extents could not be verified; network-restriction staging stays blocked."
        return base

    rules_dir = "/etc/polkit-1/rules.d"
    policy_path = "/usr/share/polkit-1/actions/org.freedesktop.NetworkManager.policy"
    rules_present, rules_layer = _inspect_overlay_member_presence(iso, layers, rules_dir, extents)
    policy_present, policy_layer = _inspect_overlay_member_presence(iso, layers, policy_path, extents)
    if not rules_present or not rules_layer:
        base["reason"] = "UNKNOWN — target polkit rules.d support was not verified; absence is not treated as unsupported."
        return base
    if not policy_present or not policy_layer:
        base["reason"] = "UNKNOWN — target NetworkManager polkit action metadata was not verified; ChromaPress will not guess action semantics."
        return base

    try:
        entries, directory_layer = _list_overlay_directory_entries(iso, layers, rules_dir, extents)
    except Exception:
        entries, directory_layer = [], ""
    if not directory_layer:
        base["reason"] = "UNKNOWN — target polkit rules directory could not be listed safely for managed-file collision detection."
        return base
    rule_names = sorted({str(x) for x in entries if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", str(x))})[:200]
    managed_present = managed_name in rule_names
    base.update({
        "polkit_rules_directory_layer": directory_layer or rules_layer,
        "networkmanager_policy_layer": policy_layer,
        "existing_rule_names": rule_names,
        "managed_target_present": managed_present,
    })
    if managed_present:
        base.update({
            "capability_status": "BLOCKED",
            "reason": (
                "BLOCKED — the managed Alpha 59 polkit rule filename already exists in the target image. "
                "Preservation-first policy forbids automatic overwrite or content inspection."
            ),
        })
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "backend": "NetworkManager-polkit-managed-rule",
        "supported_operations": ["restrict_kiosk_networkmanager_control"],
        "reason": (
            "PASS — target NetworkManager and polkit rule/action metadata were verified read-only with a collision-free managed rules.d target. "
            "Alpha 59 may stage a kiosk-account NetworkManager control restriction only. It does not claim or stage traffic blocking; firewall rules remain separate. "
            "NetworkManager profiles, polkit contents, credentials and host networking were not read."
        ),
    })
    return base


def _system_firewall_rules_evidence(
    iso: Path,
    layers: list[str],
    firewall: dict[str, object],
) -> dict[str, object]:
    """Alpha 60 target-only capability for one managed inbound TCP deny rule.

    Existing firewall rules are deliberately not read during analysis. The gate
    verifies a target backend plus an additive command path. Duplicate/conflict
    checks and backend state are re-verified immediately before apply.
    """
    base: dict[str, object] = {
        "gate_version": "alpha60",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "firewall_backend": str(firewall.get("backend") or ""),
        "backend_evidence_path": str(firewall.get("backend_path") or ""),
        "backend_evidence_layer": str(firewall.get("backend_layer") or ""),
        "rule_adapter": "",
        "rule_command_path": "",
        "rule_command_layer": "",
        "supported_operations": [],
        "rule_scope": "single_inbound_tcp_port_deny",
        "existing_rule_contents_read": False,
        "ports_services_policy_read": False,
        "application_profiles_read": False,
        "firewall_secrets_read": False,
        "host_firewall_accessed": False,
        "requires_apply_time_conflict_check": True,
        "requires_backend_state_reverification": True,
        "preserve_existing_rules": True,
        "source_read_only": True,
        "reason": "UNKNOWN — traffic firewall-rule capability has not been verified from the target rootfs.",
    }
    if firewall.get("verified") is not True:
        base["reason"] = "UNKNOWN — verified target firewall backend evidence is unavailable; rule staging stays blocked."
        return base
    backend = str(firewall.get("backend") or "").casefold()
    layer = str(firewall.get("backend_layer") or "")
    if backend not in {"ufw", "firewalld", "nftables"} or not layer.startswith("/") or not layer.casefold().endswith(".squashfs"):
        base["reason"] = "UNKNOWN — target firewall backend is not bound to supported explicit SquashFS evidence."
        return base
    if backend == "nftables":
        base["reason"] = (
            "UNKNOWN — nftables is present, but Alpha 60 has not verified a preservation-safe persistent additive rule mechanism. "
            "ChromaPress does not rewrite nftables configuration or infer persistence semantics."
        )
        return base
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; firewall-rule support is not inferred from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
    except Exception:
        extents = {}
    if not extents:
        base["reason"] = "UNKNOWN — target SquashFS byte extents could not be verified; firewall-rule staging stays blocked."
        return base
    candidates = {
        "ufw": (("/usr/sbin/ufw", "ufw-additive-cli"), ("/sbin/ufw", "ufw-additive-cli")),
        "firewalld": (("/usr/bin/firewall-cmd", "firewalld-permanent-cli"), ("/bin/firewall-cmd", "firewalld-permanent-cli")),
    }
    command_path = command_layer = adapter = ""
    for member, candidate_adapter in candidates.get(backend, ()):
        present, found_layer = _inspect_overlay_member_presence(iso, layers, member, extents)
        if present and found_layer:
            command_path, command_layer, adapter = member, found_layer, candidate_adapter
            break
    if not command_path:
        base["reason"] = (
            f"UNKNOWN — {backend} backend evidence exists, but its target additive rule command path was not verified. "
            "Absence is not treated as unsupported."
        )
        return base
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "rule_adapter": adapter,
        "rule_command_path": command_path,
        "rule_command_layer": command_layer,
        "supported_operations": ["deny_inbound_tcp_port"],
        "reason": (
            f"PASS — target {backend} backend and additive rule command path were verified read-only. "
            "Alpha 60 may stage one explicit inbound TCP-port deny intent only. Existing rule contents are not read; "
            "duplicate/conflict and backend state must be re-verified before apply, and unrelated firewall policy is preserved."
        ),
    })
    return base

def _system_persistence_policy_evidence(
    layers: list[str],
    boot: dict[str, object],
    package_format: str,
    kiosk_user: dict[str, object],
) -> dict[str, object]:
    """Alpha 61 target-only policy capability for kiosk runtime persistence.

    This gate does not implement OverlayFS, mounts, volumes or initramfs hooks.
    It only stages an explicit Part 4 policy and delegates the underlying runtime
    mechanics to the already existing Part 3 immutable/controlled-persistence
    model. No existing persistence configuration or persistent data is read.
    """
    base: dict[str, object] = {
        "gate_version": "alpha61",
        "analysis_scope": "target_iso_metadata",
        "capability_status": "UNKNOWN",
        "verified": False,
        "supported_operations": [],
        "policy_scope": "kiosk_session_runtime_only",
        "rootfs_layers": [str(x) for x in layers if str(x).strip()],
        "boot_config_files": [str(x) for x in (boot.get("boot_config_files") or []) if str(x).strip()],
        "initramfs_mechanism": "",
        "part3_volatile_dependency": "immutable_runtime",
        "part3_controlled_dependency": "controlled_persistence",
        "existing_persistence_policy_read": False,
        "persistent_data_contents_read": False,
        "mount_configuration_contents_read": False,
        "host_storage_accessed": False,
        "host_mount_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — kiosk persistence-policy capability has not been verified from target metadata.",
    }
    mechanism = {
        "deb": "update-initramfs",
        "rpm": "dracut",
        "pkg.tar": "mkinitcpio",
    }.get(str(package_format or "").casefold(), "")
    base["initramfs_mechanism"] = mechanism

    kiosk_cap = str(kiosk_user.get("capability_status") or "UNKNOWN")
    if kiosk_user.get("gate_version") != "alpha55" or kiosk_cap not in {
        "SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"
    }:
        base["reason"] = "UNKNOWN — Alpha 55 kiosk-account capability evidence is unavailable or malformed."
        return base
    if kiosk_user.get("verified") is not True or kiosk_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 55 kiosk-account capability is {kiosk_cap}; persistence-policy user scope cannot be verified safely."
        return base
    if kiosk_user.get("shadow_read") is not False or kiosk_user.get("credential_secret_read") is not False:
        base.update({
            "capability_status": "BLOCKED",
            "reason": "BLOCKED — kiosk-account evidence is not privacy-safe enough for persistence-policy staging.",
        })
        return base

    rootfs = list(base["rootfs_layers"])
    boot_files = list(base["boot_config_files"])
    if not rootfs:
        base["reason"] = "UNKNOWN — no target SquashFS/rootfs layer was verified; persistence policy is not inferred from distribution name."
        return base
    if not all(x.startswith("/") and x.casefold().endswith(".squashfs") for x in rootfs):
        base["reason"] = "UNKNOWN — target rootfs evidence is not explicit SquashFS metadata."
        return base
    if not boot_files:
        base["reason"] = "UNKNOWN — no target boot configuration evidence is available for the required Part 3 dependency."
        return base
    if not mechanism:
        base["reason"] = "UNKNOWN — no supported native initramfs mechanism could be determined from target package-family metadata."
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": [
            "require_volatile_kiosk_runtime",
            "require_controlled_kiosk_persistence",
        ],
        "reason": (
            "PASS — target rootfs, boot-config and native initramfs metadata are sufficient to stage a kiosk persistence policy. "
            "Runtime mechanics remain delegated to Part 3 and must be re-verified before apply; existing persistence policy, mount contents, persistent data and host storage state were not read."
        ),
    })
    return base


def _system_admin_recovery_policy_evidence(
    identity: dict[str, object],
    autologin: dict[str, object],
    kiosk_user: dict[str, object],
) -> dict[str, object]:
    """Alpha 62 target-only administrator/recovery policy capability.

    The gate does not read credentials, /etc/shadow, PAM/SSH contents, rescue
    boot configuration or root-account policy. It verifies only non-secret
    account/group metadata plus explicit autologin metadata so a dedicated
    recovery administrator can be kept separate from kiosk/autologin roles.
    Authentication factors remain deferred to later FIDO2/WebAuthn/TPM gates.
    """
    base: dict[str, object] = {
        "gate_version": "alpha62",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "passwd-group-policy",
        "passwd_layer": "",
        "group_layer": "",
        "admin_groups": [],
        "existing_regular_users": [],
        "existing_admin_users": [],
        "autologin_user": "",
        "supported_operations": [],
        "policy_scope": "separate_non_autologin_recovery_administrator",
        "shadow_read": False,
        "credential_secret_read": False,
        "recovery_secret_read": False,
        "pam_contents_read": False,
        "ssh_config_read": False,
        "rescue_boot_config_read": False,
        "root_account_policy_read": False,
        "host_accounts_touched": False,
        "host_login_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — administrator/recovery policy capability has not been verified from target account metadata.",
    }
    allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
    identity_cap = str(identity.get("capability_status") or identity.get("users_groups_status") or "UNKNOWN")
    kiosk_cap = str(kiosk_user.get("capability_status") or "UNKNOWN")
    if identity.get("verified") is not True or identity_cap not in allowed:
        base["reason"] = "UNKNOWN — verified target users/groups evidence is unavailable; recovery policy staging stays blocked."
        return base
    if kiosk_user.get("gate_version") != "alpha55" or kiosk_cap not in allowed:
        base["reason"] = "UNKNOWN — Alpha 55 kiosk-account evidence is unavailable or malformed."
        return base
    if kiosk_user.get("shadow_read") is not False or kiosk_user.get("credential_secret_read") is not False:
        base.update({
            "capability_status": "BLOCKED",
            "reason": "BLOCKED — kiosk-account evidence is not privacy-safe enough for recovery-policy staging.",
        })
        return base
    if autologin.get("verified") is not True:
        base["reason"] = "UNKNOWN — target autologin metadata is not verified; ChromaPress cannot safely enforce a non-autologin recovery account."
        return base

    passwd_layer = str(identity.get("passwd_layer") or "")
    group_layer = str(identity.get("group_layer") or "")
    admin_groups = [str(x) for x in (identity.get("admin_groups") or []) if str(x) in {"sudo", "wheel"}]
    regular_users = [str(x) for x in (identity.get("regular_users") or []) if str(x).strip()]
    if not (passwd_layer.startswith("/") and passwd_layer.casefold().endswith(".squashfs") and group_layer.startswith("/") and group_layer.casefold().endswith(".squashfs")):
        base["reason"] = "UNKNOWN — target account databases are not bound to explicit SquashFS layers."
        return base
    if not admin_groups:
        base["reason"] = "UNKNOWN — no verified supported target administrator group (sudo/wheel) is available; administrator policy is not guessed."
        return base

    admin_set = set(admin_groups)
    admin_users: list[str] = []
    for row in (identity.get("user_records") or []):
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "")
        groups = {str(x) for x in (row.get("groups") or [])}
        if username and groups.intersection(admin_set):
            admin_users.append(username)

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "passwd_layer": passwd_layer,
        "group_layer": group_layer,
        "admin_groups": sorted(set(admin_groups)),
        "existing_regular_users": sorted(set(regular_users)),
        "existing_admin_users": sorted(set(admin_users)),
        "autologin_user": str(autologin.get("autologin_user") or ""),
        "supported_operations": ["require_dedicated_recovery_administrator"],
        "reason": (
            "PASS — target users/groups plus explicit autologin metadata support a separate recovery-administrator policy. "
            "The recovery account must be non-root, distinct from kiosk/autologin roles and verified as administrator or explicitly depend on the Alpha 50 administrator-account gate. "
            "Credentials, recovery secrets, PAM/SSH contents, rescue boot policy, root policy and host account state were not read; authentication factors remain separate later gates."
        ),
    })
    return base


def _profile_d_source_semantics(text: str) -> bool:
    """Return True only when target /etc/profile visibly sources /etc/profile.d/*.sh."""
    if not text:
        return False
    # Do not expose or retain profile contents: only verify the conventional drop-in loop.
    has_glob = "/etc/profile.d/*.sh" in text
    has_source = bool(re.search(r"(?m)^\s*(?:\.|source)\s+[\"']?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?[\"']?\s*(?:#.*)?$", text))
    return has_glob and has_source


def _system_config_overlay_rootfs_evidence(iso: Path, layers: list[str]) -> dict[str, object]:
    """Alpha 54 target-only evidence for a managed /etc/profile.d environment overlay.

    This deliberately does not read any existing drop-in contents.  It reads only
    /etc/profile to verify that the target actually sources /etc/profile.d/*.sh,
    then lists immediate profile.d entry names so a later managed filename can be
    collision-checked without overwriting custom configuration.
    """
    base: dict[str, object] = {
        "gate_version": "alpha54",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "profile.d",
        "profile_path": "/etc/profile",
        "profile_layer": "",
        "target_directory": "/etc/profile.d",
        "target_directory_layer": "",
        "profile_d_sourcing_verified": False,
        "existing_entry_names": [],
        "existing_dropin_contents_read": False,
        "supported_operations": [],
        "managed_filename_prefix": "99-chromapress-",
        "managed_filename_suffix": ".sh",
        "host_configuration_accessed": False,
        "secret_read": False,
        "source_read_only": True,
        "reason": "UNKNOWN — target system-configuration overlay mechanism has not been verified.",
    }
    if not layers:
        base["reason"] = "UNKNOWN — no target rootfs layer is available; overlay support is not guessed from distribution name."
        return base
    try:
        extents = _iso_member_extents(iso, layers)
        profile_text, profile_layer = _read_squashfs_overlay_text(iso, layers, "/etc/profile", extents)
        entries, directory_layer = _list_overlay_directory_entries(iso, layers, "/etc/profile.d", extents)
    except Exception:
        base["reason"] = "UNKNOWN — target /etc/profile and profile.d evidence could not be verified read-only."
        return base
    if not profile_text or not profile_layer:
        base["reason"] = "UNKNOWN — target /etc/profile could not be verified; profile.d semantics are not assumed."
        return base
    base["profile_layer"] = profile_layer
    if not _profile_d_source_semantics(profile_text):
        base["reason"] = "UNKNOWN — /etc/profile was found but safe profile.d sourcing semantics were not verified."
        return base
    if not directory_layer:
        base["profile_d_sourcing_verified"] = True
        base["reason"] = "UNKNOWN — /etc/profile sources profile.d, but the target /etc/profile.d directory could not be verified for collision-safe staging."
        return base
    safe_entries = sorted({str(name) for name in entries if re.fullmatch(r"[A-Za-z0-9._+-]{1,128}", str(name))})
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "profile_d_sourcing_verified": True,
        "target_directory_layer": directory_layer,
        "existing_entry_names": safe_entries,
        "supported_operations": ["add_managed_environment_overlay"],
        "reason": (
            "PASS — target /etc/profile profile.d sourcing and /etc/profile.d directory were verified read-only. "
            "Only existing entry names were listed; existing drop-in contents, secrets and host configuration were not read. "
            "A later apply must re-verify target-file absence before creating a managed non-secret drop-in."
        ),
    })
    return base


def _read_squashfs_overlay_text(
    iso: Path,
    layers: list[str],
    relative_path: str,
    extents: dict[str, tuple[int, int]] | None = None,
) -> tuple[str, str]:
    """Read one small text file from the effective layered rootfs, read-only.

    Later layers have precedence. Do not gate the real read on parsing
    ``unsquashfs --help`` output: squashfs-tools versions format option help
    differently. The actual direct-offset read is the authoritative capability
    probe. Both documented long/short offset spellings are tried read-only.
    No SquashFS layer is materialized by this function.
    """
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs or not layers:
        return "", ""
    extents = extents or _iso_member_extents(iso, layers)
    member = relative_path.lstrip("/")
    for layer in reversed(layers):
        extent = extents.get(layer)
        if not extent:
            continue
        offset = str(extent[0])
        # Help text is not stable across squashfs-tools releases. Try the
        # real read instead. A failed invocation changes nothing and simply
        # falls through to the next spelling/layer.
        commands = (
            [unsquashfs, "-cat", "-offset", offset, str(iso), member],
            [unsquashfs, "-offset", offset, "-cat", str(iso), member],
            [unsquashfs, "-cat", "-o", offset, str(iso), member],
            [unsquashfs, "-o", offset, "-cat", str(iso), member],
        )
        for args in commands:
            try:
                cp = subprocess.run(
                    args, text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if cp.returncode == 0 and cp.stdout:
                return cp.stdout, layer
    return "", ""


def _read_identity_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read non-secret identity metadata via a temporary read-only ISO mount.

    This is a fallback for squashfs-tools builds that cannot address an
    embedded SquashFS by byte offset. It is available only when the analysis
    engine is already running as root. The ISO and SquashFS layers stay
    read-only, and /etc/shadow is never requested.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = ("etc/passwd", "etc/group", "etc/login.defs")
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-iso-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            # Later live layers override earlier layers.
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    if read.returncode == 0 and read.stdout:
                        found[member] = (read.stdout, layer)
                if all(member in found for member in wanted):
                    break
        finally:
            try:
                subprocess.run(
                    [umount_bin, str(mountpoint)],
                    text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_identity_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify the account database without reading credential secrets."""
    base: dict[str, object] = {
        "gate_version": "alpha50",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "users_groups_status": "UNKNOWN",
        "uid_gid_status": "UNKNOWN",
        "group_membership_status": "UNKNOWN",
        "password_policy_status": "UNKNOWN",
        "verified": False,
        "passwd_present": False,
        "group_present": False,
        "login_defs_present": False,
        "passwd_layer": "",
        "group_layer": "",
        "login_defs_layer": "",
        "uid_min": 1000,
        "account_count": 0,
        "regular_users": [],
        "user_records": [],
        "group_records": [],
        "groups": [],
        "admin_groups": [],
        "default_user_candidate": "",
        "password_policy": {},
        "shadow_read": False,
        "credential_secret_read": False,
        "host_accounts_touched": False,
        "source_read_only": True,
        "reason": "UNKNOWN — target-rootfs account capability has not been verified.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; account staging stays blocked."
        return base

    # The real read below is the capability test. Do not reject a supported
    # unsquashfs merely because its help text formats -offset differently.
    extents = _iso_member_extents(path, layers)
    if not extents:
        base["reason"] = "Could not verify SquashFS byte extents from the selected ISO; account staging stays blocked."
        return base
    passwd_text, passwd_layer = _read_squashfs_overlay_text(path, layers, "/etc/passwd", extents)
    group_text, group_layer = _read_squashfs_overlay_text(path, layers, "/etc/group", extents)
    login_defs_text, login_defs_layer = _read_squashfs_overlay_text(path, layers, "/etc/login.defs", extents)

    # Direct embedded-offset reads are fastest, but some squashfs-tools builds
    # reject them. Fall back to a temporary loop,ro mount rather than copying
    # multi-gigabyte SquashFS layers or weakening the verification gate.
    if not passwd_text or not group_text or not login_defs_text:
        mounted = _read_identity_from_readonly_mount(path, layers)
        if not passwd_text and "etc/passwd" in mounted:
            passwd_text, passwd_layer = mounted["etc/passwd"]
        if not group_text and "etc/group" in mounted:
            group_text, group_layer = mounted["etc/group"]
        if not login_defs_text and "etc/login.defs" in mounted:
            login_defs_text, login_defs_layer = mounted["etc/login.defs"]

    base.update({
        "passwd_present": bool(passwd_text),
        "group_present": bool(group_text),
        "login_defs_present": bool(login_defs_text),
        "passwd_layer": passwd_layer,
        "group_layer": group_layer,
        "login_defs_layer": login_defs_layer,
    })
    if not passwd_text or not group_text:
        missing = []
        if not passwd_text:
            missing.append("/etc/passwd")
        if not group_text:
            missing.append("/etc/group")
        base["reason"] = "Missing read-only rootfs evidence: " + ", ".join(missing)
        return base

    parsed = _parse_identity_rootfs(passwd_text, group_text, login_defs_text)
    base.update(parsed)
    base["verified"] = True
    base["capability_status"] = "SUPPORTED_WITH_REQUIREMENTS"
    base["users_groups_status"] = "SUPPORTED_WITH_REQUIREMENTS"
    base["uid_gid_status"] = "SUPPORTED_WITH_REQUIREMENTS"
    base["group_membership_status"] = "SUPPORTED_WITH_REQUIREMENTS"
    base["password_policy_status"] = "SUPPORTED_WITH_REQUIREMENTS" if login_defs_text else "UNKNOWN"
    base["reason"] = (
        "PASS — target ISO /etc/passwd and /etc/group verified read-only; user/group records and non-secret password-policy defaults were analyzed. "
        "/etc/shadow and Windows/WSL host account databases were not read."
    )
    return base


def _read_machine_identity_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read hostname/machine-id metadata via a temporary read-only ISO mount.

    This mirrors the Alpha 37 identity fallback but is intentionally scoped to
    non-secret machine identity metadata. The ISO and SquashFS layers remain
    read-only and are unmounted immediately after inspection.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = ("etc/hostname", "etc/machine-id")
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-machine-id-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    # Empty /etc/machine-id is a valid image state, so retain a
                    # successful zero-length read as explicit evidence.
                    if read.returncode == 0:
                        found[member] = (read.stdout, layer)
                if all(member in found for member in wanted):
                    break
        finally:
            try:
                subprocess.run(
                    [umount_bin, str(mountpoint)],
                    text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_machine_identity_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify hostname and machine-id state without exposing/staging an ID value."""
    base: dict[str, object] = {
        "verified": False,
        "hostname_present": False,
        "hostname": "",
        "hostname_layer": "",
        "machine_id_state": "unknown",
        "machine_id_layer": "",
        "machine_id_value_exposed": False,
        "reason": "Rootfs hostname/machine identity evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; hostname staging stays blocked."
        return base

    extents = _iso_member_extents(path, layers)
    if not extents:
        base["reason"] = "Could not verify SquashFS byte extents from the selected ISO; hostname staging stays blocked."
        return base

    hostname_text, hostname_layer = _read_squashfs_overlay_text(path, layers, "/etc/hostname", extents)
    machine_text, machine_layer = _read_squashfs_overlay_text(path, layers, "/etc/machine-id", extents)
    machine_seen = bool(machine_layer)

    if not hostname_text or not machine_seen:
        mounted = _read_machine_identity_from_readonly_mount(path, layers)
        if not hostname_text and "etc/hostname" in mounted:
            hostname_text, hostname_layer = mounted["etc/hostname"]
        if not machine_seen and "etc/machine-id" in mounted:
            machine_text, machine_layer = mounted["etc/machine-id"]
            machine_seen = True

    hostname = hostname_text.strip().splitlines()[0].strip() if hostname_text.strip() else ""
    if not hostname or any(ch in hostname for ch in ("\r", "\n", "\x00")):
        base["reason"] = "Missing or invalid read-only /etc/hostname evidence; hostname staging stays blocked."
        return base

    machine_raw = machine_text.strip()
    if machine_seen:
        if not machine_raw:
            machine_state = "empty"
        elif re.fullmatch(r"[0-9a-fA-F]{32}", machine_raw):
            machine_state = "present"
        else:
            machine_state = "nonstandard"
    else:
        machine_state = "absent"

    base.update({
        "verified": True,
        "hostname_present": True,
        "hostname": hostname,
        "hostname_layer": hostname_layer,
        "machine_id_state": machine_state,
        "machine_id_layer": machine_layer,
        "reason": "PASS — /etc/hostname verified read-only; machine-id state inspected without exposing or staging the machine-id value.",
    })
    return base



def _read_autologin_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read display-manager/autologin metadata from a temporary read-only mount.

    No credential database or password material is requested. The ISO and every
    SquashFS layer remain read-only and are unmounted immediately after inspection.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = (
        "etc/X11/default-display-manager",
        "etc/sddm.conf",
        "etc/sddm.conf.d/autologin.conf",
        "etc/sddm.conf.d/kde_settings.conf",
        "etc/lightdm/lightdm.conf",
        "etc/gdm3/custom.conf",
    )
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-autologin-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    if read.returncode == 0:
                        found[member] = (read.stdout, layer)
        finally:
            try:
                subprocess.run(
                    [umount_bin, str(mountpoint)],
                    text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _parse_autologin_state(display_manager: str, configs: list[tuple[str, str]]) -> tuple[str, str]:
    """Return (state, user) from explicit non-secret display-manager config only."""
    dm = display_manager.casefold()
    state = "no explicit autologin directive found"
    user = ""
    for _path, text in configs:
        if dm == "sddm":
            in_autologin = False
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith(("#", ";")):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_autologin = line[1:-1].strip().casefold() == "autologin"
                    continue
                if in_autologin and "=" in line:
                    key, value = (part.strip() for part in line.split("=", 1))
                    if key.casefold() == "user" and value:
                        user = value
                        state = "enabled explicitly"
        elif dm == "lightdm":
            for raw in text.splitlines():
                line = raw.split("#", 1)[0].strip()
                if "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                if key.casefold() == "autologin-user" and value:
                    user = value
                    state = "enabled explicitly"
        elif dm in {"gdm", "gdm3"}:
            enabled = False
            candidate = ""
            for raw in text.splitlines():
                line = raw.split("#", 1)[0].strip()
                if "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                low = key.casefold()
                if low == "automaticloginenable":
                    enabled = value.casefold() in {"true", "1", "yes"}
                elif low == "automaticlogin" and value:
                    candidate = value
            if enabled and candidate:
                user = candidate
                state = "enabled explicitly"
    return state, user


def _system_autologin_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify display-manager evidence required for staging an autologin policy."""
    base: dict[str, object] = {
        "verified": False,
        "display_manager": "",
        "display_manager_layer": "",
        "autologin_state": "unknown",
        "autologin_user": "",
        "config_evidence": [],
        "credential_secret_read": False,
        "reason": "Rootfs display-manager/autologin evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; autologin staging stays blocked."
        return base

    extents = _iso_member_extents(path, layers)
    default_text = ""
    default_layer = ""
    config_reads: dict[str, tuple[str, str]] = {}
    wanted_configs = (
        "/etc/sddm.conf",
        "/etc/sddm.conf.d/autologin.conf",
        "/etc/sddm.conf.d/kde_settings.conf",
        "/etc/lightdm/lightdm.conf",
        "/etc/gdm3/custom.conf",
    )
    if extents:
        default_text, default_layer = _read_squashfs_overlay_text(
            path, layers, "/etc/X11/default-display-manager", extents,
        )
        for member in wanted_configs:
            text, layer = _read_squashfs_overlay_text(path, layers, member, extents)
            if layer:
                config_reads[member.lstrip("/")] = (text, layer)

    if not default_text:
        mounted = _read_autologin_from_readonly_mount(path, layers)
        if "etc/X11/default-display-manager" in mounted:
            default_text, default_layer = mounted["etc/X11/default-display-manager"]
        for member, value in mounted.items():
            if member != "etc/X11/default-display-manager" and member not in config_reads:
                config_reads[member] = value

    raw_dm = default_text.strip().splitlines()[0].strip() if default_text.strip() else ""
    display_manager = Path(raw_dm).name.casefold() if raw_dm else ""
    aliases = {"gdm": "gdm", "gdm3": "gdm3", "sddm": "sddm", "lightdm": "lightdm"}
    display_manager = aliases.get(display_manager, "")
    if not display_manager or not default_layer:
        base["reason"] = "No supported default display manager was verified read-only inside the selected rootfs."
        return base

    configs: list[tuple[str, str]] = []
    config_evidence: list[dict[str, str]] = []
    for member, (text, layer) in sorted(config_reads.items()):
        configs.append((member, text))
        config_evidence.append({"path": "/" + member, "layer": layer})
    state, user = _parse_autologin_state(display_manager, configs)

    base.update({
        "verified": True,
        "display_manager": display_manager,
        "display_manager_layer": default_layer,
        "autologin_state": state,
        "autologin_user": user,
        "config_evidence": config_evidence,
        "reason": "PASS — default display manager verified read-only; explicit autologin directives inspected without reading credential secrets.",
    })
    return base



def _read_locale_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read non-secret locale configuration via a temporary read-only mount."""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = ("etc/default/locale", "etc/locale.conf", "etc/locale.gen")
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-locale-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    if read.returncode == 0:
                        found[member] = (read.stdout, layer)
        finally:
            try:
                subprocess.run(
                    [umount_bin, str(mountpoint)],
                    text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _parse_locale_assignments(text: str) -> dict[str, str]:
    """Parse only LANG/LANGUAGE/LC_ALL assignments from locale config text."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.upper()
        if key not in {"LANG", "LANGUAGE", "LC_ALL"}:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value and not any(ch in value for ch in ("\r", "\n", "\x00")):
            values[key] = value
    return values


def _system_locale_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify non-secret locale configuration evidence for a staged LANG policy."""
    base: dict[str, object] = {
        "verified": False,
        "config_path": "",
        "config_layer": "",
        "config_style": "",
        "current_lang": "",
        "current_language": "",
        "current_lc_all": "",
        "locale_gen_present": False,
        "secret_read": False,
        "reason": "Rootfs locale evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; locale staging stays blocked."
        return base

    wanted = ("/etc/default/locale", "/etc/locale.conf", "/etc/locale.gen")
    reads: dict[str, tuple[str, str]] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in wanted:
            text, layer = _read_squashfs_overlay_text(path, layers, member, extents)
            if layer:
                reads[member.lstrip("/")] = (text, layer)

    if not reads:
        reads.update(_read_locale_from_readonly_mount(path, layers))
    else:
        mounted = _read_locale_from_readonly_mount(path, layers)
        for member, value in mounted.items():
            reads.setdefault(member, value)

    config_member = ""
    config_style = ""
    for candidate, style in (
        ("etc/default/locale", "debian-default-locale"),
        ("etc/locale.conf", "locale.conf"),
        ("etc/locale.gen", "locale.gen-only"),
    ):
        if candidate in reads:
            config_member = candidate
            config_style = style
            break
    if not config_member:
        base["reason"] = "No supported locale configuration evidence was verified read-only inside the selected rootfs."
        return base

    config_text, config_layer = reads[config_member]
    assignments: dict[str, str] = {}
    for candidate in ("etc/default/locale", "etc/locale.conf"):
        if candidate in reads:
            assignments.update(_parse_locale_assignments(reads[candidate][0]))

    base.update({
        "verified": True,
        "config_path": "/" + config_member,
        "config_layer": config_layer,
        "config_style": config_style,
        "current_lang": assignments.get("LANG", ""),
        "current_language": assignments.get("LANGUAGE", ""),
        "current_lc_all": assignments.get("LC_ALL", ""),
        "locale_gen_present": "etc/locale.gen" in reads,
        "reason": "PASS — locale configuration evidence verified read-only; only non-secret LANG/LANGUAGE/LC_ALL metadata was inspected.",
    })
    return base


def _read_keyboard_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read non-secret keyboard configuration via a temporary read-only mount."""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = ("etc/default/keyboard", "etc/vconsole.conf")
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-keyboard-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    if read.returncode == 0:
                        found[member] = (read.stdout, layer)
        finally:
            try:
                subprocess.run(
                    [umount_bin, str(mountpoint)],
                    text=True, capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _parse_keyboard_assignments(text: str) -> dict[str, str]:
    """Parse only supported non-secret keyboard assignments."""
    allowed = {"XKBMODEL", "XKBLAYOUT", "XKBVARIANT", "XKBOPTIONS", "KEYMAP"}
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.upper()
        if key not in allowed:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not any(ch in value for ch in ("\r", "\n", "\x00")):
            values[key] = value
    return values


def _system_keyboard_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify keyboard configuration evidence for a staging-only layout policy."""
    base: dict[str, object] = {
        "verified": False,
        "config_path": "",
        "config_layer": "",
        "config_style": "",
        "current_layout": "",
        "current_model": "",
        "current_variant": "",
        "current_options": "",
        "secret_read": False,
        "reason": "Rootfs keyboard configuration evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; keyboard staging stays blocked."
        return base

    wanted = ("/etc/default/keyboard", "/etc/vconsole.conf")
    reads: dict[str, tuple[str, str]] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in wanted:
            text, layer = _read_squashfs_overlay_text(path, layers, member, extents)
            if layer:
                reads[member.lstrip("/")] = (text, layer)

    if not reads:
        reads.update(_read_keyboard_from_readonly_mount(path, layers))
    else:
        mounted = _read_keyboard_from_readonly_mount(path, layers)
        for member, value in mounted.items():
            reads.setdefault(member, value)

    config_member = ""
    config_style = ""
    for candidate, style in (
        ("etc/default/keyboard", "debian-default-keyboard"),
        ("etc/vconsole.conf", "vconsole.conf"),
    ):
        if candidate in reads:
            config_member = candidate
            config_style = style
            break
    if not config_member:
        base["reason"] = "No supported keyboard configuration evidence was verified read-only inside the selected rootfs."
        return base

    config_text, config_layer = reads[config_member]
    assignments = _parse_keyboard_assignments(config_text)
    layout = assignments.get("XKBLAYOUT", "") or assignments.get("KEYMAP", "")
    base.update({
        "verified": True,
        "config_path": "/" + config_member,
        "config_layer": config_layer,
        "config_style": config_style,
        "current_layout": layout,
        "current_model": assignments.get("XKBMODEL", ""),
        "current_variant": assignments.get("XKBVARIANT", ""),
        "current_options": assignments.get("XKBOPTIONS", ""),
        "reason": "PASS — keyboard configuration evidence verified read-only; only non-secret layout/model/variant/options metadata was inspected.",
    })
    return base

def _safe_timezone_name(value: str) -> str:
    """Return a normalized safe timezone identifier or an empty string."""
    value = value.strip().strip('"\'')
    if not value or len(value) > 128 or value.startswith("/") or "\x00" in value:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9._+\-/]+", value):
        return ""
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return ""
    return value


def _parse_timezone_text(text: str) -> str:
    """Parse one non-secret timezone name from a text configuration file."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value = _safe_timezone_name(line.split("#", 1)[0].strip())
        if value:
            return value
    return ""


def _localtime_listing_info(text: str) -> tuple[bool, str]:
    """Inspect unsquashfs listing text without reading binary /etc/localtime."""
    present = "etc/localtime" in text
    match = re.search(r"etc/localtime\s+->\s+(\S+)", text)
    if not match:
        return present, ""
    target = match.group(1).strip()
    prefix = "/usr/share/zoneinfo/"
    if target.startswith(prefix):
        target = target[len(prefix):]
    return True, _safe_timezone_name(target)


def _inspect_localtime_overlay(iso: Path, layers: list[str], extents: dict[str, tuple[int, int]]) -> tuple[bool, str, str]:
    """Inspect /etc/localtime metadata from embedded SquashFS layers read-only."""
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs:
        return False, "", ""
    member = "etc/localtime"
    for layer in reversed(layers):
        extent = extents.get(layer)
        if not extent:
            continue
        offset = str(extent[0])
        commands = (
            [unsquashfs, "-ll", "-offset", offset, str(iso), member],
            [unsquashfs, "-offset", offset, "-ll", str(iso), member],
            [unsquashfs, "-ll", "-o", offset, str(iso), member],
            [unsquashfs, "-o", offset, "-ll", str(iso), member],
        )
        for args in commands:
            try:
                cp = subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = (cp.stdout or "") + "\n" + (cp.stderr or "")
            present, zone = _localtime_listing_info(text)
            if cp.returncode == 0 and present:
                return True, zone, layer
    return False, "", ""


def _read_timezone_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, tuple[str, str]]:
    """Read timezone text / inspect localtime metadata through a temporary read-only ISO mount."""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}

    wanted = ("etc/timezone", "etc/default/timezone")
    found: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-timezone-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        read = subprocess.run(
                            [unsquashfs, "-cat", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    if read.returncode == 0 and read.stdout:
                        found[member] = (read.stdout, layer)
                if "etc/localtime" not in found:
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), "etc/localtime"],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        listing = None
                    if listing is not None and listing.returncode == 0:
                        text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                        present, zone = _localtime_listing_info(text)
                        if present:
                            found["etc/localtime"] = (zone, layer)
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_timezone_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify timezone configuration evidence without reading secrets or binary timezone data."""
    base: dict[str, object] = {
        "verified": False,
        "config_path": "",
        "config_layer": "",
        "config_style": "",
        "current_timezone": "",
        "localtime_present": False,
        "secret_read": False,
        "reason": "Rootfs timezone configuration evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; timezone staging stays blocked."
        return base

    reads: dict[str, tuple[str, str]] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in ("/etc/timezone", "/etc/default/timezone"):
            text, layer = _read_squashfs_overlay_text(path, layers, member, extents)
            if layer:
                reads[member.lstrip("/")] = (text, layer)
        present, zone, layer = _inspect_localtime_overlay(path, layers, extents)
        if present:
            reads.setdefault("etc/localtime", (zone, layer))

    mounted = _read_timezone_from_readonly_mount(path, layers)
    for member, value in mounted.items():
        reads.setdefault(member, value)

    for candidate, style in (("etc/timezone", "debian-timezone"), ("etc/default/timezone", "default-timezone")):
        if candidate in reads:
            text, layer = reads[candidate]
            zone = _parse_timezone_text(text)
            if zone:
                base.update({
                    "verified": True,
                    "config_path": "/" + candidate,
                    "config_layer": layer,
                    "config_style": style,
                    "current_timezone": zone,
                    "localtime_present": "etc/localtime" in reads,
                    "reason": "PASS — timezone configuration evidence verified read-only; only the non-secret timezone identifier was inspected.",
                })
                return base

    if "etc/localtime" in reads:
        zone, layer = reads["etc/localtime"]
        base.update({
            "verified": True,
            "config_path": "/etc/localtime",
            "config_layer": layer,
            "config_style": "localtime-symlink" if zone else "localtime-entry",
            "current_timezone": _safe_timezone_name(zone),
            "localtime_present": True,
            "reason": "PASS — /etc/localtime timezone evidence verified read-only; binary timezone contents were not read.",
        })
        return base

    base["reason"] = "No supported timezone configuration evidence was verified read-only inside the selected rootfs."
    return base


def _installer_evidence(files: list[str], versions: dict[str, str]) -> dict[str, object]:
    """Detect installer family only from explicit ISO paths or package manifests."""
    low_files = [str(item).casefold() for item in files]
    package_hits: list[dict[str, str]] = []
    family = "unknown"

    def add_packages(prefixes: tuple[str, ...], label: str) -> bool:
        found = False
        for package, version in sorted(versions.items()):
            low = package.casefold()
            if any(low == prefix or low.startswith(prefix + "-") for prefix in prefixes):
                package_hits.append({"kind": "package", "value": package, "version": version, "family": label})
                found = True
        return found

    # Prefer package-manifest evidence because desktop installer payloads often live
    # inside SquashFS rather than as plainly named files at ISO level.
    if add_packages(("calamares",), "Calamares"):
        family = "Calamares"
    elif add_packages(("subiquity",), "Subiquity/Autoinstall"):
        family = "Subiquity/Autoinstall"
    elif add_packages(("anaconda",), "Anaconda/Kickstart"):
        family = "Anaconda/Kickstart"
    elif add_packages(("debian-installer",), "Debian Installer/Preseed"):
        family = "Debian Installer/Preseed"
    elif add_packages(("ubiquity",), "Ubiquity"):
        family = "Ubiquity"

    config_tokens = (
        "calamares", "autoinstall", "user-data", "meta-data", "nocloud",
        "kickstart", "ks.cfg", "preseed",
    )
    config_files: list[str] = []
    for original, low in zip(files, low_files):
        basename = low.rsplit("/", 1)[-1]
        if any(token in low for token in config_tokens) or basename in {"ks.cfg", "preseed.cfg"}:
            config_files.append(str(original))
    config_files = list(dict.fromkeys(config_files))[:100]

    # Fall back to explicit file/path evidence only when package evidence did not
    # identify the family. Never infer a family from the distro name alone.
    if family == "unknown":
        joined = "\n".join(low_files)
        if "calamares" in joined:
            family = "Calamares"
        elif "subiquity" in joined or "autoinstall" in joined:
            family = "Subiquity/Autoinstall"
        elif "anaconda" in joined or "kickstart" in joined or "/ks.cfg" in joined:
            family = "Anaconda/Kickstart"
        elif "preseed" in joined:
            family = "Debian Installer/Preseed"
        elif "ubiquity" in joined:
            family = "Ubiquity"

    modes: list[str] = ["Interactive installer"] if family != "unknown" else []
    if family == "Subiquity/Autoinstall":
        modes.append("Autoinstall family detected")
    elif family == "Anaconda/Kickstart":
        modes.append("Kickstart family detected")
    elif family == "Debian Installer/Preseed":
        modes.append("Preseed family detected")
    elif family == "Calamares":
        modes.append("Calamares configuration requires rootfs-level verification before editing")

    return {
        "installer": family,
        "installer_evidence": package_hits,
        "installer_config_files": config_files,
        "installer_modes": modes,
    }


def _inspect_overlay_member_presence(
    iso: Path,
    layers: list[str],
    relative_path: str,
    extents: dict[str, tuple[int, int]] | None = None,
) -> tuple[bool, str]:
    """Verify one rootfs path exists without reading its file contents."""
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs or not layers:
        return False, ""
    extents = extents or _iso_member_extents(iso, layers)
    member = relative_path.lstrip("/")
    for layer in reversed(layers):
        extent = extents.get(layer)
        if not extent:
            continue
        offset = str(extent[0])
        commands = (
            [unsquashfs, "-ll", "-offset", offset, str(iso), member],
            [unsquashfs, "-offset", offset, "-ll", str(iso), member],
            [unsquashfs, "-ll", "-o", offset, str(iso), member],
            [unsquashfs, "-o", offset, "-ll", str(iso), member],
        )
        for args in commands:
            try:
                cp = subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = (cp.stdout or "") + "\n" + (cp.stderr or "")
            if cp.returncode == 0 and member in text:
                return True, layer
    return False, ""


def _parse_unsquashfs_metadata_entries(text: str, directory: str) -> list[str]:
    """Return child entry names from ``unsquashfs -ll`` output without reading contents."""
    prefix = directory.strip("/") + "/"
    entries: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        marker = "squashfs-root/"
        if marker in line:
            path = line.split(marker, 1)[1].strip()
        else:
            idx = line.find(prefix)
            if idx < 0:
                continue
            path = line[idx:].strip()
        if not path.startswith(prefix):
            continue
        child = path[len(prefix):]
        if not child or "/" in child:
            continue
        if child not in entries:
            entries.append(child)
    return entries


def _list_overlay_directory_entries(
    iso: Path,
    layers: list[str],
    directory: str,
    extents: dict[str, tuple[int, int]] | None = None,
) -> tuple[list[str], str]:
    """List only immediate entry names in a rootfs directory; never read file contents."""
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs or not layers:
        return [], ""
    extents = extents or _iso_member_extents(iso, layers)
    member = directory.strip("/")
    for layer in reversed(layers):
        extent = extents.get(layer)
        if not extent:
            continue
        offset = str(extent[0])
        commands = (
            [unsquashfs, "-ll", "-offset", offset, str(iso), member],
            [unsquashfs, "-offset", offset, "-ll", str(iso), member],
            [unsquashfs, "-ll", "-o", offset, str(iso), member],
            [unsquashfs, "-o", offset, "-ll", str(iso), member],
        )
        for args in commands:
            try:
                cp = subprocess.run(args, text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if cp.returncode != 0:
                continue
            entries = _parse_unsquashfs_metadata_entries((cp.stdout or "") + "\n" + (cp.stderr or ""), member)
            # An empty directory is still useful evidence, so independently verify it.
            directory_seen = member in ((cp.stdout or "") + "\n" + (cp.stderr or ""))
            if directory_seen:
                return entries, layer
    return [], ""


def _inspect_network_dns_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, object]:
    """Inspect safe network path metadata through a temporary read-only ISO mount.

    Alpha 51 deliberately reads no NetworkManager keyfile contents, no netplan YAML,
    no interface configuration contents and no Wi-Fi/VPN credentials.  The only
    profile information collected is the immediate filename of an existing
    ``.nmconnection`` file, which is sufficient to bind a later staged autoconnect
    intent to an exact target file without exposing its contents.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}
    wanted = (
        "etc/NetworkManager/NetworkManager.conf",
        "usr/sbin/NetworkManager",
        "usr/bin/nmcli",
        "etc/NetworkManager/system-connections",
        "etc/netplan",
        "etc/network/interfaces",
        "etc/network/interfaces.d",
        "etc/systemd/network",
        "usr/lib/systemd/system/systemd-networkd.service",
        "lib/systemd/system/systemd-networkd.service",
        "etc/systemd/resolved.conf",
        "etc/resolv.conf",
    )
    found: dict[str, object] = {}
    profile_names: list[str] = []
    with tempfile.TemporaryDirectory(prefix="chromapress-network-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                    if listing.returncode == 0 and member in text:
                        found[member] = layer
                        if member == "etc/NetworkManager/system-connections":
                            for entry in _parse_unsquashfs_metadata_entries(text, member):
                                if entry.endswith(".nmconnection") and entry not in profile_names:
                                    profile_names.append(entry)
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    found["networkmanager_profile_names"] = sorted(profile_names)[:100]
    return found


def _system_network_dns_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Alpha 51 capability evidence for safe staged target-ISO networking configuration."""
    base: dict[str, object] = {
        "gate_version": "alpha51",
        "analysis_scope": "target_iso_rootfs",
        "verified": False,
        "capability_status": "UNKNOWN",
        "addressing_status": "UNKNOWN",
        "dns_status": "UNKNOWN",
        "networkmanager_profile_status": "UNKNOWN",
        "ipv6_status": "BLOCKED",
        "ipv6_exposed": False,
        "backend": "",
        "backend_config_path": "",
        "backend_config_layer": "",
        "managed_config_path": "",
        "managed_config_style": "",
        "resolver_path": "",
        "resolver_layer": "",
        "supported_operations": [],
        "networkmanager_profile_directory": "",
        "networkmanager_profile_directory_layer": "",
        "networkmanager_profile_names": [],
        "connection_profiles_inspected": False,
        "connection_profile_contents_read": False,
        "profile_names_from_metadata_only": True,
        "wifi_vpn_secrets_read": False,
        "credential_secret_read": False,
        "host_network_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — target-rootfs networking capability has not been verified.",
    }
    if not layers:
        base["reason"] = "UNKNOWN — no SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "BLOCKED — unsquashfs is unavailable in the selected WSL distribution; networking configuration stays fail-closed."
        base["capability_status"] = "BLOCKED"
        base["addressing_status"] = "BLOCKED"
        base["dns_status"] = "BLOCKED"
        base["networkmanager_profile_status"] = "BLOCKED"
        return base

    members = (
        "/etc/NetworkManager/NetworkManager.conf",
        "/usr/sbin/NetworkManager",
        "/usr/bin/nmcli",
        "/etc/network/interfaces",
        "/etc/network/interfaces.d",
        "/etc/systemd/network",
        "/usr/lib/systemd/system/systemd-networkd.service",
        "/lib/systemd/system/systemd-networkd.service",
        "/etc/systemd/resolved.conf",
        "/etc/resolv.conf",
    )
    present: dict[str, str] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in members:
            ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
            if ok:
                present[member.lstrip("/")] = layer

    profile_names: list[str] = []
    profile_dir_layer = ""
    if extents:
        profile_names, profile_dir_layer = _list_overlay_directory_entries(
            path, layers, "/etc/NetworkManager/system-connections", extents,
        )
        profile_names = sorted({x for x in profile_names if x.endswith(".nmconnection")})[:100]
        if profile_dir_layer:
            present.setdefault("etc/NetworkManager/system-connections", profile_dir_layer)
        _netplan_entries, netplan_layer = _list_overlay_directory_entries(
            path, layers, "/etc/netplan", extents,
        )
        if netplan_layer:
            present.setdefault("etc/netplan", netplan_layer)

    mounted = _inspect_network_dns_from_readonly_mount(path, layers)
    for member, layer in mounted.items():
        if member == "networkmanager_profile_names":
            for name in list(layer or []):
                if isinstance(name, str) and name.endswith(".nmconnection") and name not in profile_names:
                    profile_names.append(name)
            continue
        if isinstance(layer, str):
            present.setdefault(member, layer)
    profile_names = sorted(profile_names)[:100]

    backend = ""
    backend_path = ""
    managed_path = ""
    managed_style = ""
    # Prefer explicit NetworkManager evidence over generator/fallback mechanisms.
    if any(key in present for key in (
        "etc/NetworkManager/NetworkManager.conf", "usr/sbin/NetworkManager", "usr/bin/nmcli",
    )):
        backend = "NetworkManager"
        for candidate in ("etc/NetworkManager/NetworkManager.conf", "usr/sbin/NetworkManager", "usr/bin/nmcli"):
            if candidate in present:
                backend_path = "/" + candidate
                break
        managed_path = "/etc/NetworkManager/system-connections/90-chromapress.nmconnection"
        managed_style = "networkmanager-keyfile"
    elif "etc/netplan" in present:
        backend = "netplan"
        backend_path = "/etc/netplan"
        managed_path = "/etc/netplan/90-chromapress.yaml"
        managed_style = "netplan-managed-yaml"
    elif "etc/network/interfaces" in present:
        backend = "ifupdown"
        backend_path = "/etc/network/interfaces"
        managed_path = "/etc/network/interfaces.d/90-chromapress"
        managed_style = "ifupdown-managed-fragment"
    elif any(key in present for key in (
        "etc/systemd/network", "usr/lib/systemd/system/systemd-networkd.service", "lib/systemd/system/systemd-networkd.service",
    )):
        backend = "systemd-networkd"
        for candidate in ("etc/systemd/network", "usr/lib/systemd/system/systemd-networkd.service", "lib/systemd/system/systemd-networkd.service"):
            if candidate in present:
                backend_path = "/" + candidate
                break
        managed_path = "/etc/systemd/network/90-chromapress.network"
        managed_style = "systemd-networkd-managed-unit"

    resolver_path = ""
    if "etc/systemd/resolved.conf" in present:
        resolver_path = "/etc/systemd/resolved.conf"
    elif "etc/resolv.conf" in present:
        resolver_path = "/etc/resolv.conf"

    if not backend:
        base["reason"] = "UNKNOWN — no supported target-rootfs network backend was verified from safe metadata. Host networking was not consulted."
        return base

    backend_layer = present.get(backend_path.lstrip("/"), "")
    if not backend_layer:
        base["reason"] = "UNKNOWN — network backend was identified but could not be bound to a SquashFS evidence layer."
        return base

    supported_operations = ["configure_dhcp_ipv4", "configure_static_ipv4"]
    dns_status = "SUPPORTED_WITH_REQUIREMENTS" if resolver_path else "UNKNOWN"
    if resolver_path:
        supported_operations.insert(0, "configure_dns_servers")
    nm_profile_status = "UNSUPPORTED"
    if backend == "NetworkManager":
        nm_profile_status = "SUPPORTED_WITH_REQUIREMENTS"
        supported_operations.append("create_networkmanager_profile")
        if profile_names:
            supported_operations.append("set_networkmanager_autoconnect")

    resolver_layer = present.get(resolver_path.lstrip("/"), "") if resolver_path else ""
    profile_dir = "/etc/NetworkManager/system-connections" if backend == "NetworkManager" else ""
    if profile_dir and not profile_dir_layer:
        profile_dir_layer = present.get(profile_dir.lstrip("/"), "")

    base.update({
        "verified": True,
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "addressing_status": "SUPPORTED_WITH_REQUIREMENTS",
        "dns_status": dns_status,
        "networkmanager_profile_status": nm_profile_status,
        "backend": backend,
        "backend_config_path": backend_path,
        "backend_config_layer": backend_layer,
        "managed_config_path": managed_path,
        "managed_config_style": managed_style,
        "resolver_path": resolver_path,
        "resolver_layer": resolver_layer,
        "supported_operations": supported_operations,
        "networkmanager_profile_directory": profile_dir,
        "networkmanager_profile_directory_layer": profile_dir_layer,
        "networkmanager_profile_names": profile_names,
        "reason": (
            "PASS — Alpha 51 target-rootfs network backend capability verified from read-only metadata; "
            "DHCP/static IPv4/DNS staging is capability-gated. NetworkManager profile contents, netplan YAML, "
            "Wi-Fi/VPN credentials and Windows/WSL host networking were not read."
        ),
    })
    return base

def _inspect_services_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, str]:
    """Inspect only systemd unit-directory metadata through a temporary read-only mount.

    Unit file contents, enablement symlink targets, environment files and service
    credentials are deliberately not read.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}
    wanted = (
        "usr/lib/systemd/system",
        "lib/systemd/system",
        "etc/systemd/system",
    )
    found: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-services-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                    if listing.returncode == 0 and member in text:
                        found[member] = layer
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_services_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify systemd unit-directory evidence without reading unit contents or secrets."""
    base: dict[str, object] = {
        "verified": False,
        "init_system": "",
        "vendor_unit_path": "",
        "vendor_unit_layer": "",
        "local_unit_path": "",
        "local_unit_layer": "",
        "unit_contents_read": False,
        "enablement_links_read": False,
        "service_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs services/systemd evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; services/systemd staging stays blocked."
        return base

    members = (
        "/usr/lib/systemd/system",
        "/lib/systemd/system",
        "/etc/systemd/system",
    )
    present: dict[str, str] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in members:
            ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
            if ok:
                present[member.lstrip("/")] = layer
    mounted = _inspect_services_from_readonly_mount(path, layers)
    for member, layer in mounted.items():
        present.setdefault(member, layer)

    vendor_path = ""
    if "usr/lib/systemd/system" in present:
        vendor_path = "/usr/lib/systemd/system"
    elif "lib/systemd/system" in present:
        vendor_path = "/lib/systemd/system"
    if not vendor_path:
        base["reason"] = "No supported systemd vendor unit directory was verified read-only inside the selected rootfs."
        return base

    local_path = "/etc/systemd/system" if "etc/systemd/system" in present else ""
    base.update({
        "verified": True,
        "init_system": "systemd",
        "vendor_unit_path": vendor_path,
        "vendor_unit_layer": present[vendor_path.lstrip("/")],
        "local_unit_path": local_path,
        "local_unit_layer": present.get(local_path.lstrip("/"), "") if local_path else "",
        "reason": "PASS — systemd unit-directory evidence verified read-only; unit contents, enablement links, environment files and service credentials were not read.",
    })
    return base

def _system_timers_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify systemd timer staging evidence without reading timer/unit contents or secrets."""
    base: dict[str, object] = {
        "verified": False,
        "init_system": "",
        "vendor_unit_path": "",
        "vendor_unit_layer": "",
        "local_unit_path": "",
        "local_unit_layer": "",
        "timer_contents_read": False,
        "enablement_links_read": False,
        "service_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs timers/systemd evidence is not available.",
    }
    services = _system_services_rootfs_evidence(path, layers)
    if services.get("verified") is not True:
        base["reason"] = str(services.get("reason") or base["reason"])
        return base
    base.update({
        "verified": True,
        "init_system": "systemd",
        "vendor_unit_path": str(services.get("vendor_unit_path") or ""),
        "vendor_unit_layer": str(services.get("vendor_unit_layer") or ""),
        "local_unit_path": str(services.get("local_unit_path") or ""),
        "local_unit_layer": str(services.get("local_unit_layer") or ""),
        "reason": "PASS — systemd unit-directory evidence for timer staging verified read-only; timer contents, enablement links, environment files and service credentials were not read.",
    })
    return base


def _system_targets_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify systemd default-target staging evidence without reading target/unit contents."""
    base: dict[str, object] = {
        "verified": False,
        "init_system": "",
        "vendor_unit_path": "",
        "vendor_unit_layer": "",
        "local_unit_path": "",
        "local_unit_layer": "",
        "target_contents_read": False,
        "default_target_symlink_read": False,
        "service_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs targets/systemd evidence is not available.",
    }
    services = _system_services_rootfs_evidence(path, layers)
    if services.get("verified") is not True:
        base["reason"] = str(services.get("reason") or base["reason"])
        return base
    base.update({
        "verified": True,
        "init_system": "systemd",
        "vendor_unit_path": str(services.get("vendor_unit_path") or ""),
        "vendor_unit_layer": str(services.get("vendor_unit_layer") or ""),
        "local_unit_path": str(services.get("local_unit_path") or ""),
        "local_unit_layer": str(services.get("local_unit_layer") or ""),
        "reason": "PASS — systemd unit-directory evidence for default-target staging verified read-only; target contents and default.target symlink target were not read.",
    })
    return base



def _inspect_firewall_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, str]:
    """Inspect only firewall backend path metadata through a temporary read-only mount.

    Firewall rule contents, ports/services policy, application profiles and secrets
    are deliberately not read.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}
    wanted = (
        "etc/ufw",
        "usr/sbin/ufw",
        "etc/firewalld",
        "usr/sbin/firewalld",
        "etc/nftables.conf",
        "usr/sbin/nft",
    )
    found: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-firewall-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                    if listing.returncode == 0 and member in text:
                        found[member] = layer
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_firewall_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify a supported firewall backend without reading firewall rules or secrets."""
    base: dict[str, object] = {
        "verified": False,
        "backend": "",
        "backend_path": "",
        "backend_layer": "",
        "rule_contents_read": False,
        "ports_services_policy_read": False,
        "application_profiles_read": False,
        "firewall_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs firewall evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; firewall staging stays blocked."
        return base

    members = (
        "/etc/ufw",
        "/usr/sbin/ufw",
        "/etc/firewalld",
        "/usr/sbin/firewalld",
        "/etc/nftables.conf",
        "/usr/sbin/nft",
    )
    present: dict[str, str] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in members:
            ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
            if ok:
                present[member.lstrip("/")] = layer
    mounted = _inspect_firewall_from_readonly_mount(path, layers)
    for member, layer in mounted.items():
        present.setdefault(member, layer)

    choices = (
        ("ufw", ("etc/ufw", "usr/sbin/ufw")),
        ("firewalld", ("etc/firewalld", "usr/sbin/firewalld")),
        ("nftables", ("etc/nftables.conf", "usr/sbin/nft")),
    )
    backend = ""
    evidence_member = ""
    for candidate, paths in choices:
        for member in paths:
            if member in present:
                backend = candidate
                evidence_member = member
                break
        if backend:
            break
    if not backend:
        base["reason"] = "No supported rootfs firewall backend evidence was verified without reading firewall rules."
        return base

    base.update({
        "verified": True,
        "backend": backend,
        "backend_path": "/" + evidence_member,
        "backend_layer": present[evidence_member],
        "reason": "PASS — firewall backend evidence verified read-only; firewall rule contents, ports/services policy, application profiles and secrets were not read.",
    })
    return base



def _inspect_apparmor_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, str]:
    """Inspect only AppArmor component path metadata through a temporary read-only mount.

    AppArmor profile contents, parser configuration contents, abstractions/tunables and
    policy secrets are deliberately not read.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}
    wanted = (
        "usr/sbin/apparmor_parser",
        "usr/lib/systemd/system/apparmor.service",
        "lib/systemd/system/apparmor.service",
        "etc/apparmor.d",
    )
    found: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-apparmor-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                    if listing.returncode == 0 and member in text:
                        found[member] = layer
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_apparmor_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify AppArmor component presence without reading AppArmor policy/profile contents."""
    base: dict[str, object] = {
        "verified": False,
        "backend": "",
        "evidence_path": "",
        "evidence_layer": "",
        "profile_contents_read": False,
        "parser_config_read": False,
        "abstractions_tunables_read": False,
        "apparmor_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs AppArmor evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; AppArmor staging stays blocked."
        return base

    members = (
        "/usr/sbin/apparmor_parser",
        "/usr/lib/systemd/system/apparmor.service",
        "/lib/systemd/system/apparmor.service",
        "/etc/apparmor.d",
    )
    present: dict[str, str] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in members:
            ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
            if ok:
                present[member.lstrip("/")] = layer
    mounted = _inspect_apparmor_from_readonly_mount(path, layers)
    for member, layer in mounted.items():
        present.setdefault(member, layer)

    evidence_member = ""
    for member in (
        "usr/sbin/apparmor_parser",
        "usr/lib/systemd/system/apparmor.service",
        "lib/systemd/system/apparmor.service",
        "etc/apparmor.d",
    ):
        if member in present:
            evidence_member = member
            break
    if not evidence_member:
        base["reason"] = "No AppArmor rootfs component evidence was verified without reading AppArmor policy/profile contents."
        return base

    base.update({
        "verified": True,
        "backend": "apparmor",
        "evidence_path": "/" + evidence_member,
        "evidence_layer": present[evidence_member],
        "reason": "PASS — AppArmor component evidence verified read-only; profile contents, parser configuration contents, abstractions/tunables and policy secrets were not read.",
    })
    return base



def _parse_selinux_config_metadata(text: str) -> tuple[str, str]:
    """Parse only SELINUX/SELINUXTYPE from /etc/selinux/config."""
    mode = ""
    policy_type = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        value = value.strip('"\'').casefold()
        if key == "SELINUX" and value in {"enforcing", "permissive", "disabled"}:
            mode = value
        elif key == "SELINUXTYPE" and re.fullmatch(r"[a-z0-9_.+-]{1,64}", value):
            policy_type = value
    return mode, policy_type


def _selinux_package_names_from_iso(files: list[str]) -> list[str]:
    """Return package basenames visibly carried by the selected ISO, never host packages."""
    names: list[str] = []
    needles = (
        "selinux-basics", "selinux-policy", "policycoreutils", "libselinux",
        "setools", "checkpolicy", "mcstrans", "auditd",
    )
    for member in files:
        base = Path(member).name
        low = base.casefold()
        if not low.endswith((".deb", ".rpm", ".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz")):
            continue
        if any(needle in low for needle in needles) and base not in names:
            names.append(base)
    return sorted(names)[:80]


def _classify_selinux_capability(
    *,
    components_present: bool,
    config_mode: str,
    package_mechanism_verified: bool,
    packages_available_on_iso: bool,
    kernel_support_status: str,
) -> str:
    """Capability-only classifier. UNKNOWN is preferred over unsupported guesses."""
    if components_present:
        if kernel_support_status == "UNSUPPORTED":
            return "BLOCKED"
        if config_mode in {"enforcing", "permissive"} and kernel_support_status == "SUPPORTED":
            return "SUPPORTED"
        return "SUPPORTED_WITH_REQUIREMENTS"
    if package_mechanism_verified and packages_available_on_iso and kernel_support_status != "UNSUPPORTED":
        return "SUPPORTED_WITH_REQUIREMENTS"
    if kernel_support_status == "UNSUPPORTED" and not package_mechanism_verified:
        return "UNSUPPORTED"
    return "UNKNOWN"


def _system_selinux_rootfs_evidence(
    path: Path,
    layers: list[str],
    *,
    package_format: str = "unknown",
    manifest_versions: dict[str, str] | None = None,
    iso_files: list[str] | None = None,
    kernel_images: list[str] | None = None,
    boot_config_files: list[str] | None = None,
    initramfs_mechanism: str = "",
) -> dict[str, object]:
    """Alpha 52 SELinux capability detection against the selected ISO only.

    The probe reads only /etc/selinux/config key/value metadata when present. It
    never executes target SELinux utilities, reads target policy payloads, or
    consults the Windows/WSL host SELinux state.
    """
    allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
    base: dict[str, object] = {
        "gate_version": "alpha52",
        "analysis_scope": "target_iso_rootfs",
        "capability_status": "UNKNOWN",
        "verified": False,
        "installed_present": False,
        "configured_mode": "unknown",
        "policy_type": "",
        "config_path": "/etc/selinux/config",
        "config_layer": "",
        "config_metadata_read": False,
        "config_creation_required": False,
        "policy_tree_present": False,
        "policy_entries": [],
        "policy_contents_read": False,
        "custom_policy_preserved": True,
        "package_format": str(package_format or "unknown"),
        "package_manager": "",
        "package_manager_path": "",
        "package_manager_layer": "",
        "repository_metadata_path": "",
        "repository_metadata_layer": "",
        "package_mechanism_verified": False,
        "installed_selinux_packages": [],
        "available_selinux_packages": [],
        "required_packages": [],
        "package_install_required": False,
        "kernel_support_status": "UNKNOWN",
        "kernel_config_path": "",
        "kernel_config_layer": "",
        "kernel_config_metadata_read": False,
        "kernel_images": list(kernel_images or []),
        "boot_config_files": list(boot_config_files or []),
        "initramfs_mechanism": str(initramfs_mechanism or ""),
        "part3_dependency_required": False,
        "part3_requirements": [],
        "relabel_required_on_enable": False,
        "reboot_required": False,
        "supported_modes": [],
        "supported_operations": [],
        "host_selinux_accessed": False,
        "host_security_state_accessed": False,
        "source_read_only": True,
        "secret_read": False,
        "reason": "UNKNOWN — SELinux capability has not been verified for the selected target rootfs.",
    }
    if not layers:
        base["reason"] = "UNKNOWN — no SquashFS target rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "UNKNOWN — unsquashfs is unavailable; SELinux target-rootfs capability cannot be verified."
        return base

    manifests = manifest_versions or {}
    files = iso_files or []
    extents = _iso_member_extents(path, layers)

    wanted = (
        "/etc/selinux/config", "/etc/selinux", "/usr/sbin/selinuxenabled",
        "/usr/sbin/getenforce", "/usr/sbin/setenforce", "/usr/sbin/load_policy",
        "/usr/sbin/restorecon", "/usr/sbin/selinux-activate",
        "/usr/bin/apt-get", "/etc/apt/sources.list", "/etc/apt/sources.list.d",
        "/usr/bin/dnf", "/usr/bin/yum", "/etc/yum.repos.d",
        "/usr/bin/pacman", "/etc/pacman.conf",
    )
    present: dict[str, str] = {}
    for member in wanted:
        ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
        if ok:
            present[member] = layer

    config_text = ""
    if "/etc/selinux/config" in present:
        config_text, config_layer = _read_squashfs_overlay_text(path, layers, "/etc/selinux/config", extents)
        if config_text:
            mode, policy_type = _parse_selinux_config_metadata(config_text)
            base["configured_mode"] = mode or "unknown"
            base["policy_type"] = policy_type
            base["config_layer"] = config_layer
            base["config_metadata_read"] = True
        else:
            base["config_layer"] = present["/etc/selinux/config"]

    policy_entries: list[str] = []
    if "/etc/selinux" in present:
        entries, _layer = _list_overlay_directory_entries(path, layers, "/etc/selinux", extents)
        policy_entries = [x for x in entries if x and x != "config"]
        base["policy_tree_present"] = True
        base["policy_entries"] = policy_entries[:40]

    installed = []
    for package in sorted(manifests):
        low = package.casefold()
        if (
            low in {"selinux-basics", "policycoreutils", "selinux-policy-default", "selinux-policy-targeted", "libselinux-utils", "auditd"}
            or low.startswith(("selinux-policy", "libselinux", "policycoreutils"))
        ):
            installed.append(package)
    base["installed_selinux_packages"] = installed[:80]
    available = _selinux_package_names_from_iso(files)
    base["available_selinux_packages"] = available

    component_paths = {
        "/etc/selinux/config", "/usr/sbin/selinuxenabled", "/usr/sbin/getenforce",
        "/usr/sbin/setenforce", "/usr/sbin/load_policy", "/usr/sbin/restorecon",
        "/usr/sbin/selinux-activate",
    }
    components_present = bool(installed or any(member in present for member in component_paths))
    base["installed_present"] = components_present
    base["config_creation_required"] = bool(components_present and "/etc/selinux/config" not in present)

    fmt = str(package_format or "unknown").casefold()
    package_manager = ""
    manager_path = ""
    manager_layer = ""
    repo_path = ""
    repo_layer = ""
    if fmt == "deb" and "/usr/bin/apt-get" in present:
        package_manager = "apt"
        manager_path = "/usr/bin/apt-get"
        manager_layer = present[manager_path]
        for candidate in ("/etc/apt/sources.list.d", "/etc/apt/sources.list"):
            if candidate in present:
                repo_path, repo_layer = candidate, present[candidate]
                break
    elif fmt == "rpm":
        for candidate in ("/usr/bin/dnf", "/usr/bin/yum"):
            if candidate in present:
                package_manager = "dnf" if candidate.endswith("dnf") else "yum"
                manager_path, manager_layer = candidate, present[candidate]
                break
        if "/etc/yum.repos.d" in present:
            repo_path, repo_layer = "/etc/yum.repos.d", present["/etc/yum.repos.d"]
    elif fmt == "pkg.tar" and "/usr/bin/pacman" in present:
        package_manager = "pacman"
        manager_path, manager_layer = "/usr/bin/pacman", present["/usr/bin/pacman"]
        if "/etc/pacman.conf" in present:
            repo_path, repo_layer = "/etc/pacman.conf", present["/etc/pacman.conf"]
    package_mechanism_verified = bool(package_manager and repo_path)
    base.update({
        "package_manager": package_manager,
        "package_manager_path": manager_path,
        "package_manager_layer": manager_layer,
        "repository_metadata_path": repo_path,
        "repository_metadata_layer": repo_layer,
        "package_mechanism_verified": package_mechanism_verified,
    })

    required_packages: list[str] = []
    if components_present:
        # Existing installed packages are preserved. Additions are resolved only when a
        # concrete missing requirement is visible; never replace policy packages.
        required_packages = []
    elif available:
        # Package basenames are evidence, not package-manager arguments. The later
        # package resolver must map/signature-verify them before apply.
        required_packages = available[:20]
    base["required_packages"] = required_packages
    base["package_install_required"] = bool(not components_present and required_packages)

    # Kernel capability: inspect target /boot/config-* metadata only when the rootfs
    # actually carries such a file. Never inspect /proc/config.gz or host /boot.
    kernel_status = "UNKNOWN"
    kernel_cfg_path = ""
    kernel_cfg_layer = ""
    boot_entries, boot_layer = _list_overlay_directory_entries(path, layers, "/boot", extents)
    for name in sorted(boot_entries):
        if not name.startswith("config-"):
            continue
        text, layer = _read_squashfs_overlay_text(path, layers, f"/boot/{name}", extents)
        if not text:
            continue
        kernel_cfg_path, kernel_cfg_layer = f"/boot/{name}", layer or boot_layer
        base["kernel_config_metadata_read"] = True
        if re.search(r"^CONFIG_SECURITY_SELINUX=y$", text, re.M):
            kernel_status = "SUPPORTED"
        elif re.search(r"^# CONFIG_SECURITY_SELINUX is not set$", text, re.M):
            kernel_status = "UNSUPPORTED"
        break
    base["kernel_support_status"] = kernel_status
    base["kernel_config_path"] = kernel_cfg_path
    base["kernel_config_layer"] = kernel_cfg_layer

    mode = str(base["configured_mode"])
    capability = _classify_selinux_capability(
        components_present=components_present,
        config_mode=mode,
        package_mechanism_verified=package_mechanism_verified,
        packages_available_on_iso=bool(available),
        kernel_support_status=kernel_status,
    )
    if capability not in allowed:
        capability = "UNKNOWN"
    base["capability_status"] = capability

    requirements: list[dict[str, object]] = []
    if base["package_install_required"]:
        requirements.append({"model": "part2_packages", "action": "resolve_install", "packages": list(required_packages)})
    if kernel_status != "SUPPORTED":
        requirements.append({
            "model": "part3_kernel",
            "action": "verify_selinux_kernel_capability",
            "required_config": "CONFIG_SECURITY_SELINUX=y",
            "kernel_images": list(kernel_images or []),
        })
    if initramfs_mechanism in {"update-initramfs", "dracut", "mkinitcpio"}:
        requirements.append({
            "model": "part3_kernel_initramfs",
            "action": "verify_and_regenerate_if_required",
            "initramfs_mechanism": initramfs_mechanism,
        })
    if boot_config_files:
        requirements.append({
            "model": "part3_boot",
            "action": "verify_selinux_boot_parameters",
            "boot_config_files": list(boot_config_files),
            "forbid_parameters": ["selinux=0"],
        })
    base["part3_requirements"] = requirements
    base["part3_dependency_required"] = any(str(x.get("model", "")).startswith("part3") for x in requirements)

    if capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["verified"] = True
        base["supported_modes"] = ["enforcing", "permissive", "disabled"]
        base["supported_operations"] = ["set_selinux_mode"]
        enabling_from_disabled = mode in {"disabled", "unknown"}
        base["relabel_required_on_enable"] = enabling_from_disabled
        base["reboot_required"] = True
        req = []
        if base["package_install_required"]:
            req.append("SELinux packages must be resolved and signature-verified before apply")
        if kernel_status != "SUPPORTED":
            req.append("Part 3 must verify CONFIG_SECURITY_SELINUX=y for the selected kernel")
        if boot_config_files:
            req.append("Part 3 must verify existing boot parameters do not disable SELinux")
        if enabling_from_disabled:
            req.append("filesystem relabel is required before/at first SELinux-enabled boot")
        if req:
            base["reason"] = f"{capability} — " + "; ".join(req) + "."
        else:
            base["reason"] = f"{capability} — SELinux target-rootfs components and configuration metadata are verified."
    elif capability == "UNSUPPORTED":
        base["verified"] = True
        base["reason"] = "UNSUPPORTED — target kernel metadata explicitly lacks CONFIG_SECURITY_SELINUX and no verified target package mechanism was found to remediate it."
    elif capability == "BLOCKED":
        base["verified"] = True
        base["reason"] = "BLOCKED — SELinux components are present but target kernel metadata explicitly reports CONFIG_SECURITY_SELINUX disabled; a verified Part 3 kernel remediation is required before state changes."
    else:
        base["verified"] = False
        base["reason"] = "UNKNOWN — SELinux presence/addability or kernel/boot requirements cannot be verified safely from the selected target image; staging is blocked."
    return base

def _inspect_sysctl_from_readonly_mount(iso: Path, layers: list[str]) -> dict[str, str]:
    """Inspect only sysctl component/path metadata through a temporary read-only mount.

    Existing sysctl configuration contents and effective runtime values are deliberately
    not read at this gate.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0 or not layers:
        return {}
    mount_bin = shutil.which("mount")
    umount_bin = shutil.which("umount")
    unsquashfs = shutil.which("unsquashfs")
    if not mount_bin or not umount_bin or not unsquashfs:
        return {}
    wanted = (
        "usr/sbin/sysctl",
        "sbin/sysctl",
        "etc/sysctl.conf",
        "etc/sysctl.d",
        "usr/lib/sysctl.d",
    )
    found: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="chromapress-sysctl-ro-") as td:
        mountpoint = Path(td) / "iso"
        mountpoint.mkdir()
        try:
            mounted = subprocess.run(
                [mount_bin, "-o", "loop,ro", str(iso), str(mountpoint)],
                text=True, capture_output=True, check=False, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if mounted.returncode != 0:
            return {}
        try:
            for layer in reversed(layers):
                squash = mountpoint / layer.lstrip("/")
                if not squash.is_file():
                    continue
                for member in wanted:
                    if member in found:
                        continue
                    try:
                        listing = subprocess.run(
                            [unsquashfs, "-ll", str(squash), member],
                            text=True, capture_output=True, check=False, timeout=30,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        continue
                    text = (listing.stdout or "") + "\n" + (listing.stderr or "")
                    if listing.returncode == 0 and member in text:
                        found[member] = layer
        finally:
            try:
                subprocess.run([umount_bin, str(mountpoint)], text=True, capture_output=True, check=False, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return found


def _system_sysctl_rootfs_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    """Verify sysctl infrastructure without reading existing sysctl values/config contents."""
    base: dict[str, object] = {
        "verified": False,
        "backend": "",
        "evidence_path": "",
        "evidence_layer": "",
        "config_contents_read": False,
        "runtime_values_read": False,
        "sysctl_secrets_read": False,
        "secret_read": False,
        "reason": "Rootfs sysctl evidence is not available.",
    }
    if not layers:
        base["reason"] = "No SquashFS rootfs layer was detected."
        return base
    if not shutil.which("unsquashfs"):
        base["reason"] = "unsquashfs is unavailable in the selected WSL distribution; sysctl staging stays blocked."
        return base

    members = (
        "/usr/sbin/sysctl",
        "/sbin/sysctl",
        "/etc/sysctl.conf",
        "/etc/sysctl.d",
        "/usr/lib/sysctl.d",
    )
    present: dict[str, str] = {}
    extents = _iso_member_extents(path, layers)
    if extents:
        for member in members:
            ok, layer = _inspect_overlay_member_presence(path, layers, member, extents)
            if ok:
                present[member.lstrip("/")] = layer
    mounted = _inspect_sysctl_from_readonly_mount(path, layers)
    for member, layer in mounted.items():
        present.setdefault(member, layer)

    evidence_member = ""
    for member in (
        "usr/sbin/sysctl",
        "sbin/sysctl",
        "etc/sysctl.d",
        "usr/lib/sysctl.d",
        "etc/sysctl.conf",
    ):
        if member in present:
            evidence_member = member
            break
    if not evidence_member:
        base["reason"] = "No sysctl rootfs infrastructure evidence was verified without reading existing sysctl configuration contents."
        return base

    base.update({
        "verified": True,
        "backend": "procps-sysctl",
        "evidence_path": "/" + evidence_member,
        "evidence_layer": present[evidence_member],
        "reason": "PASS — sysctl infrastructure evidence verified read-only; existing sysctl configuration contents and effective runtime values were not read.",
    })
    return base


def _squashfs_readonly_details(path: Path, layers: list[str]) -> list[dict[str, object]]:
    """Inspect SquashFS superblocks without extracting or modifying the source."""
    if not layers:
        return []
    details: list[dict[str, object]] = []
    extents = _iso_member_extents(path, layers)
    unsquashfs = shutil.which("unsquashfs")
    for member in layers:
        item: dict[str, object] = {"path": member, "compression": "unknown"}
        extent = extents.get(member)
        if unsquashfs and extent:
            cp = subprocess.run(
                [unsquashfs, "-s", "-offset", str(extent[0]), str(path)],
                text=True, capture_output=True, check=False,
            )
            text = (cp.stdout or "") + "\n" + (cp.stderr or "")
            if cp.returncode == 0:
                match = re.search(r"^Compression\s+([^\s]+)", text, re.I | re.M)
                if match:
                    item["compression"] = match.group(1)
                match = re.search(r"^Block size\s+(\d+)", text, re.I | re.M)
                if match:
                    item["block_size"] = int(match.group(1))
        details.append(item)
    return details


def _parse_os_release(text: str) -> dict[str, str]:
    """Parse non-secret /etc/os-release metadata from the target rootfs."""
    out: dict[str, str] = {}
    allowed = {"ID", "ID_LIKE", "NAME", "PRETTY_NAME", "VERSION", "VERSION_ID", "VERSION_CODENAME"}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().upper()
        if key not in allowed:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]
        out[key.lower()] = value
    return out


def _os_release_evidence(path: Path, layers: list[str]) -> dict[str, object]:
    extents = _iso_member_extents(path, layers) if layers else {}
    text, layer = _read_squashfs_overlay_text(path, layers, "/etc/os-release", extents)
    if not text:
        return {"status": "UNKNOWN", "verified": False, "path": "/etc/os-release", "reason": "No readable /etc/os-release evidence was available from the target rootfs."}
    parsed = _parse_os_release(text)
    if not parsed.get("id"):
        return {"status": "UNKNOWN", "verified": False, "path": "/etc/os-release", "layer": layer, "reason": "Target /etc/os-release did not contain an ID field."}
    return {
        "status": "PASS", "verified": True, "path": "/etc/os-release", "layer": layer,
        **parsed,
        "reason": "PASS — distribution identity metadata read from target /etc/os-release; no host distribution state was used.",
    }


def analyze(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    pvd = _run(["xorriso", "-indev", str(path), "-pvd_info"])
    files = _iso_files(path)
    low_files = [x.lower() for x in files]
    volume_match = re.search(r"Volume id\s*:\s*['\"]?([^'\"\n]+)", pvd, re.I)
    volume = volume_match.group(1).strip() if volume_match else ""
    text = (volume + " " + " ".join(files[:2000])).lower()

    distribution = "Linux"
    if "lubuntu" in text:
        distribution = "Lubuntu"
    elif "ubuntu" in text:
        distribution = "Ubuntu"
    elif "debian" in text:
        distribution = "Debian"
    elif any("/repodata/" in x for x in low_files):
        distribution = "RPM-family Linux"
    elif any("/arch/" in x for x in low_files):
        distribution = "Arch-family Linux"

    version = ""
    m = re.search(r"(?:ubuntu|lubuntu)[ _-]?(\d{2}\.\d{2}(?:\.\d+)?)", text)
    if m:
        version = m.group(1)

    rootfs = _rootfs_layers(files)

    package_format = "unknown"
    if any(x.endswith(".deb") or "/binary-amd64/packages" in x for x in low_files):
        package_format = "deb"
    elif any(x.endswith(".rpm") or "/repodata/" in x for x in low_files):
        package_format = "rpm"
    elif any(".pkg.tar." in x for x in low_files):
        package_format = "pkg.tar"

    arch = "amd64" if "amd64" in text or "x86_64" in text else "unknown"

    # Optional xorriso reports add evidence but never make source analysis fail.
    el_torito_report = _optional_run(["xorriso", "-indev", str(path), "-report_el_torito", "plain"])
    system_area_report = _optional_run(["xorriso", "-indev", str(path), "-report_system_area", "plain"])
    boot = _boot_source_metadata(files, el_torito_report, system_area_report)
    rootfs_details = _squashfs_readonly_details(path, rootfs)
    os_release_evidence = _os_release_evidence(path, rootfs)
    os_id = str(os_release_evidence.get("id") or "").casefold()
    distro_by_os_id = {
        "rhel": "RHEL", "rocky": "Rocky Linux", "almalinux": "AlmaLinux", "ol": "Oracle Linux",
        "fedora": "Fedora", "linuxmint": "Linux Mint", "centos": "CentOS Stream", "debian": "Debian",
        "arch": "Arch Linux", "manjaro": "Manjaro", "opensuse": "openSUSE", "opensuse-leap": "openSUSE",
        "opensuse-tumbleweed": "openSUSE", "sles": "SUSE Linux Enterprise", "sled": "SUSE Linux Enterprise Desktop",
    }
    if distribution not in {"Lubuntu", "Ubuntu"} and os_id in distro_by_os_id:
        distribution = distro_by_os_id[os_id]
    if not version and os_release_evidence.get("version_id"):
        version = str(os_release_evidence.get("version_id") or "")
    system_identity_evidence = _system_identity_rootfs_evidence(path, rootfs)
    system_security_defaults_evidence = _system_security_defaults_evidence(system_identity_evidence)
    system_config_overlay_evidence = _system_config_overlay_rootfs_evidence(path, rootfs)
    system_kiosk_user_evidence = _system_kiosk_user_evidence(system_identity_evidence)
    system_restricted_login_evidence = _system_restricted_login_evidence(path, rootfs, system_identity_evidence)
    system_machine_identity_evidence = _system_machine_identity_rootfs_evidence(path, rootfs)
    system_autologin_evidence = _system_autologin_rootfs_evidence(path, rootfs)
    system_restricted_session_evidence = _system_restricted_session_evidence(path, rootfs, system_autologin_evidence, system_restricted_login_evidence)
    system_service_lockdown_evidence = _system_service_lockdown_evidence(path, rootfs, _system_services_rootfs_evidence(path, rootfs))
    system_locale_evidence = _system_locale_rootfs_evidence(path, rootfs)
    system_keyboard_evidence = _system_keyboard_rootfs_evidence(path, rootfs)
    system_timezone_evidence = _system_timezone_rootfs_evidence(path, rootfs)
    system_network_dns_evidence = _system_network_dns_rootfs_evidence(path, rootfs)
    system_network_restriction_evidence = _system_network_restriction_evidence(path, rootfs, system_network_dns_evidence)
    system_services_evidence = _system_services_rootfs_evidence(path, rootfs)
    system_timers_evidence = _system_timers_rootfs_evidence(path, rootfs)
    system_targets_evidence = _system_targets_rootfs_evidence(path, rootfs)
    system_firewall_evidence = _system_firewall_rootfs_evidence(path, rootfs)
    system_firewall_rules_evidence = _system_firewall_rules_evidence(path, rootfs, system_firewall_evidence)
    system_persistence_policy_evidence = _system_persistence_policy_evidence(rootfs, boot, package_format, system_kiosk_user_evidence)
    system_admin_recovery_policy_evidence = _system_admin_recovery_policy_evidence(
        system_identity_evidence, system_autologin_evidence, system_kiosk_user_evidence
    )
    system_apparmor_evidence = _system_apparmor_rootfs_evidence(path, rootfs)
    system_sysctl_evidence = _system_sysctl_rootfs_evidence(path, rootfs)
    boot_config_details = _boot_config_readonly_details(path, list(boot.get("boot_config_files") or []))
    with tempfile.TemporaryDirectory(prefix="chromapress-hardware-manifest-") as td:
        manifest_versions = _manifest_versions(path, files, Path(td))
    system_selinux_evidence = _system_selinux_rootfs_evidence(
        path, rootfs, package_format=package_format, manifest_versions=manifest_versions,
        iso_files=files, kernel_images=list(boot.get("kernel_images") or []),
        boot_config_files=list(boot.get("boot_config_files") or []),
        initramfs_mechanism=("update-initramfs" if package_format == "deb" else "dracut" if package_format == "rpm" else "mkinitcpio" if package_format == "pkg.tar" else ""),
    )
    hardware_packages = _hardware_package_hints(manifest_versions)
    system_details = _system_config_evidence(manifest_versions)
    system_fido2_policy_evidence = _system_fido2_policy_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence
    )
    system_webauthn_policy_evidence = _system_webauthn_policy_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence, system_fido2_policy_evidence
    )
    system_security_key_policy_evidence = _system_security_key_policy_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence, system_fido2_policy_evidence
    )
    system_yubikey_policy_evidence = _system_yubikey_policy_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence, system_security_key_policy_evidence
    )
    system_platform_authenticator_policy_evidence = _system_platform_authenticator_policy_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence, system_webauthn_policy_evidence
    )
    system_tpm_key_protection_evidence = _system_tpm_key_protection_evidence(
        package_format, manifest_versions, system_admin_recovery_policy_evidence
    )
    installer_details = _installer_evidence(files, manifest_versions)
    installer = str(installer_details.get("installer") or "unknown")
    part5_installer_evidence = installer_capability(
        installer, package_format, list(installer_details.get("installer_evidence") or []),
        list(installer_details.get("installer_config_files") or []),
    )
    part5_desktop_evidence = desktop_capability(manifest_versions)
    part5_custom_content_evidence = custom_content_capability(rootfs)
    part5_kiosk_evidence = kiosk_capability(manifest_versions, part5_desktop_evidence)

    # Part 3 capability model: identify the distro-native initramfs mechanism
    # expected for the detected package family. This is not a claim that the
    # executable is present in every rootfs layer; apply must verify that later.
    initramfs_mechanism = ""
    if package_format == "deb":
        initramfs_mechanism = "update-initramfs"
    elif package_format == "rpm":
        initramfs_mechanism = "dracut"
    elif package_format == "pkg.tar":
        initramfs_mechanism = "mkinitcpio"

    return {
        "path": str(path),
        "sha256": _sha256(path),
        "volume_id": volume,
        "distribution": distribution,
        "version": version,
        "architecture": arch,
        "installer": installer,
        "installer_evidence": list(installer_details.get("installer_evidence") or []),
        "installer_config_files": list(installer_details.get("installer_config_files") or []),
        "installer_modes": list(installer_details.get("installer_modes") or []),
        "part5_installer_evidence": part5_installer_evidence,
        "part5_custom_content_evidence": part5_custom_content_evidence,
        "part5_desktop_evidence": part5_desktop_evidence,
        "part5_kiosk_evidence": part5_kiosk_evidence,
        "os_release_evidence": os_release_evidence,
        "package_format": package_format,
        "rootfs": rootfs,
        "rootfs_details": rootfs_details,
        "file_count": len(files),
        **boot,
        **boot_config_details,
        "initramfs_mechanism": initramfs_mechanism,
        "hardware_package_hints": hardware_packages,
        "component_inventory": _component_inventory(manifest_versions),
        "system_package_evidence": list(system_details.get("system_package_evidence") or []),
        "system_rootfs_verification": list(system_details.get("system_rootfs_verification") or []),
        "system_identity_evidence": system_identity_evidence,
        "system_security_defaults_evidence": system_security_defaults_evidence,
        "system_config_overlay_evidence": system_config_overlay_evidence,
        "system_kiosk_user_evidence": system_kiosk_user_evidence,
        "system_restricted_login_evidence": system_restricted_login_evidence,
        "system_machine_identity_evidence": system_machine_identity_evidence,
        "system_autologin_evidence": system_autologin_evidence,
        "system_restricted_session_evidence": system_restricted_session_evidence,
        "system_service_lockdown_evidence": system_service_lockdown_evidence,
        "system_network_restriction_evidence": system_network_restriction_evidence,
        "system_locale_evidence": system_locale_evidence,
        "system_keyboard_evidence": system_keyboard_evidence,
        "system_timezone_evidence": system_timezone_evidence,
        "system_network_dns_evidence": system_network_dns_evidence,
        "system_services_evidence": system_services_evidence,
        "system_timers_evidence": system_timers_evidence,
        "system_targets_evidence": system_targets_evidence,
        "system_firewall_evidence": system_firewall_evidence,
        "system_firewall_rules_evidence": system_firewall_rules_evidence,
        "system_persistence_policy_evidence": system_persistence_policy_evidence,
        "system_admin_recovery_policy_evidence": system_admin_recovery_policy_evidence,
        "system_fido2_policy_evidence": system_fido2_policy_evidence,
        "system_webauthn_policy_evidence": system_webauthn_policy_evidence,
        "system_security_key_policy_evidence": system_security_key_policy_evidence,
        "system_yubikey_policy_evidence": system_yubikey_policy_evidence,
        "system_platform_authenticator_policy_evidence": system_platform_authenticator_policy_evidence,
        "system_tpm_key_protection_evidence": system_tpm_key_protection_evidence,
        "system_apparmor_evidence": system_apparmor_evidence,
        "system_selinux_evidence": system_selinux_evidence,
        "system_sysctl_evidence": system_sysctl_evidence,
    }




def _system_security_key_policy_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
    fido2_policy: dict[str, object],
) -> dict[str, object]:
    """Alpha 65 external security-key class capability from target metadata only.

    This distinguishes generic roaming FIDO2/U2F security-key policy from the
    lower-level Alpha 63 FIDO2 authentication-stack gate. Package evidence can
    prove that target-side tooling exists for later verification; it cannot prove
    that a physical key is connected, compatible, enrolled, or owned by anyone.
    """
    base: dict[str, object] = {
        "gate_version": "alpha65",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "external-fido2-security-key-policy-intent",
        "package_format": str(package_format or "unknown"),
        "security_key_tool_packages": [],
        "libfido2_packages": [],
        "supported_operations": [],
        "policy_scope": "recovery_administrator_external_security_key",
        "alpha62_dependency_verified": False,
        "alpha63_dependency_verified": False,
        "physical_security_key_enumerated": False,
        "security_key_presence_claimed": False,
        "security_key_compatibility_claimed": False,
        "credential_ids_read": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "authenticator_enrollment_performed": False,
        "usb_hid_state_accessed": False,
        "yubikey_capability_claimed": False,
        "platform_authenticator_claimed": False,
        "tpm_capability_claimed": False,
        "host_authenticator_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — external security-key policy capability has not been verified from target package metadata.",
    }
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; security-key policy remains fail-closed."
        return base
    if any(admin_recovery.get(key) is not False for key in (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )):
        base.update({"capability_status": "BLOCKED", "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for security-key staging."})
        return base
    fido_cap = str(fido2_policy.get("capability_status") or "UNKNOWN")
    fido_ok = fido2_policy.get("gate_version") == "alpha63" and fido2_policy.get("verified") is True and fido_cap in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    tools = [name for name in sorted(versions) if name.casefold() in {"fido2-tools", "pamu2fcfg"}]
    libs = [name for name in sorted(versions) if name.casefold() in {"libfido2", "libfido2-1", "libfido2-dev", "libfido2-devel"} or name.casefold().startswith("libfido2-")]
    base.update({
        "security_key_tool_packages": tools,
        "libfido2_packages": libs,
        "alpha62_dependency_verified": True,
        "alpha63_dependency_verified": fido_ok,
    })
    if not fido_ok or not tools or not libs:
        base["reason"] = "UNKNOWN — target metadata does not positively verify the Alpha 63 FIDO2 dependency plus libfido2 and target-side FIDO2/U2F verification tooling. Physical key support is never inferred."
        return base
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": ["allow_external_fido2_security_key_for_recovery_admin"],
        "reason": "PASS — target package metadata verifies the Alpha 63 FIDO2 stack plus target-side FIDO2/U2F tooling. Only an external security-key class policy intent may be staged; no physical key, compatibility, enrollment, credential or host authenticator state is claimed.",
    })
    return base


def _system_yubikey_policy_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
    security_key_policy: dict[str, object],
) -> dict[str, object]:
    """Alpha 66 YubiKey-class policy capability without device-presence claims."""
    base: dict[str, object] = {
        "gate_version": "alpha66",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "yubikey-class-policy-intent",
        "package_format": str(package_format or "unknown"),
        "yubikey_packages": [],
        "supported_operations": [],
        "policy_scope": "recovery_administrator_yubikey_class",
        "alpha62_dependency_verified": False,
        "alpha65_evidence_observed": False,
        "physical_yubikey_enumerated": False,
        "yubikey_presence_claimed": False,
        "serial_number_read": False,
        "otp_secret_read": False,
        "pin_secret_read": False,
        "credential_ids_read": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "authenticator_enrollment_performed": False,
        "usb_hid_state_accessed": False,
        "platform_authenticator_claimed": False,
        "tpm_capability_claimed": False,
        "host_authenticator_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — YubiKey-class policy capability has not been verified from target package metadata.",
    }
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; YubiKey-class policy remains fail-closed."
        return base
    if any(admin_recovery.get(key) is not False for key in (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )):
        base.update({"capability_status": "BLOCKED", "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for YubiKey-class staging."})
        return base
    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    allow = {"yubikey-manager", "yubikey-personalization", "libpam-yubico", "libyubikey0", "libyubikey-dev"}
    yubi = [name for name in sorted(versions) if name.casefold() in allow or name.casefold().startswith("yubikey-")]
    base.update({
        "yubikey_packages": yubi,
        "alpha62_dependency_verified": True,
        "alpha65_evidence_observed": security_key_policy.get("gate_version") == "alpha65",
    })
    if not yubi:
        base["reason"] = "UNKNOWN — target package manifest does not positively identify YubiKey-specific userspace/PAM tooling. ChromaPress does not infer YubiKey capability from generic FIDO2 support or USB hardware."
        return base
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": ["allow_yubikey_class_authenticator_for_recovery_admin"],
        "reason": "PASS — target package metadata positively identifies YubiKey-class userspace/PAM tooling. Only a vendor-class policy intent may be staged; no physical device, serial, PIN/OTP secret, enrollment, credential or host USB/HID state is read or claimed.",
    })
    return base


def _system_platform_authenticator_policy_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
    webauthn_policy: dict[str, object],
) -> dict[str, object]:
    """Alpha 67 platform-authenticator gate.

    Static ISO/package metadata cannot prove a built-in WebAuthn platform
    authenticator because that requires runtime OS integration plus actual device
    hardware/firmware. The current analyzer therefore remains UNKNOWN even when
    Alpha 62/64 prerequisites are visible. This is fail-closed, not UNSUPPORTED.
    """
    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    browser_packages = [name for name in sorted(versions) if name.casefold() in {
        "firefox", "firefox-esr", "chromium", "chromium-browser", "google-chrome-stable",
        "microsoft-edge-stable", "brave-browser", "epiphany-browser",
    }]
    base: dict[str, object] = {
        "gate_version": "alpha67",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "platform-authenticator-runtime-required",
        "package_format": str(package_format or "unknown"),
        "browser_packages": browser_packages,
        "supported_operations": [],
        "policy_scope": "recovery_administrator_platform_authenticator",
        "alpha62_dependency_verified": False,
        "alpha64_dependency_verified": False,
        "platform_authenticator_runtime_verified": False,
        "platform_authenticator_hardware_verified": False,
        "platform_authenticator_claimed": False,
        "biometric_hardware_verified": False,
        "biometric_capability_claimed": False,
        "tpm_hardware_verified": False,
        "tpm_capability_claimed": False,
        "credential_ids_read": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "authenticator_enrollment_performed": False,
        "host_authenticator_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — platform-authenticator prerequisites have not been verified.",
    }
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; platform-authenticator policy remains fail-closed."
        return base
    if any(admin_recovery.get(key) is not False for key in (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )):
        base.update({"capability_status": "BLOCKED", "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for platform-authenticator policy."})
        return base
    web_cap = str(webauthn_policy.get("capability_status") or "UNKNOWN")
    web_ok = webauthn_policy.get("gate_version") == "alpha64" and webauthn_policy.get("verified") is True and web_cap in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
    base.update({"alpha62_dependency_verified": True, "alpha64_dependency_verified": web_ok})
    if not web_ok:
        base["reason"] = f"UNKNOWN — Alpha 64 WebAuthn dependency is {web_cap}; platform-authenticator policy remains fail-closed."
        return base
    base["reason"] = "UNKNOWN — Alpha 62 recovery and Alpha 64 WebAuthn prerequisites are verified, but static target ISO/package metadata cannot positively verify a WebAuthn platform authenticator. Runtime OS integration and actual hardware/firmware must be verified on the target device; biometrics and TPM are not inferred."
    return base


def _system_tpm_key_protection_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
) -> dict[str, object]:
    """Alpha 68 TPM-backed recovery-key protection capability from package metadata."""
    base: dict[str, object] = {
        "gate_version": "alpha68",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "tpm2-key-protection-policy-intent",
        "package_format": str(package_format or "unknown"),
        "tpm_tool_packages": [],
        "tss_packages": [],
        "supported_operations": [],
        "policy_scope": "recovery_administrator_tpm_backed_key_protection",
        "alpha62_dependency_verified": False,
        "tpm_hardware_enumerated": False,
        "tpm_hardware_verified": False,
        "tpm_presence_claimed": False,
        "tpm_ownership_state_read": False,
        "pcr_values_read": False,
        "key_material_generated": False,
        "key_material_read": False,
        "key_material_staged": False,
        "key_material_sealed": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "biometric_capability_claimed": False,
        "platform_authenticator_claimed": False,
        "host_tpm_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — TPM2 key-protection capability has not been verified from target package metadata.",
    }
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; TPM-backed protection remains fail-closed."
        return base
    if any(admin_recovery.get(key) is not False for key in (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )):
        base.update({"capability_status": "BLOCKED", "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for TPM-backed key-protection staging."})
        return base
    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    tools = [name for name in sorted(versions) if name.casefold() in {"tpm2-tools", "tpm2.0-tools"}]
    tss = [name for name in sorted(versions) if name.casefold() in {"tpm2-tss", "libtss2-dev"} or name.casefold().startswith("libtss2-")]
    base.update({"tpm_tool_packages": tools, "tss_packages": tss, "alpha62_dependency_verified": True})
    if not tools or not tss:
        base["reason"] = "UNKNOWN — target package manifest does not positively verify both TPM2 tooling and a TSS2 userspace stack. ChromaPress never infers TPM hardware from package names or host state."
        return base
    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": ["require_tpm_backed_recovery_key_protection"],
        "reason": "PASS — target package metadata verifies TPM2 tooling plus a TSS2 userspace stack and Alpha 62 recovery-role evidence. Only a TPM-backed key-protection policy intent may be staged; physical TPM presence, ownership, PCRs, key generation/sealing and credentials remain deferred to verified apply/runtime.",
    })
    return base

def _system_fido2_policy_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
) -> dict[str, object]:
    """Alpha 63 target-manifest FIDO2 policy capability.

    This gate verifies only installed-package evidence for a PAM/FIDO2-capable
    authentication stack plus the Alpha 62 recovery-administrator dependency.
    It does not inspect PAM contents, enumerate USB/HID authenticators, enroll a
    security key, read credential identifiers, or claim WebAuthn/YubiKey/
    platform-authenticator/TPM support. Those remain separate later gates.
    """
    base: dict[str, object] = {
        "gate_version": "alpha63",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "pam-fido2-policy-intent",
        "package_format": str(package_format or "unknown"),
        "pam_fido2_packages": [],
        "libfido2_packages": [],
        "fido2_tool_packages": [],
        "supported_operations": [],
        "policy_scope": "recovery_administrator_fido2_second_factor",
        "alpha62_dependency_verified": False,
        "pam_contents_read": False,
        "pam_contents_modified_during_analysis": False,
        "authenticator_devices_enumerated": False,
        "usb_hid_state_accessed": False,
        "credential_ids_read": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "authenticator_enrollment_performed": False,
        "webauthn_capability_claimed": False,
        "security_key_presence_claimed": False,
        "yubikey_capability_claimed": False,
        "platform_authenticator_claimed": False,
        "tpm_capability_claimed": False,
        "host_authenticator_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — FIDO2 authentication-policy capability has not been verified from target package metadata.",
    }
    allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_cap not in allowed:
        base["reason"] = "UNKNOWN — Alpha 62 administrator/recovery evidence is unavailable or malformed."
        return base
    if admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; FIDO2 policy remains fail-closed."
        return base
    protected_false = (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )
    if any(admin_recovery.get(key) is not False for key in protected_false):
        base.update({
            "capability_status": "BLOCKED",
            "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for FIDO2 policy staging.",
        })
        return base

    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    pam_pkgs: list[str] = []
    lib_pkgs: list[str] = []
    tool_pkgs: list[str] = []
    for name in sorted(versions):
        low = name.casefold()
        if low in {"libpam-u2f", "pam-u2f"} or low.startswith("libpam-u2f-"):
            pam_pkgs.append(name)
        if low in {"libfido2-1", "libfido2", "libfido2-devel", "libfido2-dev"} or low.startswith("libfido2-"):
            lib_pkgs.append(name)
        if low in {"fido2-tools", "pamu2fcfg"}:
            tool_pkgs.append(name)

    base.update({
        "pam_fido2_packages": pam_pkgs,
        "libfido2_packages": lib_pkgs,
        "fido2_tool_packages": tool_pkgs,
        "alpha62_dependency_verified": True,
    })
    if not pam_pkgs or not lib_pkgs:
        base["reason"] = (
            "UNKNOWN — target package manifest does not positively verify both a PAM FIDO2/U2F module and libfido2. "
            "ChromaPress does not infer support from distro family or host packages."
        )
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": ["require_fido2_second_factor_for_recovery_admin"],
        "reason": (
            "PASS — target package manifest positively verifies a PAM FIDO2/U2F module plus libfido2, and Alpha 62 recovery-administrator evidence is verified. "
            "Only a FIDO2 second-factor policy intent may be staged; PAM contents, physical authenticators, USB/HID state, credential identifiers/secrets and host authenticator state were not read. "
            "WebAuthn, security-key enrollment, YubiKey-specific behavior, platform authenticators and TPM remain separate later gates."
        ),
    })
    return base


def _system_webauthn_policy_evidence(
    package_format: str,
    manifest_versions: dict[str, str],
    admin_recovery: dict[str, object],
    fido2_policy: dict[str, object],
) -> dict[str, object]:
    """Alpha 64 browser-mediated WebAuthn policy capability.

    Package metadata can positively identify a supported browser product family,
    but it cannot prove runtime WebAuthn enablement, a relying party/origin, or an
    authenticator. Alpha 64 therefore stages only a browser-mediated recovery
    policy intent and keeps all runtime/authenticator claims fail-closed.
    """
    base: dict[str, object] = {
        "gate_version": "alpha64",
        "analysis_scope": "target_iso_package_manifest",
        "capability_status": "UNKNOWN",
        "verified": False,
        "backend": "browser-webauthn-policy-intent",
        "package_format": str(package_format or "unknown"),
        "browser_packages": [],
        "libfido2_packages": [],
        "supported_operations": [],
        "policy_scope": "recovery_administrator_browser_webauthn",
        "alpha62_dependency_verified": False,
        "alpha63_evidence_observed": False,
        "browser_config_contents_read": False,
        "webauthn_runtime_verified": False,
        "relying_party_config_read": False,
        "relying_party_verified": False,
        "origin_config_read": False,
        "origin_verified": False,
        "authenticator_devices_enumerated": False,
        "usb_hid_state_accessed": False,
        "credential_ids_read": False,
        "credential_secret_read": False,
        "credential_secret_staged": False,
        "authenticator_enrollment_performed": False,
        "security_key_presence_claimed": False,
        "yubikey_capability_claimed": False,
        "platform_authenticator_claimed": False,
        "tpm_capability_claimed": False,
        "host_browser_state_accessed": False,
        "host_authenticator_state_accessed": False,
        "source_read_only": True,
        "reason": "UNKNOWN — browser-mediated WebAuthn policy capability has not been verified from target package metadata.",
    }
    allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
    admin_cap = str(admin_recovery.get("capability_status") or "UNKNOWN")
    if admin_recovery.get("gate_version") != "alpha62" or admin_cap not in allowed:
        base["reason"] = "UNKNOWN — Alpha 62 administrator/recovery evidence is unavailable or malformed."
        return base
    if admin_recovery.get("verified") is not True or admin_cap not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}:
        base["reason"] = f"UNKNOWN — Alpha 62 recovery-administrator dependency is {admin_cap}; WebAuthn policy remains fail-closed."
        return base
    protected_false = (
        "shadow_read", "credential_secret_read", "recovery_secret_read", "pam_contents_read",
        "ssh_config_read", "rescue_boot_config_read", "root_account_policy_read",
        "host_accounts_touched", "host_login_state_accessed",
    )
    if any(admin_recovery.get(key) is not False for key in protected_false):
        base.update({
            "capability_status": "BLOCKED",
            "reason": "BLOCKED — Alpha 62 recovery evidence is not sufficiently secret/host isolated for WebAuthn policy staging.",
        })
        return base

    browser_names = {
        "firefox", "firefox-esr", "chromium", "chromium-browser",
        "google-chrome-stable", "microsoft-edge-stable", "brave-browser", "epiphany-browser",
    }
    versions = {str(k): str(v) for k, v in (manifest_versions or {}).items()}
    browsers = [name for name in sorted(versions) if name.casefold() in browser_names]
    libfido2 = [
        name for name in sorted(versions)
        if name.casefold() in {"libfido2", "libfido2-1", "libfido2-dev", "libfido2-devel"}
        or name.casefold().startswith("libfido2-")
    ]
    base.update({
        "browser_packages": browsers,
        "libfido2_packages": libfido2,
        "alpha62_dependency_verified": True,
        "alpha63_evidence_observed": fido2_policy.get("gate_version") == "alpha63",
    })
    if not browsers:
        base["reason"] = (
            "UNKNOWN — target package manifest does not positively identify a browser package from the Alpha 64 WebAuthn client allowlist. "
            "ChromaPress does not infer browser/WebAuthn support from distro family or host software."
        )
        return base

    base.update({
        "capability_status": "SUPPORTED_WITH_REQUIREMENTS",
        "verified": True,
        "supported_operations": ["allow_webauthn_for_recovery_web_workflows"],
        "reason": (
            "PASS — target package manifest positively identifies a browser package from the Alpha 64 WebAuthn client allowlist and Alpha 62 recovery-administrator evidence is verified. "
            "Only a browser-mediated WebAuthn recovery-policy intent may be staged. Actual browser runtime support, relying party/origin configuration, authenticator presence/enrollment, security-key/YubiKey/platform-authenticator behavior and TPM support are not claimed and require later verification."
        ),
    })
    return base


def _extract_iso_member(iso: Path, member: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["xorriso", "-indev", str(iso), "-osirrox", "on", "-extract", member, str(target)],
        text=True,
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0 or not target.exists():
        raise RuntimeError((cp.stderr or cp.stdout or f"Could not extract {member}").strip())


def _manifest_versions(iso: Path, files: list[str], work: Path) -> dict[str, str]:
    """Read available package manifests with one ISO open instead of one per file."""
    versions: dict[str, str] = {}
    candidates = (
        "/casper/filesystem.manifest",
        "/casper/minimal.standard.live.manifest",
        "/casper/minimal.standard.manifest",
        "/live/filesystem.packages",
    )
    file_set = set(files)
    selected = [member for member in candidates if member in file_set]
    if not selected:
        return versions

    args = ["xorriso", "-indev", str(iso), "-osirrox", "on"]
    targets: list[Path] = []
    for index, member in enumerate(selected):
        target = work / f"manifest-{index}.txt"
        targets.append(target)
        args += ["-extract", member, str(target)]
    cp = subprocess.run(args, text=True, capture_output=True, check=False)
    if cp.returncode != 0:
        # Version enrichment is optional in Quick view. Do not block the catalogue.
        return versions

    for target in targets:
        if not target.is_file():
            continue
        for raw in target.read_text(encoding="utf-8", errors="ignore").splitlines():
            fields = raw.split()
            if len(fields) >= 2 and not fields[0].startswith("#"):
                versions[fields[0].lstrip("+")] = fields[1]
    return versions

def _desktop_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_desktop = False
    wanted = {
        "Type", "Name", "Comment", "Icon", "Exec", "NoDisplay", "Hidden",
        "OnlyShowIn", "NotShowIn", "Categories",
    }
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_desktop = line == "[Desktop Entry]"
            continue
        if not in_desktop:
            continue
        key, sep, value = raw.partition("=")
        if sep and key in wanted and key not in fields:
            fields[key] = value.strip()
    return fields


def _manifest_package_candidates(desktop: Path, versions: dict[str, str]) -> tuple[str, str]:
    """Return an exact, conservative package match from the desktop filename.

    This is intentionally strict. It is used only to enrich the Quick catalogue
    without scanning dpkg ownership metadata. If the match is not exact, package
    removal stays unavailable until a later on-demand resolver confirms ownership.
    """
    stem = desktop.stem
    candidates = [stem]
    # Common desktop aliases such as org.foo.Bar are not package names; do not guess.
    if "_" in stem:
        candidates.append(stem.split("_", 1)[0])
    for candidate in candidates:
        if candidate in versions:
            return candidate, versions[candidate]
    return "", ""


def _iso_member_extents(iso: Path, members: list[str]) -> dict[str, tuple[int, int]]:
    """Return byte extents for requested ISO members with one xorriso load.

    xorriso's report_lba table is deliberately parsed by columns instead of a
    brittle regex. Some versions place report output on stderr, so both streams
    are considered.
    """
    if not members:
        return {}
    args = ["xorriso", "-indev", str(iso)]
    for member in members:
        args += ["-find", member, "-exec", "report_lba", "--"]
    cp = subprocess.run(args, text=True, capture_output=True, check=False)
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    if cp.returncode != 0 and "File data lba:" not in text:
        return {}
    wanted = set(members)
    rows: dict[str, list[tuple[int, int]]] = {m: [] for m in members}
    for raw in text.splitlines():
        if "File data lba:" not in raw:
            continue
        try:
            payload = raw.split("File data lba:", 1)[1].strip()
            parts = [x.strip() for x in payload.split(",", 4)]
            if len(parts) != 5:
                continue
            start_lba = int(parts[1])
            file_size = int(parts[3])
            member = parts[4].strip().strip("'\"")
        except (ValueError, IndexError):
            continue
        if member in wanted:
            rows[member].append((start_lba * 2048, file_size))
    return {member: values[0] for member, values in rows.items() if values}

def _unsquashfs_supports_offset() -> bool:
    """Detect byte-offset support across old and new squashfs-tools help modes.

    squashfs-tools 4.7+ may keep miscellaneous options such as -offset out of
    the short ``-help`` summary and expose them only through ``-help-all``.
    Treat help probing as read-only capability detection and never infer support
    from the distro/version string alone.
    """
    unsquashfs = shutil.which("unsquashfs")
    if not unsquashfs:
        return False

    for help_args in (["-help"], ["-help-all", "-no-pager"]):
        try:
            cp = subprocess.run(
                [unsquashfs, *help_args],
                text=True, capture_output=True, check=False, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (cp.stdout or "") + "\n" + (cp.stderr or "")
        if "-offset" in text or re.search(r"(?:^|\s)-o\s+(?:BYTES|<[^>]+>|OFFSET)", text, re.I | re.M):
            return True
    return False

def _extract_fast_metadata_from_layer(
    iso: Path,
    member: str,
    merged: Path,
    work: Path,
    extent: tuple[int, int] | None,
    offset_supported: bool,
) -> str:
    """Extract only user-facing application metadata from one SquashFS layer.

    Fast path: unsquashfs reads the SquashFS directly inside the ISO by byte
    offset, so no multi-GB layer copy is created. Fallback: materialize one layer
    into the explicit workspace, then extract the same small metadata set.
    """
    source = iso
    offset: int | None = None
    temporary_layer: Path | None = None

    if extent is not None and offset_supported:
        offset = extent[0]
        method = "direct-offset"
    else:
        temporary_layer = work / (Path(member).name + ".layer")
        _extract_iso_member(iso, member, temporary_layer)
        source = temporary_layer
        method = "workspace-fallback"

    try:
        common = ["unsquashfs", "-no-progress", "-no-xattrs"]
        if offset is not None:
            common += ["-offset", str(offset)]
        # Quick mode only needs desktop entries. Avoid a full SquashFS listing and
        # avoid AppStream directories until Advanced enrichment actually needs them.
        # /usr/share/applications is present on normal desktop images and is tiny.
        args = common + ["-f", "-d", str(merged), str(source), "usr/share/applications"]
        cp = subprocess.run(args, text=True, capture_output=True, check=False)
        if cp.returncode != 0:
            # Some custom images put launchers under /usr/local instead.
            args = common + ["-f", "-d", str(merged), str(source), "usr/local/share/applications"]
            cp = subprocess.run(args, text=True, capture_output=True, check=False)
        if cp.returncode != 0:
            # A layer without application metadata is valid; it may only provide
            # libraries or runtime content. Do not fail the whole catalogue.
            text = ((cp.stderr or "") + "\n" + (cp.stdout or "")).casefold()
            if "no matches" in text or "not found" in text or "no such" in text:
                return method
            raise RuntimeError((cp.stderr or cp.stdout or "unsquashfs metadata extraction failed").strip())
        return method
    finally:
        if temporary_layer is not None:
            try:
                temporary_layer.unlink()
            except OSError:
                pass


def _catalog_cache_path(cache_dir: Path, cache_key: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", cache_key).strip("-") or "unknown"
    return cache_dir / "catalog" / f"{safe}.json"


def application_catalog(
    path: Path,
    workspace: Path,
    cache_dir: Path | None = None,
    cache_key: str = "",
) -> dict:
    """Return a fast human-facing catalogue from the selected ISO only.

    The Quick path extracts only desktop/AppStream metadata. It does not scan
    thousands of dpkg ownership files. Package ownership and dependency/removal
    details are deliberately deferred until they are actually needed.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    if not workspace:
        raise RuntimeError("No explicit ChromaPress workspace is configured.")
    workspace.mkdir(parents=True, exist_ok=True)

    cache_file: Path | None = None
    if cache_dir is not None and cache_key:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = _catalog_cache_path(cache_dir, cache_key)
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached.get("schema") == 3 and cached.get("source_sha256") == cache_key:
                    cached["cache_hit"] = True
                    return cached
            except (OSError, json.JSONDecodeError):
                pass

    files = _iso_files(path)
    layers = _rootfs_layers(files)
    if not layers:
        raise RuntimeError("No supported SquashFS root filesystem was found in this image.")

    with tempfile.TemporaryDirectory(prefix="chromapress-app-catalog-", dir=workspace) as td:
        work = Path(td)
        merged = work / "metadata-root"
        merged.mkdir()
        versions = _manifest_versions(path, files, work)
        methods: list[str] = []
        # Prefer direct byte-offset reads. Modern squashfs-tools support this;
        # if a particular installation does not, the extraction helper falls
        # back safely for that layer. This avoids an extra help-process and fixes
        # xorriso-report parsing that previously forced multi-GB fallbacks.
        extents = _iso_member_extents(path, layers)

        for member in layers:
            methods.append(_extract_fast_metadata_from_layer(
                path, member, merged, work, extents.get(member), bool(extents.get(member))
            ))

        apps: list[dict[str, object]] = []
        app_dirs = [
            merged / "usr/share/applications",
            merged / "usr/local/share/applications",
        ]
        for app_dir in app_dirs:
            if not app_dir.is_dir():
                continue
            for desktop in sorted(app_dir.glob("*.desktop")):
                fields = _desktop_fields(desktop)
                if fields.get("Type", "Application") != "Application":
                    continue
                if fields.get("Hidden", "").lower() == "true" or fields.get("NoDisplay", "").lower() == "true":
                    continue
                name = fields.get("Name", "").strip()
                if not name:
                    continue
                rel = desktop.relative_to(merged).as_posix()
                package, version = _manifest_package_candidates(desktop, versions)
                apps.append({
                    "application": name,
                    "package": package,
                    "version": version,
                    "description": fields.get("Comment", "").strip(),
                    "icon": fields.get("Icon", "").strip(),
                    "categories": [x for x in fields.get("Categories", "").split(";") if x],
                    "desktop_file": "/" + rel,
                    "state": "Installed",
                    "removable": bool(package),
                    "ownership": "exact-filename" if package else "unresolved",
                })

        deduped: dict[tuple[str, str], dict[str, object]] = {}
        for app in apps:
            key = (str(app["application"]).casefold(), str(app.get("desktop_file", "")))
            previous = deduped.get(key)
            if previous is None or (not previous.get("removable") and app.get("removable")):
                deduped[key] = app
        result = sorted(deduped.values(), key=lambda x: str(x["application"]).casefold())
        payload = {
            "schema": 3,
            "source": str(path),
            "source_sha256": cache_key,
            "rootfs_layers": layers,
            "count": len(result),
            "applications": result,
            "cache_hit": False,
            "read_method": "direct-offset" if methods and all(x == "direct-offset" for x in methods) else "mixed/fallback",
        }

        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(cache_file)
        return payload

def main() -> int:
    parser = argparse.ArgumentParser(prog="chromapress-engine")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("iso", type=Path)
    c = sub.add_parser("catalog")
    c.add_argument("iso", type=Path)
    c.add_argument("--workspace", required=True, type=Path)
    c.add_argument("--cache-dir", type=Path)
    c.add_argument("--cache-key", default="")
    b = sub.add_parser("build")
    b.add_argument("plan", type=Path)
    args = parser.parse_args()
    if args.cmd == "analyze":
        print(json.dumps(analyze(args.iso), indent=2))
        return 0
    if args.cmd == "catalog":
        print(json.dumps(application_catalog(args.iso, args.workspace, args.cache_dir, args.cache_key), indent=2))
        return 0
    if args.cmd == "build":
        from chromapress.services.builder import build_iso_from_plan
        print(json.dumps(build_iso_from_plan(args.plan), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
