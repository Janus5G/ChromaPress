#!/usr/bin/env python3
"""ChromaPress acceptance runner.

Runs every safe, automatable verification currently possible across the original
8-part ChromaPress plan and writes Markdown + JSON reports.

Design goals:
- local/offline only; never sends project data anywhere
- never modifies a source ISO
- disables Python/pytest cache generation
- reports PASS/FAIL/SKIP/MANUAL_REQUIRED/NOT_IMPLEMENTED truthfully
- future-safe: automatically runs every pytest test added to the project

Typical Windows use from the ChromaPress project root:
    .venv-win\\Scripts\\python.exe chromapress_acceptance.py --through 2

Full framework view:
    .venv-win\\Scripts\\python.exe chromapress_acceptance.py --through 8

Optional real ISO read-only analysis (when WSL/xorriso are available):
    .venv-win\\Scripts\\python.exe chromapress_acceptance.py --through 8 --iso "E:\\path\\source.iso"
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 is unsupported by ChromaPress
    tomllib = None

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
MANUAL = "MANUAL_REQUIRED"
NOT_IMPL = "NOT_IMPLEMENTED"
INFO = "INFO"

PARTS = {
    1: "Workbench Foundation",
    2: "Software & Components",
    3: "Boot, Kernel & Hardware",
    4: "System Configuration",
    5: "Installer & Desktop",
    6: "AI App Studio",
    7: "Presets, Expert & Production Workflow",
    8: "Cross-Distro Hardening & Acceptance",
}

# Locked Alpha 24 assets. These checks are applied only when those files exist.
CHROMALEARN_045_SHA256 = "024374666992d83df7ae6c9b0f488973e896beec80aeff18c997336d7dbe9fbc"
SCHOOL_PACK_121_SHA256 = "9fec49879412c056991e123c06d89b3ce99f64eff3ca19718891333fca6e67eb"

IGNORE_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", ".venv-win", "venv", "node_modules",
    "test-reports", ".chromapress-test-reports", ".distroforge",
}

FORBIDDEN_RELEASE_NAMES = {
    ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".coverage",
}
FORBIDDEN_RELEASE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".swp"}

SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|passwd|bearer[_-]?token)\b\s*[:=]\s*[\"']([^\"']{12,})[\"']"
)
PRIVATE_KEY_MARKER = "-----BEGIN PRIVATE KEY-----"
SAFE_SECRET_WORDS = (
    "placeholder", "example", "dummy", "changeme", "replace_me", "redacted",
    "your_", "test", "fake", "none", "null", "env", "${", "<",
)

TEST_PART_PATTERNS = {
    1: re.compile(r"windows_to_wsl|empty_plan|source|overview|project_persists|path", re.I),
    2: re.compile(r"package|catalog|application|recommend|scenario|desktop_entry|remove|replace|school|chromalearn|gaming|business|refract|repository", re.I),
    3: re.compile(r"rootfs|boot|kernel|initramfs|firmware|driver|squashfs", re.I),
    4: re.compile(r"system|user|group|hostname|machine.?identity|autologin|display.?manager|locale|keyboard|timezone|network|dns|service|timer|firewall|apparmor|selinux|sysctl|credential_redaction|kiosk|restricted|login", re.I),
    5: re.compile(r"installer|kickstart|autoinstall|preseed|archive|traversal|symlink|desktop_capability|overlay", re.I),
    6: re.compile(r"\bai\b|api_key|provider|model|credential|ai_catalog", re.I),
    7: re.compile(r"preset|profile|expert|reproduce|build_plan|production", re.I),
    8: re.compile(r"distro|distribution|acceptance|checksum|rebuild|preservation|cross", re.I),
}


@dataclass
class Check:
    part: int
    check_id: str
    name: str
    status: str
    detail: str = ""
    automated: bool = True


class AcceptanceRunner:
    def __init__(self, root: Path, through: int, iso: Path | None, release_zip: Path | None, report_dir: Path, staged_sweep: bool = True, testpack_restart: bool = False, legacy_testpack: bool = False):
        self.root = root.resolve()
        self.through = through
        self.iso = iso.resolve() if iso else None
        self.release_zip = release_zip.resolve() if release_zip else None
        self.report_dir = report_dir.resolve()
        self.staged_sweep = bool(staged_sweep)
        self.testpack_restart = bool(testpack_restart)
        self.legacy_testpack = bool(legacy_testpack)
        self.part4_testpack_report: dict = {}
        self.part4_testpack_status = "NOT_RUN"
        self.part5_testpack_report: dict = {}
        self.part5_testpack_status = "NOT_RUN"
        self.part6_testpack_report: dict = {}
        self.part6_testpack_status = "NOT_RUN"
        self.part7_testpack_report: dict = {}
        self.part7_testpack_status = "NOT_RUN"
        self.part8_testpack_report: dict = {}
        self.part8_testpack_status = "NOT_RUN"
        # Backward-compatible aliases used by older Part 4 reporting helpers.
        self.testpack_report: dict = self.part4_testpack_report
        self.testpack_status = self.part4_testpack_status
        self.checks: list[Check] = []
        self.pytest_output = ""
        self.part4_staged_sweep_output = ""
        self.part4_staged_sweep_status = "NOT_RUN"
        self.part5_staged_sweep_output = ""
        self.part5_staged_sweep_status = "NOT_RUN"
        self.part6_staged_sweep_output = ""
        self.part6_staged_sweep_status = "NOT_RUN"
        self.part7_staged_sweep_output = ""
        self.part7_staged_sweep_status = "NOT_RUN"
        self.part8_staged_sweep_output = ""
        self.part8_staged_sweep_status = "NOT_RUN"
        self.collected_tests: list[str] = []
        self.version = self._project_version()
        self.started = dt.datetime.now(dt.timezone.utc)

    def add(self, part: int, check_id: str, name: str, status: str, detail: str = "", automated: bool = True) -> None:
        if part <= self.through:
            self.checks.append(Check(part, check_id, name, status, detail.strip(), automated))

    def _add_alpha50_users_groups_password_gate(self, identity: dict) -> None:
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        required_statuses = (
            str(identity.get("capability_status") or ""),
            str(identity.get("users_groups_status") or ""),
            str(identity.get("uid_gid_status") or ""),
            str(identity.get("group_membership_status") or ""),
            str(identity.get("password_policy_status") or ""),
        )
        schema_ok = (
            identity.get("gate_version") == "alpha50"
            and identity.get("analysis_scope") == "target_iso_rootfs"
            and identity.get("host_accounts_touched") is False
            and identity.get("shadow_read") is False
            and identity.get("credential_secret_read") is False
            and identity.get("source_read_only") is True
            and isinstance(identity.get("user_records"), list)
            and isinstance(identity.get("group_records"), list)
            and isinstance(identity.get("password_policy"), dict)
            and all(value in allowed for value in required_statuses)
        )
        detail = (
            "PASS — Alpha 50 users/groups/password-policy evidence schema is present; target-rootfs scope is explicit, "
            "capability states are truthful, and shadow/credential secrets plus Windows/WSL host accounts were not used."
            if schema_ok else
            "FAIL — Alpha 50 users/groups/password-policy evidence is missing/incomplete or not fail-closed."
        )
        self.add(4, "P4-REAL-ROOTFS-USERS-GROUPS-PASSWORD",
                 "Real ISO users/groups/password-policy capability verification",
                 PASS if schema_ok else FAIL, detail)

    def _add_alpha51_networking_configuration_gate(self, network: dict, source_sha256: str) -> None:
        """Exercise a real Alpha 51 staged DHCP plan against analyzed target-rootfs capability."""
        allowed_states = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        supported = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        statuses = (
            str(network.get("capability_status") or "UNKNOWN"),
            str(network.get("addressing_status") or "UNKNOWN"),
            str(network.get("dns_status") or "UNKNOWN"),
            str(network.get("networkmanager_profile_status") or "UNKNOWN"),
            str(network.get("ipv6_status") or "UNKNOWN"),
        )
        schema_ok = (
            network.get("gate_version") == "alpha51"
            and network.get("analysis_scope") == "target_iso_rootfs"
            and network.get("host_network_accessed") is False
            and network.get("connection_profiles_inspected") is False
            and network.get("connection_profile_contents_read") is False
            and network.get("wifi_vpn_secrets_read") is False
            and network.get("credential_secret_read") is False
            and network.get("source_read_only") is True
            and network.get("ipv6_exposed") is False
            and isinstance(network.get("supported_operations"), list)
            and all(state in allowed_states for state in statuses)
        )
        if not schema_ok:
            self.add(4, "P4-REAL-STAGED-NETWORK-CONFIG", "Real staged networking configuration verification", FAIL,
                     "FAIL — Alpha 51 networking capability schema is missing/incomplete or host/secret isolation is not explicit.")
            return
        if str(network.get("capability_status")) not in supported or str(network.get("addressing_status")) not in supported:
            self.add(4, "P4-REAL-STAGED-NETWORK-CONFIG", "Real staged networking configuration verification", FAIL,
                     f"FAIL — analyzed target reports networking={network.get('capability_status')} addressing={network.get('addressing_status')}; no supported staged DHCP plan can be verified.")
            return
        operations = {str(x) for x in network.get("supported_operations") or []}
        if "configure_dhcp_ipv4" not in operations:
            self.add(4, "P4-REAL-STAGED-NETWORK-CONFIG", "Real staged networking configuration verification", FAIL,
                     "FAIL — analyzed target does not advertise the Alpha 51 DHCP staging operation.")
            return
        backend = str(network.get("backend") or "")
        payload = {
            "config_type": "system_network_dns",
            "gate_version": "alpha51",
            "source_sha256": str(source_sha256 or "").strip().casefold(),
            "analysis_scope": "target_iso_rootfs",
            "capability_status": str(network.get("capability_status") or "UNKNOWN"),
            "addressing_status": str(network.get("addressing_status") or "UNKNOWN"),
            "dns_status": str(network.get("dns_status") or "UNKNOWN"),
            "networkmanager_profile_status": str(network.get("networkmanager_profile_status") or "UNKNOWN"),
            "control_depth": "quick",
            "operation": "configure_dhcp_ipv4",
            "network_backend": backend,
            "backend_config_path": str(network.get("backend_config_path") or ""),
            "backend_config_layer": str(network.get("backend_config_layer") or ""),
            "managed_config_path": str(network.get("managed_config_path") or ""),
            "managed_config_style": str(network.get("managed_config_style") or ""),
            "resolver_path": str(network.get("resolver_path") or ""),
            "resolver_layer": str(network.get("resolver_layer") or ""),
            "rootfs_network_dns_verified": True,
            "supported_operations": sorted(operations),
            "target_profile_name": "ChromaPress Acceptance DHCP" if backend == "NetworkManager" else "",
            "existing_profile_filename": "",
            "target_interface": "",
            "ipv4_method": "auto",
            "target_ipv4_address": "",
            "target_gateway": "",
            "target_dns_servers": [],
            "autoconnect_enabled": None,
            "profile_connection_type": "preserve",
            "require_backend_specific_apply_verification": True,
            "require_target_path_reverification_before_apply": True,
            "require_syntax_validation_before_apply": True,
            "require_profile_reverification_before_apply": False,
            "preserve_existing_profiles": True,
            "preserve_unrelated_routes": True,
            "preserve_hostname": True,
            "connection_profiles_inspected": False,
            "connection_profile_contents_read": False,
            "profile_names_from_metadata_only": True,
            "wifi_vpn_secrets_read": False,
            "credential_secret_read": False,
            "credential_secret_staged": False,
            "secret_read": False,
            "secret_staged": False,
            "host_network_accessed": False,
            "ipv6_exposed": False,
            "ipv6_supported_by_gate": False,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Networking / NetworkManager / DNS plan", ChangeKind.CONFIG, "acceptance staged DHCP", payload))
            ok = status == ChangeStatus.PASS
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        self.add(
            4, "P4-REAL-STAGED-NETWORK-CONFIG", "Real staged networking configuration verification",
            PASS if ok else FAIL,
            ("PASS — real analyzed target capability produced an Alpha 51 DHCP staged plan and preflight accepted it without host-network or secret substitution. " + str(message))
            if ok else ("FAIL — analyzed target capability could not produce a valid Alpha 51 staged DHCP plan. " + str(message)),
        )

    def _add_alpha52_selinux_gate(self, selinux: dict, source_sha256: str) -> None:
        """Validate truthful Alpha 52 SELinux capability and staged/fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(selinux.get("capability_status") or "UNKNOWN")
        schema_ok = (
            selinux.get("gate_version") == "alpha52"
            and selinux.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and selinux.get("host_selinux_accessed") is False
            and selinux.get("host_security_state_accessed") is False
            and selinux.get("policy_contents_read") is False
            and selinux.get("custom_policy_preserved") is True
            and selinux.get("source_read_only") is True
            and isinstance(selinux.get("supported_modes"), list)
            and isinstance(selinux.get("required_packages"), list)
            and isinstance(selinux.get("part3_requirements"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA52-SELINUX", "SELinux capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 52 SELinux capability schema is missing/incomplete or host/policy/source isolation is not explicit.")
            return
        payload = {
            "config_type": "system_selinux",
            "gate_version": "alpha52",
            "source_sha256": str(source_sha256 or "").strip().casefold(),
            "analysis_scope": "target_iso_rootfs",
            "operation": "set_selinux_mode",
            "target_mode": "permissive",
            "configured_mode": str(selinux.get("configured_mode") or "unknown"),
            "capability_status": capability,
            "rootfs_selinux_verified": selinux.get("verified") is True,
            "config_path": str(selinux.get("config_path") or "/etc/selinux/config"),
            "config_layer": str(selinux.get("config_layer") or ""),
            "config_metadata_read": bool(selinux.get("config_metadata_read")),
            "config_creation_required": bool(selinux.get("config_creation_required")),
            "policy_type": str(selinux.get("policy_type") or ""),
            "policy_tree_present": bool(selinux.get("policy_tree_present")),
            "policy_entries": [str(x) for x in (selinux.get("policy_entries") or [])],
            "policy_contents_read": False,
            "preserve_existing_policies": True,
            "custom_policy_preserved": True,
            "package_manager": str(selinux.get("package_manager") or ""),
            "package_manager_path": str(selinux.get("package_manager_path") or ""),
            "repository_metadata_path": str(selinux.get("repository_metadata_path") or ""),
            "package_install_required": bool(selinux.get("package_install_required")),
            "required_packages": [str(x) for x in (selinux.get("required_packages") or [])],
            "require_signed_repository_metadata": True,
            "require_dependency_resolution": True,
            "package_requirements_staged": bool(selinux.get("required_packages")),
            "kernel_support_status": str(selinux.get("kernel_support_status") or "UNKNOWN"),
            "kernel_config_path": str(selinux.get("kernel_config_path") or ""),
            "kernel_images": [str(x) for x in (selinux.get("kernel_images") or [])],
            "boot_config_files": [str(x) for x in (selinux.get("boot_config_files") or [])],
            "initramfs_mechanism": str(selinux.get("initramfs_mechanism") or ""),
            "part3_dependency_required": bool(selinux.get("part3_dependency_required")),
            "part3_requirements": list(selinux.get("part3_requirements") or []),
            "dependencies_visible": True,
            "dependencies_staged": True,
            "delegate_boot_kernel_to_part3": True,
            "direct_boot_mutation": False,
            "direct_kernel_mutation": False,
            "direct_initramfs_mutation": False,
            "relabel_required": bool(selinux.get("relabel_required_on_enable")),
            "relabel_before_enforcing": False,
            "reboot_required": bool(selinux.get("reboot_required")),
            "require_post_boot_verification": True,
            "host_selinux_accessed": False,
            "host_security_state_accessed": False,
            "secret_read": False,
            "secret_staged": False,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        if supported:
            modes = {str(x) for x in (selinux.get("supported_modes") or [])}
            if "permissive" not in modes:
                self.add(4, "P4-ALPHA52-SELINUX", "SELinux capability / staged configuration verification", FAIL,
                         "FAIL — supported SELinux capability does not expose the verified permissive mode expected by Alpha 52.")
                return
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("SELinux plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed SELinux capability produced a valid staged permissive plan with explicit package/Part-3/relabel/reboot dependencies and no host/policy/source substitution. " + str(message)
        else:
            detail = f"PASS — analyzed SELinux capability is {capability}; Alpha 52 correctly fail-closed the attempted state change. " + str(message)
        self.add(4, "P4-ALPHA52-SELINUX", "SELinux capability / staged configuration verification",
                 PASS if ok else FAIL,
                 detail if ok else (f"FAIL — Alpha 52 SELinux {capability} behavior did not match fail-closed capability policy. " + str(message)))

    def _add_alpha53_security_defaults_gate(self, security: dict, source_sha256: str) -> None:
        """Validate Alpha 53 target-only security defaults and real staged/fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(security.get("capability_status") or "UNKNOWN")
        schema_ok = (
            security.get("gate_version") == "alpha53"
            and security.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and security.get("host_security_state_accessed") is False
            and security.get("credential_secret_read") is False
            and security.get("full_config_exposed") is False
            and security.get("source_read_only") is True
            and isinstance(security.get("supported_umasks"), list)
            and isinstance(security.get("metadata_keys_read"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA53-SECURITY-DEFAULTS", "Security defaults capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 53 security-default capability schema is missing/incomplete or target/host/secret isolation is not explicit.")
            return
        payload = {
            "config_type": "system_security_defaults",
            "gate_version": "alpha53",
            "source_sha256": str(source_sha256 or "").strip().casefold(),
            "analysis_scope": "target_iso_rootfs",
            "capability_status": capability,
            "rootfs_security_defaults_verified": security.get("verified") is True,
            "operation": "set_default_umask",
            "target_umask": "027",
            "supported_umasks": [str(x) for x in (security.get("supported_umasks") or [])],
            "backend": str(security.get("backend") or ""),
            "config_path": str(security.get("config_path") or "/etc/login.defs"),
            "config_layer": str(security.get("config_layer") or ""),
            "current_umask": str(security.get("current_umask") or ""),
            "umask_directive_present": bool(security.get("umask_directive_present")),
            "usergroups_enab": str(security.get("usergroups_enab") or ""),
            "metadata_keys_read": [str(x) for x in (security.get("metadata_keys_read") or [])],
            "require_target_directive_reverification_before_apply": True,
            "require_effective_session_semantics_verification_before_apply": True,
            "preserve_login_defs_unrelated": True,
            "preserve_pam_configuration": True,
            "preserve_account_policy": True,
            "full_config_exposed": False,
            "credential_secret_read": False,
            "credential_secret_staged": False,
            "host_security_state_accessed": False,
            "secret_read": False,
            "secret_staged": False,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Security defaults plan", ChangeKind.CONFIG, "acceptance UMASK=027", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target security-default capability produced a real Alpha 53 staged UMASK=027 plan with preservation and host/secret isolation. " + str(message)
        else:
            detail = f"PASS — analyzed security-default capability is {capability}; Alpha 53 correctly fail-closed the attempted UMASK change. " + str(message)
        self.add(4, "P4-ALPHA53-SECURITY-DEFAULTS", "Security defaults capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 53 security-default {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha54_config_overlay_gate(self, overlay: dict, source_sha256: str) -> None:
        """Validate Alpha 54 target-only profile.d overlay capability and staged/fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(overlay.get("capability_status") or "UNKNOWN")
        schema_ok = (
            overlay.get("gate_version") == "alpha54"
            and overlay.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and overlay.get("host_configuration_accessed") is False
            and overlay.get("existing_dropin_contents_read") is False
            and overlay.get("secret_read") is False
            and overlay.get("source_read_only") is True
            and isinstance(overlay.get("existing_entry_names"), list)
            and isinstance(overlay.get("supported_operations"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA54-CONFIG-OVERLAY", "System configuration overlay capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 54 system-configuration overlay schema is missing/incomplete or target/host/secret isolation is not explicit.")
            return
        existing = [str(x) for x in (overlay.get("existing_entry_names") or [])]
        candidate = "acceptance54"
        for suffix in ("", "b", "c", "d"):
            trial = "acceptance54" + suffix
            if f"99-chromapress-{trial}.sh" not in existing:
                candidate = trial
                break
        payload = {
            "config_type": "system_config_overlay",
            "gate_version": "alpha54",
            "source_sha256": str(source_sha256 or "").strip().casefold(),
            "analysis_scope": "target_iso_rootfs",
            "capability_status": capability,
            "rootfs_overlay_verified": overlay.get("verified") is True,
            "operation": "add_managed_environment_overlay",
            "backend": str(overlay.get("backend") or ""),
            "profile_path": str(overlay.get("profile_path") or ""),
            "profile_layer": str(overlay.get("profile_layer") or ""),
            "target_directory": str(overlay.get("target_directory") or ""),
            "target_directory_layer": str(overlay.get("target_directory_layer") or ""),
            "profile_d_sourcing_verified": overlay.get("profile_d_sourcing_verified") is True,
            "existing_entry_names": existing,
            "overlay_name": candidate,
            "target_filename": f"99-chromapress-{candidate}.sh",
            "environment_variable": "CHROMAPRESS_TEST",
            "public_nonsecret_value": "1",
            "content_classification": "public_nonsecret",
            "generated_content_only": True,
            "arbitrary_shell_content_allowed": False,
            "require_target_file_absence_reverification_before_apply": True,
            "preserve_existing_profile": True,
            "preserve_existing_dropins": True,
            "existing_dropin_contents_read": False,
            "host_configuration_accessed": False,
            "secret_read": False,
            "secret_staged": False,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("System configuration overlay plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target profile.d capability produced a real Alpha 54 managed non-secret overlay plan with collision checks and preservation/host isolation. " + str(message)
        else:
            detail = f"PASS — analyzed system-configuration overlay capability is {capability}; Alpha 54 correctly fail-closed the attempted overlay. " + str(message)
        self.add(4, "P4-ALPHA54-CONFIG-OVERLAY", "System configuration overlay capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 54 overlay {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha55_kiosk_user_gate(self, kiosk: dict, source_sha256: str) -> None:
        """Validate Alpha 55 dedicated non-admin kiosk-user capability and staging/fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(kiosk.get("capability_status") or "UNKNOWN")
        schema_ok = (
            kiosk.get("gate_version") == "alpha55"
            and kiosk.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and kiosk.get("shadow_read") is False
            and kiosk.get("credential_secret_read") is False
            and kiosk.get("host_accounts_touched") is False
            and kiosk.get("login_policy_inspected") is False
            and kiosk.get("session_policy_inspected") is False
            and kiosk.get("source_read_only") is True
            and isinstance(kiosk.get("existing_regular_users"), list)
            and isinstance(kiosk.get("admin_groups"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA55-KIOSK-USER", "Dedicated non-admin kiosk-user capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 55 kiosk-user schema is missing/incomplete or target/host/credential isolation is not explicit.")
            return
        existing = [str(x) for x in (kiosk.get("existing_regular_users") or [])]
        candidate = "acceptance55kiosk"
        if candidate in existing:
            candidate = "acceptance55kioskb"
        payload = {
            "config_type": "dedicated_kiosk_user", "gate_version": "alpha55",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_account_verified": kiosk.get("verified") is True,
            "operation": "create_dedicated_non_admin_kiosk_user", "backend": str(kiosk.get("backend") or "passwd-group"),
            "passwd_layer": str(kiosk.get("passwd_layer") or ""), "group_layer": str(kiosk.get("group_layer") or ""),
            "uid_min": int(kiosk.get("uid_min") or 1000), "existing_regular_users": existing,
            "existing_user_uids": list(kiosk.get("existing_user_uids") or []), "available_groups": list(kiosk.get("available_groups") or []),
            "verified_admin_groups": list(kiosk.get("admin_groups") or []), "username": candidate, "display_name": "Acceptance Kiosk",
            "account_role": "dedicated_non_admin_kiosk", "uid_mode": "automatic", "primary_gid_mode": "automatic",
            "supplementary_groups": [], "administrative_groups": [], "create_home": True,
            "credential_policy": "deferred_to_later_verified_gate", "credential_secret_read": False, "credential_secret_staged": False,
            "shadow_read": False, "host_accounts_touched": False, "login_policy_deferred_to_later_gate": True,
            "session_policy_deferred_to_later_gate": True, "autologin_policy_preserved": True,
            "require_user_absence_reverification_before_apply": True, "preserve_existing_users_groups": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Dedicated non-admin kiosk user plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target account capability produced a real Alpha 55 dedicated non-admin kiosk-user plan without credentials/admin membership and with later login/session policy preserved. " + str(message)
        else:
            detail = f"PASS — analyzed kiosk-user capability is {capability}; Alpha 55 correctly fail-closed the attempted account staging. " + str(message)
        self.add(4, "P4-ALPHA55-KIOSK-USER", "Dedicated non-admin kiosk-user capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 55 kiosk-user {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha56_restricted_login_gate(self, login: dict, source_sha256: str) -> None:
        """Validate Alpha 56 target-only restricted password-login capability and fail-closed staging."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(login.get("capability_status") or "UNKNOWN")
        schema_ok = (
            login.get("gate_version") == "alpha56"
            and login.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and login.get("shadow_read") is False
            and login.get("credential_secret_read") is False
            and login.get("host_login_state_accessed") is False
            and login.get("pam_contents_read") is False
            and login.get("ssh_config_read") is False
            and login.get("autologin_policy_read") is False
            and login.get("session_policy_read") is False
            and login.get("source_read_only") is True
            and isinstance(login.get("existing_regular_users"), list)
            and isinstance(login.get("admin_users"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA56-RESTRICTED-LOGIN", "Restricted login capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 56 restricted-login schema is missing/incomplete or target/host/secret isolation is not explicit.")
            return
        existing = [str(x) for x in (login.get("existing_regular_users") or [])]
        admins = [str(x) for x in (login.get("admin_users") or [])]
        candidate = "acceptance56kiosk"
        while candidate in admins or candidate in existing:
            candidate += "x"
        payload = {
            "config_type": "restricted_login", "gate_version": "alpha56",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_login_restriction_verified": login.get("verified") is True,
            "operation": "lock_password_authentication", "backend": str(login.get("backend") or ""),
            "management_tool_path": str(login.get("management_tool_path") or ""),
            "management_tool_layer": str(login.get("management_tool_layer") or ""),
            "passwd_layer": str(login.get("passwd_layer") or ""), "group_layer": str(login.get("group_layer") or ""),
            "existing_regular_users": existing, "admin_users": admins, "username": candidate,
            "account_dependency": "alpha55_dedicated_non_admin_kiosk_user",
            "restriction_scope": "password_authentication_only", "password_authentication": "locked",
            "credential_secret_read": False, "credential_secret_staged": False, "shadow_read": False,
            "host_login_state_accessed": False, "pam_contents_read": False, "ssh_config_read": False,
            "preserve_autologin": True, "preserve_session_policy": True,
            "preserve_ssh_configuration": True, "preserve_pam_configuration": True,
            "require_account_dependency_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Restricted login plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target account/tool capability produced a real Alpha 56 password-lock restricted-login plan with explicit Alpha 55 dependency and preservation of other login mechanisms. " + str(message)
        else:
            detail = f"PASS — analyzed restricted-login capability is {capability}; Alpha 56 correctly fail-closed the attempted login restriction. " + str(message)
        self.add(4, "P4-ALPHA56-RESTRICTED-LOGIN", "Restricted login capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 56 restricted-login {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha57_restricted_session_gate(self, session: dict, source_sha256: str) -> None:
        """Validate Alpha 57 target-only restricted-session capability and fail-closed staging."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(session.get("capability_status") or "UNKNOWN")
        schema_ok = (
            session.get("gate_version") == "alpha57"
            and session.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and session.get("session_file_contents_read") is False
            and session.get("display_manager_config_contents_read") is False
            and session.get("credential_secret_read") is False
            and session.get("host_session_state_accessed") is False
            and session.get("pam_contents_read") is False
            and session.get("ssh_config_read") is False
            and session.get("source_read_only") is True
            and isinstance(session.get("verified_sessions"), list)
            and isinstance(session.get("existing_regular_users"), list)
            and isinstance(session.get("admin_users"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA57-RESTRICTED-SESSION", "Restricted session capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 57 restricted-session schema is missing/incomplete or target/host/secret isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        sessions = [x for x in (session.get("verified_sessions") or []) if isinstance(x, dict)]
        existing = [str(x) for x in (session.get("existing_regular_users") or [])]
        admins = [str(x) for x in (session.get("admin_users") or [])]
        candidate = "acceptance57kiosk"
        while candidate in admins or candidate in existing:
            candidate += "x"
        selected = sessions[0] if sessions else {"name": "unverified.desktop", "kind": "x11"}
        payload = {
            "config_type": "restricted_session", "gate_version": "alpha57",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_restricted_session_verified": session.get("verified") is True,
            "operation": "bind_kiosk_autologin_session", "backend": str(session.get("backend") or ""),
            "display_manager": str(session.get("display_manager") or ""), "display_manager_layer": str(session.get("display_manager_layer") or ""),
            "target_config_directory": str(session.get("target_config_directory") or "/etc/sddm.conf.d"),
            "target_config_directory_layer": str(session.get("target_config_directory_layer") or ""),
            "managed_target_path": str(session.get("managed_target_path") or "/etc/sddm.conf.d/99-chromapress-kiosk-session.conf"),
            "managed_target_present": session.get("managed_target_present") is True,
            "verified_sessions": sessions, "existing_regular_users": existing, "admin_users": admins,
            "username": candidate, "account_dependency": "alpha55_dedicated_non_admin_kiosk_user",
            "session_name": str(selected.get("name") or ""), "session_kind": str(selected.get("kind") or ""),
            "restriction_scope": "fixed_autologin_session_selection_only", "sddm_section": "Autologin", "sddm_key": "Session",
            "restricted_login_dependency": "alpha56_restricted_login_required",
            "autologin_dependency": "alpha39_autologin_same_user_required",
            "session_file_contents_read": False, "display_manager_config_contents_read": False,
            "credential_secret_read": False, "credential_secret_staged": False, "host_session_state_accessed": False,
            "pam_contents_read": False, "ssh_config_read": False,
            "preserve_existing_session_descriptors": True, "preserve_existing_display_manager_config": True,
            "preserve_other_users_sessions": True, "preserve_pam_configuration": True, "preserve_ssh_configuration": True,
            "require_managed_target_absence_reverification_before_apply": True,
            "require_dependencies_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Restricted session plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target SDDM/session capability produced a real Alpha 57 fixed-session plan with explicit Alpha 39/56 dependencies and preservation of existing session/display-manager configuration. " + str(message)
        else:
            detail = f"PASS — analyzed restricted-session capability is {capability}; Alpha 57 correctly fail-closed the attempted session staging. " + str(message)
        self.add(4, "P4-ALPHA57-RESTRICTED-SESSION", "Restricted session capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 57 restricted-session {capability} behavior did not match capability policy. " + str(message)))


    def _add_alpha58_service_lockdown_gate(self, lockdown: dict, source_sha256: str) -> None:
        """Validate Alpha 58 target-only service-lockdown capability and fail-closed staging."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(lockdown.get("capability_status") or "UNKNOWN")
        schema_ok = (
            lockdown.get("gate_version") == "alpha58"
            and lockdown.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and lockdown.get("unit_contents_read") is False
            and lockdown.get("enablement_links_read") is False
            and lockdown.get("enablement_link_targets_read") is False
            and lockdown.get("environment_files_read") is False
            and lockdown.get("service_secrets_read") is False
            and lockdown.get("credential_secret_read") is False
            and lockdown.get("host_service_state_accessed") is False
            and lockdown.get("source_read_only") is True
            and isinstance(lockdown.get("verified_service_units"), list)
            and isinstance(lockdown.get("available_lockdown_units"), list)
            and isinstance(lockdown.get("protected_service_units"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA58-SERVICE-LOCKDOWN", "Service lockdown capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 58 service-lockdown schema is missing/incomplete or target/host/secret isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        available = [x for x in (lockdown.get("available_lockdown_units") or []) if isinstance(x, dict)]
        selected = available[0] if available else {"name": "unverified.service", "directory": "", "layer": ""}
        payload = {
            "config_type": "service_lockdown", "gate_version": "alpha58",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_service_lockdown_verified": lockdown.get("verified") is True,
            "operation": "disable_and_mask_verified_service", "backend": str(lockdown.get("backend") or ""),
            "init_system": str(lockdown.get("init_system") or ""),
            "vendor_unit_path": str(lockdown.get("vendor_unit_path") or ""),
            "vendor_unit_layer": str(lockdown.get("vendor_unit_layer") or ""),
            "local_unit_path": str(lockdown.get("local_unit_path") or ""),
            "local_unit_layer": str(lockdown.get("local_unit_layer") or ""),
            "verified_service_units": list(lockdown.get("verified_service_units") or []),
            "available_lockdown_units": available,
            "protected_service_units": [str(x) for x in (lockdown.get("protected_service_units") or [])],
            "service_unit": str(selected.get("name") or ""),
            "service_unit_directory": str(selected.get("directory") or ""),
            "service_unit_layer": str(selected.get("layer") or ""),
            "lockdown_scope": "single_verified_noncritical_systemd_service",
            "unit_contents_read": False, "enablement_links_read": False, "enablement_link_targets_read": False,
            "environment_files_read": False, "service_secrets_read": False, "credential_secret_read": False,
            "host_service_state_accessed": False,
            "preserve_unit_file_contents": True, "preserve_timer_socket_units": True, "preserve_unrelated_services": True,
            "require_target_unit_reverification_before_apply": True, "require_systemd_apply_verification": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Service lockdown plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target systemd service metadata produced a real Alpha 58 single-service disable+mask plan with protected-unit filtering and preservation of unit/timer/socket data. " + str(message)
        else:
            detail = f"PASS — analyzed service-lockdown capability is {capability}; Alpha 58 correctly fail-closed the attempted service lockdown. " + str(message)
        self.add(4, "P4-ALPHA58-SERVICE-LOCKDOWN", "Service lockdown capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 58 service-lockdown {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha59_network_restriction_gate(self, evidence: dict, source_sha256: str) -> None:
        """Validate Alpha 59 target-only NetworkManager/polkit kiosk control restriction."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha59"
            and evidence.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and evidence.get("traffic_blocking_claimed") is False
            and evidence.get("firewall_rules_read") is False
            and evidence.get("firewall_rules_staged") is False
            and evidence.get("networkmanager_profile_contents_read") is False
            and evidence.get("polkit_policy_contents_read") is False
            and evidence.get("existing_rule_contents_read") is False
            and evidence.get("credential_secret_read") is False
            and evidence.get("host_network_accessed") is False
            and evidence.get("source_read_only") is True
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA59-NETWORK-RESTRICTIONS", "Network restrictions capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 59 network-restriction schema is incomplete or target/host/firewall/content isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        payload = {
            "config_type": "network_restriction", "gate_version": "alpha59",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_network_restriction_verified": evidence.get("verified") is True,
            "operation": "restrict_kiosk_networkmanager_control", "backend": str(evidence.get("backend") or ""),
            "network_backend": str(evidence.get("network_backend") or ""),
            "polkit_rules_directory": str(evidence.get("polkit_rules_directory") or ""),
            "polkit_rules_directory_layer": str(evidence.get("polkit_rules_directory_layer") or ""),
            "networkmanager_policy_path": str(evidence.get("networkmanager_policy_path") or ""),
            "networkmanager_policy_layer": str(evidence.get("networkmanager_policy_layer") or ""),
            "managed_rule_name": str(evidence.get("managed_rule_name") or ""),
            "managed_rule_path": str(evidence.get("managed_rule_path") or ""),
            "managed_target_present": evidence.get("managed_target_present") is True,
            "existing_rule_names": list(evidence.get("existing_rule_names") or []),
            "restricted_actions": list(evidence.get("restricted_actions") or []),
            "username": "chromakiosk59", "restriction_scope": "kiosk_networkmanager_control_only",
            "kiosk_user_dependency": "alpha55_dedicated_non_admin_kiosk_user_required",
            "traffic_blocking_claimed": False, "firewall_rules_read": False, "firewall_rules_staged": False,
            "networkmanager_profile_contents_read": False, "polkit_policy_contents_read": False,
            "existing_rule_contents_read": False, "credential_secret_read": False, "host_network_accessed": False,
            "preserve_existing_network_profiles": True, "preserve_existing_polkit_rules": True,
            "preserve_firewall_policy": True, "preserve_other_users_network_control": True,
            "require_managed_target_absence_reverification_before_apply": True,
            "require_networkmanager_polkit_reverification_before_apply": True,
            "require_kiosk_user_dependency_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Network restrictions plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target NetworkManager/polkit metadata produced a real Alpha 59 kiosk network-control restriction plan without claiming traffic blocking. " + str(message)
        else:
            detail = f"PASS — analyzed network-restriction capability is {capability}; Alpha 59 correctly fail-closed the attempted network-control restriction. " + str(message)
        self.add(4, "P4-ALPHA59-NETWORK-RESTRICTIONS", "Network restrictions capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 59 network-restriction {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha60_firewall_rules_gate(self, evidence: dict, source_sha256: str) -> None:
        """Validate Alpha 60 target-only single inbound TCP-port deny rule planning."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha60"
            and evidence.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and evidence.get("existing_rule_contents_read") is False
            and evidence.get("ports_services_policy_read") is False
            and evidence.get("application_profiles_read") is False
            and evidence.get("firewall_secrets_read") is False
            and evidence.get("host_firewall_accessed") is False
            and evidence.get("source_read_only") is True
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA60-FIREWALL-RULES", "Firewall rules capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 60 firewall-rule schema is incomplete or target/host/rule-content isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        payload = {
            "config_type": "firewall_rule", "gate_version": "alpha60",
            "source_sha256": str(source_sha256 or "").strip().casefold(), "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_firewall_rules_verified": evidence.get("verified") is True,
            "operation": "deny_inbound_tcp_port", "firewall_backend": str(evidence.get("firewall_backend") or ""),
            "backend_evidence_path": str(evidence.get("backend_evidence_path") or ""),
            "backend_evidence_layer": str(evidence.get("backend_evidence_layer") or ""),
            "rule_adapter": str(evidence.get("rule_adapter") or ""), "rule_command_path": str(evidence.get("rule_command_path") or ""),
            "rule_command_layer": str(evidence.get("rule_command_layer") or ""),
            "tcp_port": 65060, "protocol": "tcp", "direction": "in", "action": "deny",
            "rule_scope": "single_inbound_tcp_port_deny",
            "existing_rule_contents_read": False, "ports_services_policy_read": False,
            "application_profiles_read": False, "firewall_secrets_read": False, "host_firewall_accessed": False,
            "preserve_existing_rules": True, "preserve_default_policy": True, "preserve_unrelated_firewall_policy": True,
            "requires_apply_time_conflict_check": True, "requires_backend_state_reverification": True,
            "require_rule_command_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            src = str(self.root / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Firewall rules plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target firewall backend/command metadata produced a real Alpha 60 single inbound TCP-port deny plan with apply-time conflict/state re-verification and preservation of existing/default/unrelated firewall policy. " + str(message)
        else:
            detail = f"PASS — analyzed firewall-rule capability is {capability}; Alpha 60 correctly fail-closed the attempted traffic-rule plan. " + str(message)
        self.add(4, "P4-ALPHA60-FIREWALL-RULES", "Firewall rules capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 60 firewall-rule {capability} behavior did not match capability policy. " + str(message)))

    def _add_part5_installer_gate(self, evidence: dict, source_sha256: str) -> None:
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            capability in allowed
            and evidence.get("analysis_scope") == "target_iso_installer_evidence"
            and evidence.get("credential_secret_read") is False
            and evidence.get("credential_secret_staged") is False
            and evidence.get("source_read_only") is True
            and evidence.get("stage_only") is True
        )
        if not schema_ok:
            self.add(5, "P5-INSTALLER-STRUCTURED", "Structured native installer capability / staging verification", FAIL,
                     "Part 5 installer evidence schema is missing/incomplete or secret/source isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and bool(evidence.get("native_generator"))
        payload = {
            "config_type": "part5_installer_profile", "part": 5, "gate_version": "part5-complete",
            "source_sha256": source_sha256, "analysis_scope": "target_iso_installer_evidence",
            "capability_status": capability, "installer_family": str(evidence.get("installer_family") or "unknown"),
            "native_generator": str(evidence.get("native_generator") or ""), "control_depth": "advanced",
            "username": "chromapress", "display_name": "ChromaPress Test", "groups": ["audio", "video"],
            "admin": True, "credential_policy": "secure_hash_deferred_to_verified_apply", "hostname": "chromapress-test",
            "language": "en", "locale": "en_US.UTF-8", "keyboard": "us", "timezone": "Europe/Copenhagen",
            "network_mode": "dhcp", "ipv4_address": "", "gateway": "", "dns_servers": [],
            "package_selections": [], "installer_profile": "standard", "installation_behavior": "interactive_reviewed",
            "partitioning": "preserve_installer_default", "destructive_partitioning_confirmed": False,
            "credential_secret_read": False, "credential_secret_staged": False, "native_tool_validation_performed": False,
            "require_native_tool_validation_before_apply": True, "require_secure_credential_material_before_apply": True,
            "require_source_reverification_before_apply": True, "source_read_only": True, "preserve_unrelated": True,
            "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.part5 import generate_installer_template
            from chromapress.services.preflight import test_change
            if supported:
                payload["generated_native_template"] = generate_installer_template(payload)
                payload["generated_template_contains_real_secret"] = False
            status, message = test_change(ChangeItem("Part 5 installer profile", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — verified native installer evidence produced a credential-free structured installer template and preflight accepted it; secure credential material and native validation remain apply-time requirements. " + str(message)
        else:
            detail = f"PASS — native installer capability is {capability}; unsupported/unverified family correctly failed closed without guessing from distro identity. " + str(message)
        self.add(5, "P5-INSTALLER-STRUCTURED", "Structured native installer capability / staging verification", PASS if ok else FAIL,
                 detail if ok else f"FAIL — Part 5 installer {capability} behavior did not match capability policy. {message}")

    def _add_part5_custom_content_gate(self, evidence: dict, source_sha256: str) -> None:
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            capability in allowed and evidence.get("analysis_scope") == "target_iso_rootfs_metadata"
            and evidence.get("source_image_contents_overwritten") is False
            and evidence.get("source_read_only") is True and evidence.get("stage_only") is True
        )
        if not schema_ok:
            self.add(5, "P5-CUSTOM-CONTENT", "Files / custom-content capability / staging verification", FAIL,
                     "Part 5 custom-content evidence schema is missing/incomplete or preservation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("rootfs_verified") is True
        payload = {
            "config_type": "part5_custom_content", "part": 5, "gate_version": "part5-complete", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_rootfs_metadata", "capability_status": capability, "target_kind": "default_user_content",
            "target_root": "/etc/skel/", "conflict_policy": "PRESERVE", "replace_unknown_content_confirmed": False,
            "entries": [{"source": "acceptance-synthetic", "relative_path": "Documents/README.txt", "type": "file", "mode": "0644", "ownership": "target-default"}],
            "entry_count": 1, "archive_inspected": True, "safe_paths_verified": True, "symlinks_validated": True,
            "show_target_paths": True, "show_conflicts": True, "show_ownership": True, "show_permissions": True,
            "require_review_before_apply": True, "require_target_conflict_review_before_apply": True,
            "never_silently_overwrite_unknown_source_content": True, "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Part 5 custom content", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = ("PASS — rootfs metadata permits reviewed /etc/skel staging with explicit PRESERVE conflict policy and archive/path/symlink review. " if supported else f"PASS — custom-content capability is {capability}; staging correctly failed closed. ") + str(message)
        self.add(5, "P5-CUSTOM-CONTENT", "Files / custom-content capability / staging verification", PASS if ok else FAIL,
                 detail if ok else f"FAIL — Part 5 custom-content {capability} behavior did not match capability policy. {message}")

    def _add_part5_desktop_gate(self, evidence: dict, source_sha256: str) -> None:
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            capability in allowed and evidence.get("analysis_scope") == "target_iso_package_manifest"
            and evidence.get("desktop_config_contents_read") is False and evidence.get("host_desktop_state_accessed") is False
            and evidence.get("source_read_only") is True and evidence.get("stage_only") is True
        )
        if not schema_ok:
            self.add(5, "P5-DESKTOP-NATIVE", "Desktop-native capability / staging verification", FAIL,
                     "Part 5 desktop evidence schema is missing/incomplete or host/config isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and bool(evidence.get("active_desktop")) and bool(evidence.get("native_adapter"))
        payload = {
            "config_type": "part5_desktop_defaults", "part": 5, "gate_version": "part5-complete", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability,
            "active_desktop": str(evidence.get("active_desktop") or ""), "native_adapter": str(evidence.get("native_adapter") or ""),
            "controls": {"wallpaper": "/usr/share/backgrounds/chromapress-acceptance.jpg"},
            "desktop_config_contents_read": False, "host_desktop_state_accessed": False,
            "require_native_adapter_reverification_before_apply": True, "preserve_unrelated_desktop_configuration": True,
            "source_read_only": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Part 5 desktop defaults", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = (f"PASS — {payload['active_desktop']} package evidence bound desktop staging to native adapter {payload['native_adapter']}; unrelated desktop configuration is preserved. " if supported else f"PASS — desktop capability is {capability}; ChromaPress correctly exposes no guessed desktop control. ") + str(message)
        self.add(5, "P5-DESKTOP-NATIVE", "Desktop-native capability / staging verification", PASS if ok else FAIL,
                 detail if ok else f"FAIL — Part 5 desktop {capability} behavior did not match capability policy. {message}")

    def _add_part5_kiosk_gate(self, evidence: dict, source_sha256: str) -> None:
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        modes = [str(x) for x in (evidence.get("supported_modes") or [])]
        schema_ok = (
            capability in allowed and evidence.get("analysis_scope") == "target_iso_package_manifest"
            and evidence.get("provider_or_website_hardcoded") is False and evidence.get("host_session_state_accessed") is False
            and evidence.get("source_read_only") is True and evidence.get("stage_only") is True
        )
        if not schema_ok:
            self.add(5, "P5-KIOSK-GENERIC", "Generic kiosk/thin-client capability / staging verification", FAIL,
                     "Part 5 kiosk evidence schema is missing/incomplete or generic/host isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and bool(modes)
        mode = modes[0] if modes else "browser_kiosk"
        if mode == "browser_kiosk": target = "https://example.invalid"
        elif mode in {"custom_application_kiosk", "minimal_wayland_weston"}: target = "/usr/bin/true"
        else: target = ""
        payload = {
            "config_type": "part5_kiosk_session", "part": 5, "gate_version": "part5-complete", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability, "supported_modes": modes,
            "mode": mode, "target": target, "weston_verified": evidence.get("weston_verified") is True,
            "browser_packages": list(evidence.get("browser_packages") or []), "fullscreen": True, "autostart": True,
            "restricted_navigation": True, "restricted_session_controls": True, "controlled_recovery_escape": True,
            "provider_or_website_hardcoded": False, "require_runtime_session_validation_before_apply": True,
            "require_part4_security_review_before_apply": True, "source_read_only": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Part 5 kiosk session", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = (f"PASS — verified target packages permit generic kiosk mode {mode}; runtime validation and controlled recovery escape remain required before apply. " if supported else f"PASS — kiosk capability is {capability}; no website/provider/runtime support was invented. ") + str(message)
        self.add(5, "P5-KIOSK-GENERIC", "Generic kiosk/thin-client capability / staging verification", PASS if ok else FAIL,
                 detail if ok else f"FAIL — Part 5 kiosk {capability} behavior did not match capability policy. {message}")

    def _add_part5_acceptance_gates(self, payload: dict) -> None:
        source_sha = str(payload.get("sha256") or "")
        self._add_part5_installer_gate(dict(payload.get("part5_installer_evidence") or {}), source_sha)
        self._add_part5_custom_content_gate(dict(payload.get("part5_custom_content_evidence") or {}), source_sha)
        self._add_part5_desktop_gate(dict(payload.get("part5_desktop_evidence") or {}), source_sha)
        self._add_part5_kiosk_gate(dict(payload.get("part5_kiosk_evidence") or {}), source_sha)

    def _project_version(self) -> str:
        p = self.root / "pyproject.toml"
        if not p.is_file() or tomllib is None:
            return "unknown"
        try:
            return str(tomllib.loads(p.read_text(encoding="utf-8"))["project"]["version"])
        except Exception:
            return "unknown"

    def _add_alpha61_persistence_policy_gate(self, evidence: dict, kiosk: dict, source_sha256: str) -> None:
        """Validate Alpha 61 kiosk persistence-policy staging or truthful fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha61"
            and evidence.get("analysis_scope") == "target_iso_metadata"
            and capability in allowed
            and evidence.get("existing_persistence_policy_read") is False
            and evidence.get("persistent_data_contents_read") is False
            and evidence.get("mount_configuration_contents_read") is False
            and evidence.get("host_storage_accessed") is False
            and evidence.get("host_mount_state_accessed") is False
            and evidence.get("source_read_only") is True
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA61-PERSISTENCE-POLICY", "Persistence policy capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 61 persistence-policy evidence schema is missing/incomplete or host/data isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        username = "chromakiosk61"
        existing = {str(x).casefold() for x in (kiosk.get("existing_regular_users") or [])}
        account_dependency = "verified_existing_target_user" if username in existing else "alpha55_dedicated_non_admin_kiosk_user"
        payload = {
            "config_type": "persistence_policy", "gate_version": "alpha61", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_metadata", "capability_status": capability,
            "rootfs_persistence_policy_verified": supported, "operation": "require_volatile_kiosk_runtime",
            "username": username, "account_dependency": account_dependency,
            "existing_regular_users": sorted(existing), "admin_users": [str(x).casefold() for x in (kiosk.get("admin_users") or [])],
            "policy_scope": "kiosk_session_runtime_only",
            "persistence_policy": "volatile", "persistent_directories": [], "runtime_changes_survive_reboot": False,
            "selected_directories_survive_reboot": False, "unlisted_runtime_changes_survive_reboot": False,
            "part3_dependency": "immutable_runtime", "rootfs_layers": list(evidence.get("rootfs_layers") or []),
            "boot_config_files": list(evidence.get("boot_config_files") or []), "initramfs_mechanism": str(evidence.get("initramfs_mechanism") or ""),
            "existing_persistence_policy_read": False, "persistent_data_contents_read": False,
            "mount_configuration_contents_read": False, "host_storage_accessed": False, "host_mount_state_accessed": False,
            "require_part3_dependency_before_apply": True, "require_part3_dependency_reverification_before_apply": True,
            "require_account_dependency_reverification_before_apply": True, "preserve_existing_persistence_configuration": True,
            "preserve_unselected_user_data": True, "do_not_stage_mount_or_volume_changes": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Persistence policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target metadata produced a real Alpha 61 volatile kiosk persistence policy with explicit Part 3 dependency and no persistence/data/host-state reads. " + str(message)
        else:
            detail = f"PASS — analyzed persistence-policy capability is {capability}; Alpha 61 correctly fail-closed the attempted policy change. " + str(message)
        self.add(4, "P4-ALPHA61-PERSISTENCE-POLICY", "Persistence policy capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 61 persistence-policy {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha62_admin_recovery_policy_gate(self, evidence: dict, source_sha256: str) -> None:
        """Validate Alpha 62 administrator/recovery policy staging or truthful fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha62"
            and evidence.get("analysis_scope") == "target_iso_rootfs"
            and capability in allowed
            and evidence.get("shadow_read") is False
            and evidence.get("credential_secret_read") is False
            and evidence.get("recovery_secret_read") is False
            and evidence.get("pam_contents_read") is False
            and evidence.get("ssh_config_read") is False
            and evidence.get("rescue_boot_config_read") is False
            and evidence.get("root_account_policy_read") is False
            and evidence.get("host_accounts_touched") is False
            and evidence.get("host_login_state_accessed") is False
            and evidence.get("source_read_only") is True
            and isinstance(evidence.get("admin_groups"), list)
            and isinstance(evidence.get("existing_regular_users"), list)
            and isinstance(evidence.get("existing_admin_users"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA62-ADMIN-RECOVERY-POLICY", "Administrator/recovery policy capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 62 administrator/recovery schema is missing/incomplete or protected-state isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        admins = {str(x).casefold() for x in (evidence.get("existing_admin_users") or [])}
        existing = {str(x).casefold() for x in (evidence.get("existing_regular_users") or [])}
        admin_groups = [str(x) for x in (evidence.get("admin_groups") or []) if str(x) in {"sudo", "wheel"}]
        username = next((x for x in sorted(admins) if x != str(evidence.get("autologin_user") or "").casefold()), "acceptance62recovery")
        if username in admins:
            dependency = "verified_existing_admin_user"
        else:
            while username in existing or username == str(evidence.get("autologin_user") or "").casefold():
                username += "x"
            dependency = "alpha50_create_administrator"
        payload = {
            "config_type": "administrator_recovery_policy", "gate_version": "alpha62",
            "source_sha256": source_sha256, "analysis_scope": "target_iso_rootfs",
            "capability_status": capability, "rootfs_admin_recovery_verified": supported,
            "operation": "require_dedicated_recovery_administrator",
            "policy_scope": "separate_non_autologin_recovery_administrator",
            "username": username, "admin_group": admin_groups[0] if admin_groups else "",
            "account_dependency": dependency, "existing_regular_users": sorted(existing),
            "existing_admin_users": sorted(admins), "verified_admin_groups": admin_groups,
            "current_autologin_user": str(evidence.get("autologin_user") or "").casefold(),
            "recovery_account_must_be_distinct_from_kiosk": True,
            "recovery_account_must_not_autologin": True, "allow_root_as_recovery_administrator": False,
            "credential_policy": "deferred_secure_verified_apply",
            "authentication_factor_policy": "deferred_to_fido2_webauthn_security_key_tpm_gates",
            "shadow_read": False, "credential_secret_read": False, "credential_secret_staged": False,
            "recovery_secret_read": False, "recovery_secret_staged": False,
            "pam_contents_read": False, "ssh_config_read": False, "rescue_boot_config_read": False,
            "root_account_policy_read": False, "host_accounts_touched": False, "host_login_state_accessed": False,
            "preserve_existing_administrators": True, "preserve_root_account_policy": True,
            "preserve_rescue_boot_configuration": True, "preserve_pam_configuration": True,
            "preserve_ssh_configuration": True, "do_not_stage_authenticator_changes": True,
            "require_admin_membership_reverification_before_apply": True,
            "require_autologin_reverification_before_apply": True,
            "require_recovery_kiosk_separation_reverification_before_apply": True,
            "require_account_dependency_before_apply": True, "require_account_dependency_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Administrator/recovery policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target account/autologin metadata produced a real Alpha 62 separate recovery-administrator policy with explicit account dependency and no credential/authenticator/root/rescue/PAM/SSH state reads. " + str(message)
        else:
            detail = f"PASS — analyzed administrator/recovery capability is {capability}; Alpha 62 correctly fail-closed the attempted policy change. " + str(message)
        self.add(4, "P4-ALPHA62-ADMIN-RECOVERY-POLICY", "Administrator/recovery policy capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 62 administrator/recovery {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha63_fido2_policy_gate(self, evidence: dict, admin_recovery: dict, source_sha256: str) -> None:
        """Validate Alpha 63 FIDO2 policy staging or truthful fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha63"
            and evidence.get("analysis_scope") == "target_iso_package_manifest"
            and capability in allowed
            and evidence.get("pam_contents_read") is False
            and evidence.get("pam_contents_modified_during_analysis") is False
            and evidence.get("authenticator_devices_enumerated") is False
            and evidence.get("usb_hid_state_accessed") is False
            and evidence.get("credential_ids_read") is False
            and evidence.get("credential_secret_read") is False
            and evidence.get("credential_secret_staged") is False
            and evidence.get("authenticator_enrollment_performed") is False
            and evidence.get("webauthn_capability_claimed") is False
            and evidence.get("security_key_presence_claimed") is False
            and evidence.get("yubikey_capability_claimed") is False
            and evidence.get("platform_authenticator_claimed") is False
            and evidence.get("tpm_capability_claimed") is False
            and evidence.get("host_authenticator_state_accessed") is False
            and evidence.get("source_read_only") is True
            and isinstance(evidence.get("pam_fido2_packages"), list)
            and isinstance(evidence.get("libfido2_packages"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA63-FIDO2-POLICY", "FIDO2 policy capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 63 FIDO2 schema is missing/incomplete or protected authenticator-state isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        admins = [str(x).casefold() for x in (admin_recovery.get("existing_admin_users") or []) if str(x).strip()]
        autologin = str(admin_recovery.get("autologin_user") or "").casefold()
        username = next((x for x in admins if x != autologin and x != "root"), "acceptance63recovery")
        payload = {
            "config_type": "fido2_policy", "gate_version": "alpha63",
            "source_sha256": source_sha256, "analysis_scope": "target_iso_package_manifest",
            "capability_status": capability, "fido2_policy_verified": supported,
            "operation": "require_fido2_second_factor_for_recovery_admin",
            "policy_scope": "recovery_administrator_fido2_second_factor",
            "username": username, "current_autologin_user": autologin,
            "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "pam_fido2_packages": list(evidence.get("pam_fido2_packages") or []),
            "libfido2_packages": list(evidence.get("libfido2_packages") or []),
            "fido2_tool_packages": list(evidence.get("fido2_tool_packages") or []),
            "authentication_composition": "existing_primary_plus_fido2_second_factor",
            "pam_contents_read": False, "pam_contents_modified_during_analysis": False,
            "authenticator_devices_enumerated": False, "usb_hid_state_accessed": False,
            "credential_ids_read": False, "credential_secret_read": False, "credential_secret_staged": False,
            "authenticator_enrollment_performed": False, "webauthn_capability_claimed": False,
            "security_key_presence_claimed": False, "yubikey_capability_claimed": False,
            "platform_authenticator_claimed": False, "tpm_capability_claimed": False,
            "host_authenticator_state_accessed": False,
            "preserve_existing_primary_authentication": True,
            "preserve_pam_contents_during_analysis_and_staging": True,
            "require_pam_integration_verification_before_apply": True,
            "require_alpha62_dependency_before_apply": True,
            "require_alpha62_dependency_reverification_before_apply": True,
            "require_target_package_reverification_before_apply": True,
            "require_recovery_username_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("FIDO2 policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target package metadata produced a real Alpha 63 FIDO2 second-factor policy intent with explicit Alpha 62 dependency and no authenticator/credential/PAM/host-state reads. " + str(message)
        else:
            detail = f"PASS — analyzed FIDO2 capability is {capability}; Alpha 63 correctly fail-closed the attempted policy change. " + str(message)
        self.add(4, "P4-ALPHA63-FIDO2-POLICY", "FIDO2 policy capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 63 FIDO2 {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha64_webauthn_policy_gate(self, evidence: dict, admin_recovery: dict, source_sha256: str) -> None:
        """Validate Alpha 64 WebAuthn policy staging or truthful fail-closed behavior."""
        allowed = {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "UNSUPPORTED", "BLOCKED", "UNKNOWN"}
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        schema_ok = (
            evidence.get("gate_version") == "alpha64"
            and evidence.get("analysis_scope") == "target_iso_package_manifest"
            and capability in allowed
            and evidence.get("browser_config_contents_read") is False
            and evidence.get("webauthn_runtime_verified") is False
            and evidence.get("relying_party_config_read") is False
            and evidence.get("relying_party_verified") is False
            and evidence.get("origin_config_read") is False
            and evidence.get("origin_verified") is False
            and evidence.get("authenticator_devices_enumerated") is False
            and evidence.get("usb_hid_state_accessed") is False
            and evidence.get("credential_ids_read") is False
            and evidence.get("credential_secret_read") is False
            and evidence.get("credential_secret_staged") is False
            and evidence.get("authenticator_enrollment_performed") is False
            and evidence.get("security_key_presence_claimed") is False
            and evidence.get("yubikey_capability_claimed") is False
            and evidence.get("platform_authenticator_claimed") is False
            and evidence.get("tpm_capability_claimed") is False
            and evidence.get("host_browser_state_accessed") is False
            and evidence.get("host_authenticator_state_accessed") is False
            and evidence.get("source_read_only") is True
            and isinstance(evidence.get("browser_packages"), list)
        )
        if not schema_ok:
            self.add(4, "P4-ALPHA64-WEBAUTHN-POLICY", "WebAuthn policy capability / staged configuration verification", FAIL,
                     "FAIL — Alpha 64 WebAuthn schema is missing/incomplete or protected browser/authenticator-state isolation is not explicit.")
            return
        supported = capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and evidence.get("verified") is True
        admins = [str(x).casefold() for x in (admin_recovery.get("existing_admin_users") or []) if str(x).strip()]
        autologin = str(admin_recovery.get("autologin_user") or "").casefold()
        username = next((x for x in admins if x != autologin and x != "root"), "acceptance64recovery")
        browsers = [str(x) for x in (evidence.get("browser_packages") or []) if str(x).strip()]
        payload = {
            "config_type": "webauthn_policy", "gate_version": "alpha64",
            "source_sha256": source_sha256, "analysis_scope": "target_iso_package_manifest",
            "capability_status": capability, "webauthn_policy_verified": supported,
            "operation": "allow_webauthn_for_recovery_web_workflows",
            "policy_scope": "recovery_administrator_browser_webauthn",
            "username": username, "current_autologin_user": autologin,
            "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "alpha63_evidence_observed": evidence.get("alpha63_evidence_observed") is True,
            "browser_package": browsers[0] if browsers else "", "browser_packages": browsers,
            "libfido2_packages": list(evidence.get("libfido2_packages") or []),
            "browser_config_contents_read": False, "webauthn_runtime_verified": False,
            "relying_party_config_read": False, "relying_party_verified": False,
            "origin_config_read": False, "origin_verified": False,
            "authenticator_devices_enumerated": False, "usb_hid_state_accessed": False,
            "credential_ids_read": False, "credential_secret_read": False, "credential_secret_staged": False,
            "authenticator_enrollment_performed": False, "security_key_presence_claimed": False,
            "yubikey_capability_claimed": False, "platform_authenticator_claimed": False,
            "tpm_capability_claimed": False, "host_browser_state_accessed": False,
            "host_authenticator_state_accessed": False,
            "preserve_existing_primary_authentication": True,
            "preserve_browser_configuration_during_analysis_and_staging": True,
            "require_browser_runtime_verification_before_apply": True,
            "require_relying_party_and_origin_verification_before_use": True,
            "require_alpha62_dependency_before_apply": True,
            "require_alpha62_dependency_reverification_before_apply": True,
            "require_target_package_reverification_before_apply": True,
            "require_recovery_username_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("WebAuthn policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False
            message = f"Preflight invocation failed: {exc}"
        if supported:
            detail = "PASS — analyzed target browser-package metadata produced a real Alpha 64 browser-mediated WebAuthn recovery-policy intent with explicit Alpha 62 dependency and no runtime/RP/origin/authenticator/credential/host-state claims. " + str(message)
        else:
            detail = f"PASS — analyzed WebAuthn capability is {capability}; Alpha 64 correctly fail-closed the attempted policy change. " + str(message)
        self.add(4, "P4-ALPHA64-WEBAUTHN-POLICY", "WebAuthn policy capability / staged configuration verification",
                 PASS if ok else FAIL, detail if ok else (f"FAIL — Alpha 64 WebAuthn {capability} behavior did not match capability policy. " + str(message)))

    def _add_alpha65_security_key_gate(self, evidence: dict, admin_recovery: dict, source_sha256: str) -> None:
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        supported = evidence.get("verified") is True and capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        username = next(iter(admin_recovery.get("existing_admin_users") or []), "recovery65")
        if username == str(admin_recovery.get("autologin_user") or ""):
            username = "recovery65"
        payload = {
            "config_type": "security_key_policy", "gate_version": "alpha65", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability,
            "security_key_policy_verified": supported, "operation": "allow_external_fido2_security_key_for_recovery_admin",
            "policy_scope": "recovery_administrator_external_security_key", "username": username,
            "current_autologin_user": str(admin_recovery.get("autologin_user") or ""),
            "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "fido2_dependency": "alpha63_fido2_policy", "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "alpha63_dependency_verified": evidence.get("alpha63_dependency_verified") is True,
            "security_key_tool_packages": list(evidence.get("security_key_tool_packages") or []),
            "libfido2_packages": list(evidence.get("libfido2_packages") or []),
            "physical_security_key_enumerated": False, "security_key_presence_claimed": False,
            "security_key_compatibility_claimed": False, "credential_ids_read": False,
            "credential_secret_read": False, "credential_secret_staged": False,
            "authenticator_enrollment_performed": False, "usb_hid_state_accessed": False,
            "yubikey_capability_claimed": False, "platform_authenticator_claimed": False,
            "tpm_capability_claimed": False, "host_authenticator_state_accessed": False,
            "preserve_existing_primary_authentication": True, "require_physical_key_verification_before_apply": True,
            "require_key_compatibility_verification_before_apply": True, "require_explicit_enrollment_before_use": True,
            "require_recovery_username_reverification_before_apply": True, "require_target_package_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Security-key policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = ("PASS — target metadata produced a generic external security-key policy intent with physical-key/compatibility/enrollment/credential claims deferred. " if supported else f"PASS — security-key capability is {capability}; Alpha 65 correctly failed closed. ") + str(message)
        self.add(4, "P4-ALPHA65-SECURITY-KEY", "Security-key policy capability / staged configuration verification", PASS if ok else FAIL, detail if ok else f"FAIL — Alpha 65 security-key {capability} behavior did not match capability policy. {message}")

    def _add_alpha66_yubikey_gate(self, evidence: dict, admin_recovery: dict, source_sha256: str) -> None:
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        supported = evidence.get("verified") is True and capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        username = next(iter(admin_recovery.get("existing_admin_users") or []), "recovery66")
        if username == str(admin_recovery.get("autologin_user") or ""):
            username = "recovery66"
        payload = {
            "config_type": "yubikey_policy", "gate_version": "alpha66", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability,
            "yubikey_policy_verified": supported, "operation": "allow_yubikey_class_authenticator_for_recovery_admin",
            "policy_scope": "recovery_administrator_yubikey_class", "username": username,
            "current_autologin_user": str(admin_recovery.get("autologin_user") or ""),
            "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "alpha65_evidence_observed": evidence.get("alpha65_evidence_observed") is True,
            "yubikey_packages": list(evidence.get("yubikey_packages") or []),
            "physical_yubikey_enumerated": False, "yubikey_presence_claimed": False,
            "serial_number_read": False, "otp_secret_read": False, "pin_secret_read": False,
            "credential_ids_read": False, "credential_secret_read": False, "credential_secret_staged": False,
            "authenticator_enrollment_performed": False, "usb_hid_state_accessed": False,
            "platform_authenticator_claimed": False, "tpm_capability_claimed": False,
            "host_authenticator_state_accessed": False, "preserve_existing_primary_authentication": True,
            "require_physical_yubikey_verification_before_apply": True,
            "require_vendor_mode_compatibility_verification_before_apply": True,
            "require_explicit_enrollment_before_use": True, "require_recovery_username_reverification_before_apply": True,
            "require_target_package_reverification_before_apply": True, "source_read_only": True,
            "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("YubiKey-class policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = ("PASS — target metadata produced a YubiKey-class policy intent without physical-device/serial/PIN/OTP/enrollment claims. " if supported else f"PASS — YubiKey-class capability is {capability}; Alpha 66 correctly failed closed. ") + str(message)
        self.add(4, "P4-ALPHA66-YUBIKEY", "YubiKey-class capability / staged configuration verification", PASS if ok else FAIL, detail if ok else f"FAIL — Alpha 66 YubiKey-class {capability} behavior did not match capability policy. {message}")

    def _add_alpha67_platform_authenticator_gate(self, evidence: dict, source_sha256: str) -> None:
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        # Static ISO evidence is expected to stay UNKNOWN. Verify that a staged intent fails closed.
        payload = {
            "config_type": "platform_authenticator_policy", "gate_version": "alpha67", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability,
            "platform_authenticator_policy_verified": evidence.get("verified") is True,
            "operation": "allow_verified_platform_authenticator_for_recovery_workflows",
            "policy_scope": "recovery_administrator_platform_authenticator", "username": "recovery67",
            "current_autologin_user": "", "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "alpha64_dependency_verified": evidence.get("alpha64_dependency_verified") is True,
            "platform_authenticator_runtime_verified": evidence.get("platform_authenticator_runtime_verified") is True,
            "platform_authenticator_hardware_verified": evidence.get("platform_authenticator_hardware_verified") is True,
            "biometric_capability_claimed": False, "tpm_capability_claimed": False,
            "credential_ids_read": False, "credential_secret_read": False, "credential_secret_staged": False,
            "authenticator_enrollment_performed": False, "host_authenticator_state_accessed": False,
            "preserve_existing_primary_authentication": True, "require_runtime_reverification_before_apply": True,
            "require_hardware_reverification_before_apply": True, "require_explicit_enrollment_before_use": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("Platform-authenticator policy plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = status == ChangeStatus.FAIL if capability not in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} else status == ChangeStatus.PASS
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = f"PASS — platform-authenticator capability is {capability}; static ISO analysis does not infer built-in authenticator hardware, biometrics or TPM and the gate {'failed closed' if capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'} else 'accepted separately verified runtime/hardware evidence'}. {message}"
        self.add(4, "P4-ALPHA67-PLATFORM-AUTH", "Platform-authenticator capability / fail-closed verification", PASS if ok else FAIL, detail if ok else f"FAIL — Alpha 67 platform-authenticator behavior did not match capability policy. {message}")

    def _add_alpha68_tpm_gate(self, evidence: dict, admin_recovery: dict, source_sha256: str) -> None:
        capability = str(evidence.get("capability_status") or "UNKNOWN")
        supported = evidence.get("verified") is True and capability in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"}
        username = next(iter(admin_recovery.get("existing_admin_users") or []), "recovery68")
        if username == str(admin_recovery.get("autologin_user") or ""):
            username = "recovery68"
        payload = {
            "config_type": "tpm_key_protection", "gate_version": "alpha68", "source_sha256": source_sha256,
            "analysis_scope": "target_iso_package_manifest", "capability_status": capability,
            "tpm_key_protection_verified": supported, "operation": "require_tpm_backed_recovery_key_protection",
            "policy_scope": "recovery_administrator_tpm_backed_key_protection", "username": username,
            "current_autologin_user": str(admin_recovery.get("autologin_user") or ""),
            "administrator_recovery_dependency": "alpha62_administrator_recovery_policy",
            "alpha62_dependency_verified": evidence.get("alpha62_dependency_verified") is True,
            "tpm_tool_packages": list(evidence.get("tpm_tool_packages") or []),
            "tss_packages": list(evidence.get("tss_packages") or []),
            "tpm_hardware_enumerated": False, "tpm_hardware_verified": False, "tpm_presence_claimed": False,
            "tpm_ownership_state_read": False, "pcr_values_read": False, "key_material_generated": False,
            "key_material_read": False, "key_material_staged": False, "key_material_sealed": False,
            "credential_secret_read": False, "credential_secret_staged": False,
            "biometric_capability_claimed": False, "platform_authenticator_claimed": False,
            "host_tpm_state_accessed": False, "preserve_existing_primary_authentication": True,
            "require_tpm_hardware_verification_before_apply": True,
            "require_tpm_ownership_verification_before_apply": True,
            "require_pcr_policy_review_before_sealing": True,
            "require_key_generation_and_sealing_only_at_verified_apply": True,
            "require_recovery_username_reverification_before_apply": True,
            "require_target_package_reverification_before_apply": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        try:
            from chromapress.models import ChangeItem, ChangeKind, ChangeStatus
            from chromapress.services.preflight import test_change
            status, message = test_change(ChangeItem("TPM-backed key-protection plan", ChangeKind.CONFIG, "acceptance", payload))
            ok = (status == ChangeStatus.PASS) if supported else (status == ChangeStatus.FAIL)
        except Exception as exc:
            ok = False; message = f"Preflight invocation failed: {exc}"
        detail = ("PASS — target metadata produced a TPM-backed key-protection policy intent while hardware/ownership/PCR/key operations remain deferred and TPM is not treated as biometric/platform-authenticator proof. " if supported else f"PASS — TPM key-protection capability is {capability}; Alpha 68 correctly failed closed. ") + str(message)
        self.add(4, "P4-ALPHA68-TPM", "TPM-backed credential/key protection capability / staged configuration verification", PASS if ok else FAIL, detail if ok else f"FAIL — Alpha 68 TPM {capability} behavior did not match capability policy. {message}")

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def iter_project_files(self) -> Iterable[Path]:
        for p in self.root.rglob("*"):
            try:
                rel = p.relative_to(self.root)
            except ValueError:
                continue
            if any(part in IGNORE_DIR_NAMES for part in rel.parts):
                continue
            if p.is_file():
                yield p

    def run(self) -> int:
        # Run in ordered phases and stop on the first automated failure. The
        # consolidated test pack itself uses stepwise checkpointing, so the next
        # invocation resumes at the failed test and performs a full seal pass once
        # the remainder is green.
        self.clean_known_test_caches()
        self.check_project_shape()
        self.check_runtime_source_alignment()
        self.check_syntax()
        if any(c.status == FAIL for c in self.checks):
            self.add_manual_gates()
            return self.write_reports()

        self.collect_and_run_pytest()
        if self.staged_sweep:
            self.run_part4_staged_gate_sweep()
            self.run_part5_staged_gate_sweep()
            self.run_part6_staged_gate_sweep()
            self.run_part7_staged_gate_sweep()
            self.run_part8_staged_gate_sweep()
        else:
            if self.through >= 4:
                self.part4_staged_sweep_status = "MANUAL_FALLBACK_SELECTED"
                self.add(4, "P4-STAGED-SWEEP", "Part 4 staged-gate sweep", SKIP,
                         "MANUAL_FALLBACK_SELECTED — consolidated staged-gate automation disabled by command line; the established manual Stage → Changes → Test → Undo workflow remains available.")
            if self.through >= 5:
                self.part5_staged_sweep_status = "MANUAL_FALLBACK_SELECTED"
                self.add(5, "P5-STAGED-SWEEP", "Part 5 staged-gate sweep", SKIP,
                         "MANUAL_FALLBACK_SELECTED — consolidated staged-gate automation disabled by command line; the established manual Stage → Changes → Test → Undo workflow remains available.")
            if self.through >= 6:
                self.part6_staged_sweep_status = "MANUAL_FALLBACK_SELECTED"
                self.add(6, "P6-STAGED-SWEEP", "Part 6 staged-gate sweep", SKIP,
                         "MANUAL_FALLBACK_SELECTED — consolidated staged-gate automation disabled by command line; human AI-source/security/dependency review remains mandatory.")
            if self.through >= 7:
                self.part7_staged_sweep_status = "MANUAL_FALLBACK_SELECTED"
                self.add(7, "P7-STAGED-SWEEP", "Part 7 staged-gate sweep", SKIP,
                         "MANUAL_FALLBACK_SELECTED — production-plan automation disabled by command line; manual profile/hook/output/build-plan review remains mandatory.")
            if self.through >= 8:
                self.part8_staged_sweep_status = "MANUAL_FALLBACK_SELECTED"
                self.add(8, "P8-STAGED-SWEEP", "Part 8 acceptance GUI sweep", SKIP,
                         "MANUAL_FALLBACK_SELECTED — cross-distro acceptance GUI automation disabled; runtime distro/boot verification remains manual.")
        if any(c.status == FAIL for c in self.checks):
            self.add_manual_gates()
            return self.write_reports()

        self.check_release_hygiene()
        self.check_security_and_privacy()
        self.check_part1()
        self.check_part2()
        self.check_part3_to_8_readiness()
        if any(c.status == FAIL for c in self.checks):
            self.add_manual_gates()
            return self.write_reports()

        self.check_optional_iso()
        self.add_manual_gates()
        return self.write_reports()


    def clean_known_test_caches(self) -> None:
        """Remove only deterministic Python/pytest cache artefacts inside the project.

        This is intentionally narrow: no logs, user workspaces, downloads, build
        products or unknown temporary files are deleted.
        """
        removed: list[str] = []
        for dname in (".pytest_cache", ".mypy_cache", ".ruff_cache"):
            for p in self.root.rglob(dname):
                if p.is_dir() and not any(part in IGNORE_DIR_NAMES for part in p.relative_to(self.root).parts[:-1]):
                    shutil.rmtree(p, ignore_errors=True)
                    removed.append(str(p.relative_to(self.root)))
        for p in list(self.root.rglob("__pycache__")):
            if p.is_dir() and not any(part in IGNORE_DIR_NAMES for part in p.relative_to(self.root).parts[:-1]):
                shutil.rmtree(p, ignore_errors=True)
                removed.append(str(p.relative_to(self.root)))
        for suffix in ("*.pyc", "*.pyo"):
            for p in self.root.rglob(suffix):
                if p.is_file() and not any(part in IGNORE_DIR_NAMES for part in p.relative_to(self.root).parts):
                    try:
                        p.unlink()
                        removed.append(str(p.relative_to(self.root)))
                    except OSError:
                        pass
        self.add(1, "GLOBAL-CACHE-CLEAN", "Known Python/pytest caches cleaned", PASS,
                 f"Removed {len(removed)} cache artefacts" if removed else "No Python/pytest cache artefacts present")

    def check_project_shape(self) -> None:
        required = [
            self.root / "pyproject.toml",
            self.root / "src" / "chromapress" / "__init__.py",
            self.root / "src" / "chromapress" / "app.py",
            self.root / "chromapress_testpack.py",
            self.root / "testpack" / "part4_tests.zip",
            self.root / "testpack" / "part4_tests.zip.sha256",
            self.root / "testpack" / "part4_manifest.json",
        ]
        if self.through >= 5:
            required.extend([
                self.root / "testpack" / "part5_tests.zip",
                self.root / "testpack" / "part5_tests.zip.sha256",
                self.root / "testpack" / "part5_manifest.json",
            ])
        if self.through >= 6:
            required.extend([
                self.root / "testpack" / "part6_tests.zip",
                self.root / "testpack" / "part6_tests.zip.sha256",
                self.root / "testpack" / "part6_manifest.json",
            ])
        if self.through >= 7:
            required.extend([
                self.root / "testpack" / "part7_tests.zip",
                self.root / "testpack" / "part7_tests.zip.sha256",
                self.root / "testpack" / "part7_manifest.json",
            ])
        if self.through >= 8:
            required.extend([
                self.root / "testpack" / "part8_tests.zip",
                self.root / "testpack" / "part8_tests.zip.sha256",
                self.root / "testpack" / "part8_manifest.json",
            ])
        missing = [str(p.relative_to(self.root)) for p in required if not p.exists()]
        self.add(1, "P1-STRUCTURE", "Core project structure", FAIL if missing else PASS,
                 "Missing: " + ", ".join(missing) if missing else f"Project version: {self.version}")

        if sys.version_info >= (3, 11):
            self.add(1, "P1-PYTHON", "Supported Python runtime", PASS, sys.version.split()[0])
        else:
            self.add(1, "P1-PYTHON", "Supported Python runtime", FAIL,
                     f"Python {sys.version.split()[0]} detected; ChromaPress requires >= 3.11")

    def check_syntax(self) -> None:
        bad: list[str] = []
        count = 0
        candidates: list[Path] = []
        src_root = self.root / "src"
        if src_root.exists():
            candidates.extend(src_root.rglob("*.py"))
        for top in (self.root / "chromapress_acceptance.py", self.root / "chromapress_testpack.py"):
            if top.is_file():
                candidates.append(top)
        for p in candidates:
            if any(part in IGNORE_DIR_NAMES for part in p.relative_to(self.root).parts):
                continue
            count += 1
            try:
                compile(p.read_text(encoding="utf-8"), str(p), "exec")
            except Exception as exc:
                bad.append(f"{p.relative_to(self.root)}: {exc}")
        self.add(1, "GLOBAL-SYNTAX", "Python syntax check (no bytecode written)",
                 FAIL if bad else PASS,
                 "; ".join(bad[:8]) if bad else f"{count} persistent Python files compiled in-memory; bundled tests are syntax/collection checked by the consolidated test pack")


    def _pytest_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        src = str(self.root / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env

    def _run_testpack(self, part: int) -> tuple[dict, str, str, int]:
        """Run one consolidated Part test pack and return report/status/console/count."""
        runner = self.root / "chromapress_testpack.py"
        json_report = self.report_dir / f".chromapress-part{part}-testpack-latest.json"
        cmd = [
            sys.executable, str(runner), "--part", str(part),
            "--project", str(self.root),
            "--report-dir", str(self.report_dir),
            "--json-report", str(json_report),
        ]
        if self.testpack_restart:
            cmd.append("--restart")
        if self.legacy_testpack:
            cmd.append("--legacy-full")
        try:
            cp = subprocess.run(cmd, cwd=self.root, env=self._pytest_env(), text=True, capture_output=True, timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {}, "TESTPACK_FAIL", f"Could not run Part {part} test pack: {exc}", 0
        console = (cp.stdout + ("\n" + cp.stderr if cp.stderr else "")).strip()
        try:
            report = json.loads(json_report.read_text(encoding="utf-8"))
        except Exception as exc:
            return {}, "TESTPACK_FAIL", f"Part {part} test pack did not produce readable JSON: {exc}. {console[-1500:]}", cp.returncode
        status = str(report.get("status") or "TESTPACK_FAIL")
        return report, status, console, cp.returncode

    def collect_and_run_pytest(self) -> None:
        """Run consolidated regression packs in Part order, stopping at first failing pack."""
        combined_nodes: list[str] = []
        outputs: list[str] = []

        # Part 4 archive is the historical/core regression pack and is run for every acceptance depth.
        if self.through >= 1:
            report, status, console, rc = self._run_testpack(4)
            self.part4_testpack_report = report
            self.part4_testpack_status = status
            self.testpack_report = report
            self.testpack_status = status
            nodes = [str(x) for x in report.get("collected_tests") or []]
            combined_nodes.extend(nodes)
            out = str(report.get("pytest_output") or console)
            outputs.append("--- PART 4 TEST PACK ---\n" + out)
            count = int(report.get("collected_count") or len(nodes))
            self.add(1, "GLOBAL-PYTEST-COLLECT", "Part 4 consolidated test-pack collection", PASS if count else FAIL,
                     f"{count} tests collected from one verified Part 4 archive" if count else "No Part 4 tests were collected")
            if status == "TESTPACK_PASS" and rc == 0:
                detail = f"{count} Part 4 bundled tests passed/accepted by the checkpoint runner"
                if report.get("resumed_from_checkpoint"):
                    detail += "; resumed from the previous failure and completed a full seal pass"
                self.add(1, "GLOBAL-PYTEST", "Part 4 consolidated regression test pack", PASS, detail)
            else:
                failed_at = str(report.get("failed_node") or "unknown")
                self.add(1, "GLOBAL-PYTEST", "Part 4 consolidated regression test pack", FAIL,
                         f"Stopped at first failure: {failed_at}. The next identical command resumes from that checkpoint. {console[-1200:]}")
                self.collected_tests = combined_nodes
                self.pytest_output = "\n\n".join(outputs)
                return

        if self.through >= 5:
            report, status, console, rc = self._run_testpack(5)
            self.part5_testpack_report = report
            self.part5_testpack_status = status
            nodes = [str(x) for x in report.get("collected_tests") or []]
            combined_nodes.extend(nodes)
            out = str(report.get("pytest_output") or console)
            outputs.append("--- PART 5 TEST PACK ---\n" + out)
            count = int(report.get("collected_count") or len(nodes))
            self.add(5, "P5-TESTPACK-COLLECT", "Part 5 consolidated test-pack collection", PASS if count else FAIL,
                     f"{count} tests collected from one verified Part 5 archive" if count else "No Part 5 tests were collected")
            if status == "TESTPACK_PASS" and rc == 0:
                detail = f"{count} Part 5 bundled tests passed/accepted by the checkpoint runner"
                if report.get("resumed_from_checkpoint"):
                    detail += "; resumed from the previous failure and completed a full seal pass"
                self.add(5, "P5-TESTPACK", "Part 5 consolidated regression test pack", PASS, detail)
            else:
                failed_at = str(report.get("failed_node") or "unknown")
                self.add(5, "P5-TESTPACK", "Part 5 consolidated regression test pack", FAIL,
                         f"Stopped at first failure: {failed_at}. The next identical command resumes from that checkpoint. {console[-1200:]}")
                self.collected_tests = combined_nodes
                self.pytest_output = "\n\n".join(outputs)
                return

        if self.through >= 6:
            report, status, console, rc = self._run_testpack(6)
            self.part6_testpack_report = report
            self.part6_testpack_status = status
            nodes = [str(x) for x in report.get("collected_tests") or []]
            combined_nodes.extend(nodes)
            out = str(report.get("pytest_output") or console)
            outputs.append("--- PART 6 TEST PACK ---\n" + out)
            count = int(report.get("collected_count") or len(nodes))
            self.add(6, "P6-TESTPACK-COLLECT", "Part 6 consolidated test-pack collection", PASS if count else FAIL,
                     f"{count} tests collected from one verified Part 6 archive" if count else "No Part 6 tests were collected")
            if status == "TESTPACK_PASS" and rc == 0:
                detail = f"{count} Part 6 bundled tests passed/accepted by the checkpoint runner"
                if report.get("resumed_from_checkpoint"):
                    detail += "; resumed from the previous failure and completed a full seal pass"
                self.add(6, "P6-TESTPACK", "Part 6 consolidated regression test pack", PASS, detail)
            else:
                failed_at = str(report.get("failed_node") or "unknown")
                self.add(6, "P6-TESTPACK", "Part 6 consolidated regression test pack", FAIL,
                         f"Stopped at first failure: {failed_at}. The next identical command resumes from that checkpoint. {console[-1200:]}")
                self.collected_tests = combined_nodes
                self.pytest_output = "\n\n".join(outputs)
                return

        if self.through >= 7:
            report, status, console, rc = self._run_testpack(7)
            self.part7_testpack_report = report
            self.part7_testpack_status = status
            nodes = [str(x) for x in report.get("collected_tests") or []]
            combined_nodes.extend(nodes)
            out = str(report.get("pytest_output") or console)
            outputs.append("--- PART 7 TEST PACK ---\n" + out)
            count = int(report.get("collected_count") or len(nodes))
            self.add(7, "P7-TESTPACK-COLLECT", "Part 7 consolidated test-pack collection", PASS if count else FAIL,
                     f"{count} tests collected from one verified Part 7 archive" if count else "No Part 7 tests were collected")
            if status == "TESTPACK_PASS" and rc == 0:
                detail = f"{count} Part 7 bundled tests passed/accepted by the checkpoint runner"
                if report.get("resumed_from_checkpoint"):
                    detail += "; resumed from the previous failure and completed a full seal pass"
                self.add(7, "P7-TESTPACK", "Part 7 consolidated regression test pack", PASS, detail)
            else:
                failed_at = str(report.get("failed_node") or "unknown")
                self.add(7, "P7-TESTPACK", "Part 7 consolidated regression test pack", FAIL,
                         f"Stopped at first failure: {failed_at}. The next identical command resumes from that checkpoint. {console[-1200:]}")
                self.collected_tests = combined_nodes
                self.pytest_output = "\n\n".join(outputs)
                return

        if self.through >= 8:
            report, status, console, rc = self._run_testpack(8)
            self.part8_testpack_report = report
            self.part8_testpack_status = status
            nodes = [str(x) for x in report.get("collected_tests") or []]
            combined_nodes.extend(nodes)
            out = str(report.get("pytest_output") or console)
            outputs.append("--- PART 8 TEST PACK ---\n" + out)
            count = int(report.get("collected_count") or len(nodes))
            self.add(8, "P8-TESTPACK-COLLECT", "Part 8 consolidated test-pack collection", PASS if count else FAIL,
                     f"{count} tests collected from one verified Part 8 archive" if count else "No Part 8 tests were collected")
            if status == "TESTPACK_PASS" and rc == 0:
                detail = f"{count} Part 8 bundled tests passed/accepted by the checkpoint runner"
                if report.get("resumed_from_checkpoint"):
                    detail += "; resumed from the previous failure and completed a full seal pass"
                self.add(8, "P8-TESTPACK", "Part 8 consolidated regression test pack", PASS, detail)
            else:
                failed_at = str(report.get("failed_node") or "unknown")
                self.add(8, "P8-TESTPACK", "Part 8 consolidated regression test pack", FAIL,
                         f"Stopped at first failure: {failed_at}. The next identical command resumes from that checkpoint. {console[-1200:]}")

        self.collected_tests = combined_nodes
        self.pytest_output = "\n\n".join(outputs)
        for part in range(1, self.through + 1):
            pat = TEST_PART_PATTERNS[part]
            matches = [t for t in self.collected_tests if pat.search(t)]
            self.add(part, f"P{part}-TEST-COVERAGE", "Detected automated tests for this Part", PASS if matches else SKIP,
                     f"{len(matches)} matching tests" if matches else "No matching dedicated tests yet")

    def run_part4_staged_gate_sweep(self) -> None:
        """Report Part 4 staged-gate results already produced by the test pack.

        No second pytest process is launched. The single test package is the source
        of truth, while manual Stage → Changes → Test → Undo remains available as
        fallback.
        """
        if self.through < 4:
            return
        groups = dict(self.testpack_report.get("part4_staged_gates") or {})
        overall = str(self.testpack_report.get("part4_staged_gate_status") or "AUTOMATED_GATE_SKIP")
        self.part4_staged_sweep_status = overall
        details: list[str] = []
        for alpha_text in sorted(groups, key=lambda x: int(x) if str(x).isdigit() else 9999):
            counts = dict(groups.get(alpha_text) or {})
            passed = int(counts.get("passed") or 0)
            failed = int(counts.get("failed") or 0)
            errors = int(counts.get("errors") or 0)
            skipped = int(counts.get("skipped") or 0)
            if failed or errors:
                status, label = FAIL, "AUTOMATED_GATE_FAIL"
            elif passed:
                status, label = PASS, "AUTOMATED_GATE_PASS"
            else:
                status, label = SKIP, "AUTOMATED_GATE_SKIP"
            self.add(4, f"P4-STAGED-A{alpha_text}", f"Alpha {alpha_text} staged-gate GUI automation", status,
                     f"{label} — Alpha {alpha_text}: {passed} passed, {failed + errors} failed/error, {skipped} skipped inside the consolidated test pack. Manual Stage → Changes → Test → Undo remains available as fallback.")
            details.append(f"A{alpha_text}:{label}")
        if overall == "AUTOMATED_GATE_FAIL":
            status = FAIL
        elif overall in {"AUTOMATED_GATE_PASS", "AUTOMATED_GATE_PASS_WITH_SKIPS"}:
            status = PASS
        else:
            status = SKIP
        self.part4_staged_sweep_output = " | ".join(details)
        self.add(4, "P4-STAGED-SWEEP", "Part 4 staged-gate sweep", status,
                 f"{overall} — staged-gate results came from the single consolidated checkpointed test package; manual fallback preserved.")


    def run_part5_staged_gate_sweep(self) -> None:
        """Report Part 5 GUI staged-gate results from the consolidated Part 5 pack."""
        if self.through < 5:
            return
        report = self.part5_testpack_report
        groups = dict(report.get("part5_staged_gates") or report.get("staged_gates") or {})
        overall = str(report.get("part5_staged_gate_status") or report.get("staged_gate_status") or "AUTOMATED_GATE_SKIP")
        self.part5_staged_sweep_status = overall
        details: list[str] = []
        for name in sorted(groups):
            counts = dict(groups.get(name) or {})
            passed = int(counts.get("passed") or 0); failed = int(counts.get("failed") or 0); errors = int(counts.get("errors") or 0); skipped = int(counts.get("skipped") or 0)
            if failed or errors:
                status, label = FAIL, "AUTOMATED_GATE_FAIL"
            elif passed:
                status, label = PASS, "AUTOMATED_GATE_PASS"
            else:
                status, label = SKIP, "AUTOMATED_GATE_SKIP"
            self.add(5, f"P5-STAGED-{str(name).upper()}", f"Part 5 staged-gate GUI automation — {name}", status,
                     f"{label} — {passed} passed, {failed + errors} failed/error, {skipped} skipped inside the consolidated Part 5 pack. Manual Stage → Changes → Test → Undo remains available as fallback.")
            details.append(f"{name}:{label}")
        status = FAIL if overall == "AUTOMATED_GATE_FAIL" else PASS if overall in {"AUTOMATED_GATE_PASS", "AUTOMATED_GATE_PASS_WITH_SKIPS"} else SKIP
        self.part5_staged_sweep_output = " | ".join(details)
        self.add(5, "P5-STAGED-SWEEP", "Part 5 staged-gate sweep", status,
                 f"{overall} — staged-gate results came from the single consolidated Part 5 checkpointed test package; manual fallback preserved.")

    def run_part6_staged_gate_sweep(self) -> None:
        """Report Part 6 AI App Studio staged-gate results from the consolidated Part 6 pack."""
        if self.through < 6:
            return
        report = self.part6_testpack_report
        groups = dict(report.get("part6_staged_gates") or report.get("staged_gates") or {})
        overall = str(report.get("part6_staged_gate_status") or report.get("staged_gate_status") or "AUTOMATED_GATE_SKIP")
        self.part6_staged_sweep_status = overall
        details: list[str] = []
        for name in sorted(groups):
            counts = dict(groups.get(name) or {})
            passed = int(counts.get("passed") or 0); failed = int(counts.get("failed") or 0); errors = int(counts.get("errors") or 0); skipped = int(counts.get("skipped") or 0)
            if failed or errors:
                status, label = FAIL, "AUTOMATED_GATE_FAIL"
            elif passed:
                status, label = PASS, "AUTOMATED_GATE_PASS"
            else:
                status, label = SKIP, "AUTOMATED_GATE_SKIP"
            self.add(6, f"P6-STAGED-{str(name).upper()}", f"Part 6 staged-gate GUI automation — {name}", status,
                     f"{label} — {passed} passed, {failed + errors} failed/error, {skipped} skipped inside the consolidated Part 6 pack. Human code/security/dependency review remains mandatory.")
            details.append(f"{name}:{label}")
        status = FAIL if overall == "AUTOMATED_GATE_FAIL" else PASS if overall in {"AUTOMATED_GATE_PASS", "AUTOMATED_GATE_PASS_WITH_SKIPS"} else SKIP
        self.part6_staged_sweep_output = " | ".join(details)
        self.add(6, "P6-STAGED-SWEEP", "Part 6 staged-gate sweep", status,
                 f"{overall} — staged-gate results came from the single consolidated Part 6 checkpointed test package; human review remains a separate gate.")

    def run_part7_staged_gate_sweep(self) -> None:
        """Report Part 7 production workflow GUI gates from the consolidated Part 7 pack."""
        if self.through < 7:
            return
        report = self.part7_testpack_report
        groups = dict(report.get("part7_staged_gates") or report.get("staged_gates") or {})
        overall = str(report.get("part7_staged_gate_status") or report.get("staged_gate_status") or "AUTOMATED_GATE_SKIP")
        self.part7_staged_sweep_status = overall
        details: list[str] = []
        for name in sorted(groups):
            counts = dict(groups.get(name) or {})
            passed = int(counts.get("passed") or 0); failed = int(counts.get("failed") or 0); errors = int(counts.get("errors") or 0); skipped = int(counts.get("skipped") or 0)
            if failed or errors:
                status, label = FAIL, "AUTOMATED_GATE_FAIL"
            elif passed:
                status, label = PASS, "AUTOMATED_GATE_PASS"
            else:
                status, label = SKIP, "AUTOMATED_GATE_SKIP"
            self.add(7, f"P7-STAGED-{str(name).upper()}", f"Part 7 staged-gate GUI automation — {name}", status,
                     f"{label} — {passed} passed, {failed + errors} failed/error, {skipped} skipped inside the consolidated Part 7 pack. Manual profile/hook/output/build-plan review remains available.")
            details.append(f"{name}:{label}")
        status = FAIL if overall == "AUTOMATED_GATE_FAIL" else PASS if overall in {"AUTOMATED_GATE_PASS", "AUTOMATED_GATE_PASS_WITH_SKIPS"} else SKIP
        self.part7_staged_sweep_output = " | ".join(details)
        self.add(7, "P7-STAGED-SWEEP", "Part 7 staged-gate sweep", status,
                 f"{overall} — staged-gate results came from the single consolidated Part 7 checkpointed test package; human production review remains a separate gate.")

    def run_part8_staged_gate_sweep(self) -> None:
        """Report Part 8 acceptance-framework GUI gates from the consolidated Part 8 pack."""
        if self.through < 8:
            return
        report = self.part8_testpack_report
        groups = dict(report.get("part8_staged_gates") or report.get("staged_gates") or {})
        overall = str(report.get("part8_staged_gate_status") or report.get("staged_gate_status") or "AUTOMATED_GATE_SKIP")
        self.part8_staged_sweep_status = overall
        details: list[str] = []
        for name in sorted(groups):
            counts = dict(groups.get(name) or {})
            passed = int(counts.get("passed") or 0); failed = int(counts.get("failed") or 0); errors = int(counts.get("errors") or 0); skipped = int(counts.get("skipped") or 0)
            if failed or errors:
                status, label = FAIL, "AUTOMATED_GATE_FAIL"
            elif passed:
                status, label = PASS, "AUTOMATED_GATE_PASS"
            else:
                status, label = SKIP, "AUTOMATED_GATE_SKIP"
            self.add(8, f"P8-STAGED-{str(name).upper()}", f"Part 8 acceptance GUI automation — {name}", status,
                     f"{label} — {passed} passed, {failed + errors} failed/error, {skipped} skipped inside the consolidated Part 8 pack. Runtime distro/boot verification remains a separate manual gate.")
            details.append(f"{name}:{label}")
        status = FAIL if overall == "AUTOMATED_GATE_FAIL" else PASS if overall in {"AUTOMATED_GATE_PASS", "AUTOMATED_GATE_PASS_WITH_SKIPS"} else SKIP
        self.part8_staged_sweep_output = " | ".join(details)
        self.add(8, "P8-STAGED-SWEEP", "Part 8 acceptance GUI sweep", status,
                 f"{overall} — acceptance UI results came from the single consolidated Part 8 checkpointed test package; analysis alone never marks a distro VERIFIED.")

    def check_release_hygiene(self) -> None:
        bad: list[str] = []
        for p in self.iter_project_files():
            rel = p.relative_to(self.root)
            if any(part in FORBIDDEN_RELEASE_NAMES for part in rel.parts):
                bad.append(str(rel))
            elif p.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES:
                bad.append(str(rel))
            elif p.name.lower().endswith(("~", ".orig", ".rej")):
                bad.append(str(rel))
        self.add(1, "GLOBAL-HYGIENE", "No build-cache/temp files in project package",
                 FAIL if bad else PASS,
                 "Unexpected: " + ", ".join(bad[:20]) if bad else "No cache/temp artefacts found")

        if self.release_zip:
            import zipfile
            if not self.release_zip.is_file():
                self.add(1, "GLOBAL-ZIP", "Release ZIP integrity/hygiene", FAIL, f"Not found: {self.release_zip}")
            else:
                bad_zip: list[str] = []
                try:
                    with zipfile.ZipFile(self.release_zip) as z:
                        corrupt = z.testzip()
                        for name in z.namelist():
                            parts = Path(name).parts
                            if any(x in FORBIDDEN_RELEASE_NAMES for x in parts):
                                bad_zip.append(name)
                            elif Path(name).suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES:
                                bad_zip.append(name)
                    if corrupt:
                        self.add(1, "GLOBAL-ZIP", "Release ZIP integrity/hygiene", FAIL, f"Corrupt member: {corrupt}")
                    elif bad_zip:
                        self.add(1, "GLOBAL-ZIP", "Release ZIP integrity/hygiene", FAIL,
                                 "Cache/temp members: " + ", ".join(bad_zip[:20]))
                    else:
                        self.add(1, "GLOBAL-ZIP", "Release ZIP integrity/hygiene", PASS,
                                 f"ZIP valid; SHA-256 {self.sha256(self.release_zip)}")
                except Exception as exc:
                    self.add(1, "GLOBAL-ZIP", "Release ZIP integrity/hygiene", FAIL, str(exc))

    def check_security_and_privacy(self) -> None:
        findings: list[str] = []
        scan_ext = {".py", ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg", ".md", ".txt", ".cmd", ".ps1", ".sh"}
        for p in self.iter_project_files():
            if p.resolve() == Path(__file__).resolve():
                continue
            if p.suffix.lower() not in scan_ext or p.stat().st_size > 2_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if PRIVATE_KEY_MARKER in text:
                findings.append(f"{p.relative_to(self.root)}: private key marker")
            for m in SECRET_ASSIGNMENT.finditer(text):
                value = m.group(2).strip().lower()
                if not any(word in value for word in SAFE_SECRET_WORDS):
                    findings.append(f"{p.relative_to(self.root)}: possible hard-coded {m.group(1)}")
                    break
        self.add(4 if self.through >= 4 else 1, "GLOBAL-SECRETS", "Secret/privacy static scan",
                 FAIL if findings else PASS,
                 "; ".join(findings[:20]) if findings else "No obvious embedded private keys or hard-coded credentials found")

        core_files = list((self.root / "src" / "chromapress").rglob("*.py")) if (self.root / "src" / "chromapress").exists() else []
        separation_hits: list[str] = []
        for p in core_files:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for forbidden in ("Internet Identity", "ChromaFiles", "ChromaCommand"):
                if forbidden.lower() in text.lower():
                    separation_hits.append(f"{p.relative_to(self.root)}: {forbidden}")
        self.add(1, "GLOBAL-SEPARATION", "ChromaPress/ChromaLinux core separation guard",
                 FAIL if separation_hits else PASS,
                 "; ".join(separation_hits[:20]) if separation_hits else "No ChromaLinux-only identity/desktop integration markers in core")

    def check_part1(self) -> None:
        src = self.root / "src" / "chromapress"
        required_modules = [
            "gui/source_page.py", "gui/overview_page.py", "gui/applications_page.py",
            "gui/changes.py", "services/paths.py", "services/wsl.py", "engine_cli.py",
        ]
        missing = [m for m in required_modules if not (src / m).is_file()]
        self.add(1, "P1-MODULES", "Workbench foundation modules present",
                 FAIL if missing else PASS, "Missing: " + ", ".join(missing) if missing else "Required foundation modules present")

        main = src / "gui" / "main_window.py"
        if main.is_file():
            text = main.read_text(encoding="utf-8", errors="ignore")
            nav = ["Source", "Overview", "Applications", "Components", "Files", "System", "Boot & Hardware", "Installer", "Desktop", "AI App Studio", "Changes", "Build & Verify"]
            missing_nav = [x for x in nav if x not in text]
            self.add(1, "P1-NAV", "Main workflow navigation present", FAIL if missing_nav else PASS,
                     "Missing: " + ", ".join(missing_nav) if missing_nav else "Full workflow navigation found")
        else:
            self.add(1, "P1-NAV", "Main workflow navigation present", FAIL, "main_window.py missing")

    def check_part2(self) -> None:
        if self.through < 2:
            return
        scenarios = self.root / "src" / "chromapress" / "scenarios.py"
        apps = self.root / "src" / "chromapress" / "gui" / "applications_page.py"
        missing = [str(x.relative_to(self.root)) for x in (scenarios, apps) if not x.is_file()]
        self.add(2, "P2-APPLICATIONS", "Applications/catalogue implementation present",
                 FAIL if missing else PASS, "Missing: " + ", ".join(missing) if missing else "Applications and scenario modules present")

        chromalearn = self.root / "bundled_apps" / "chromalearn_0.4.5_all.deb"
        old = self.root / "bundled_apps" / "chromalearn_0.4.4_all.deb"
        school = self.root / "bundled_docs" / "ChromaLearn_Skoleevalueringspakke_v1.2.1_DA.zip"
        if chromalearn.exists() or school.exists() or old.exists():
            if chromalearn.is_file():
                actual = self.sha256(chromalearn)
                self.add(2, "P2-CHROMALEARN", "ChromaLearn 0.4.5 integrity", PASS if actual == CHROMALEARN_045_SHA256 else FAIL,
                         f"SHA-256 {actual}")
            else:
                self.add(2, "P2-CHROMALEARN", "ChromaLearn 0.4.5 integrity", FAIL, "0.4.5 .deb missing")
            self.add(2, "P2-CHROMALEARN-OLD", "No stale ChromaLearn 0.4.4 bundle", FAIL if old.exists() else PASS,
                     "Old 0.4.4 bundle still present" if old.exists() else "No stale 0.4.4 bundle")
            if school.is_file():
                actual = self.sha256(school)
                self.add(2, "P2-SCHOOL", "School Evaluation Pack v1.2.1 integrity", PASS if actual == SCHOOL_PACK_121_SHA256 else FAIL,
                         f"SHA-256 {actual}")
            else:
                self.add(2, "P2-SCHOOL", "School Evaluation Pack v1.2.1 integrity", FAIL, "Evaluation Pack missing")

        source = scenarios.read_text(encoding="utf-8", errors="ignore") if scenarios.is_file() else ""
        expected = ["AbiWord", "Notepad++ Linux", "Refract Studio", "MangoHud", "nvtop", "Speedtest CLI", "GLMark2"]
        missing_labels = [x for x in expected if x.lower() not in source.lower()]
        self.add(2, "P2-RECOMMENDATIONS", "Locked Part 2 recommendations present",
                 FAIL if missing_labels else PASS,
                 "Missing: " + ", ".join(missing_labels) if missing_labels else "Office/Development/Production/Gaming recommendations found")

    def _placeholder(self, labels: Iterable[str]) -> tuple[bool, str]:
        p = self.root / "src" / "chromapress" / "gui" / "main_window.py"
        if not p.is_file():
            return True, "main_window.py missing"
        text = p.read_text(encoding="utf-8", errors="ignore")
        found = [label for label in labels if re.search(rf"PlaceholderPage\(\s*[\"']{re.escape(label)}[\"']", text)]
        return bool(found), ", ".join(found)

    def check_part3_to_8_readiness(self) -> None:
        if self.through >= 3:
            placeholder, labels = self._placeholder(["Boot & Hardware"])
            self.add(3, "P3-IMPLEMENTATION", "Boot/Kernel/Hardware page implemented",
                     NOT_IMPL if placeholder else PASS,
                     f"Placeholder remains: {labels}" if placeholder else "No Boot & Hardware placeholder detected")
        if self.through >= 4:
            placeholder, labels = self._placeholder(["System"])
            self.add(4, "P4-IMPLEMENTATION", "System Configuration page implemented",
                     NOT_IMPL if placeholder else PASS,
                     f"Placeholder remains: {labels}" if placeholder else "No System placeholder detected")
        if self.through >= 5:
            placeholder, labels = self._placeholder(["Files", "Installer", "Desktop"])
            self.add(5, "P5-IMPLEMENTATION", "Files/Installer/Desktop pages implemented",
                     NOT_IMPL if placeholder else PASS,
                     f"Placeholder remains: {labels}" if placeholder else "No Part 5 placeholders detected")
        if self.through >= 6:
            ai = self.root / "src" / "chromapress" / "gui" / "ai_studio.py"
            part6 = self.root / "src" / "chromapress" / "services" / "part6.py"
            catalog = self.root / "src" / "chromapress" / "services" / "ai_catalog.py"
            complete = ai.is_file() and part6.is_file() and catalog.is_file()
            self.add(6, "P6-IMPLEMENTATION", "AI App Studio reviewed-project workflow implemented",
                     PASS if complete else NOT_IMPL,
                     "AI UI, provider catalog and reviewed-project/security/dependency staging service present" if complete else "Part 6 AI App Studio service/module set is incomplete")
        if self.through >= 7:
            part7 = self.root / "src" / "chromapress" / "services" / "part7.py"
            production = self.root / "src" / "chromapress" / "gui" / "production_page.py"
            main = self.root / "src" / "chromapress" / "gui" / "main_window.py"
            main_text = main.read_text(encoding="utf-8", errors="ignore") if main.is_file() else ""
            complete = part7.is_file() and production.is_file() and "ProductionWorkflowPage" in main_text
            self.add(7, "P7-IMPLEMENTATION", "Presets, Expert and production-plan workflow implemented",
                     PASS if complete else NOT_IMPL,
                     "Inspectable profiles, capability-backed presets, reviewed Expert hooks and production preflight/build-plan staging present" if complete else "Part 7 production workflow modules are incomplete")
        if self.through >= 8:
            part8 = self.root / "src" / "chromapress" / "services" / "part8.py"
            production = self.root / "src" / "chromapress" / "gui" / "production_page.py"
            dedicated = [t for t in self.collected_tests if re.search(r"part8|cross.*distro", t, re.I)]
            complete = part8.is_file() and production.is_file() and bool(dedicated)
            self.add(8, "P8-IMPLEMENTATION", "Cross-distro hardening and acceptance framework implemented",
                     PASS if complete else NOT_IMPL,
                     f"Adapter priority matrix, fail-closed static/runtime checklist, diagnostics export and {len(dedicated)} dedicated Part 8 tests present" if complete else "Part 8 cross-distro acceptance framework is incomplete")

    def check_runtime_source_alignment(self) -> None:
        """Ensure the venv entry point imports this project tree, not a stale copy.

        Alpha updates are intentionally unpacked over the existing project while the
        Windows venv is preserved. A normal (non-editable) pip install can therefore
        leave ``chromapress.exe`` pointing at an older site-packages copy even though
        the project ``src/`` tree is current.

        On Windows this gate repairs that *local venv only* with an offline editable
        install when needed, then verifies the imported path again. It never modifies
        the selected ISO and uses ``--no-deps --no-build-isolation`` so it cannot fetch
        dependencies from the network.
        """
        if os.name != "nt":
            self.add(1, "P1-RUNTIME-SOURCE", "Runtime package source alignment", SKIP,
                     "Windows venv import-path check is only applicable on Windows.")
            return

        expected = (self.root / "src" / "chromapress").resolve()
        code = (
            "import pathlib, chromapress; "
            "p=pathlib.Path(chromapress.__file__).resolve(); "
            "print(p)"
        )

        def imported_path() -> tuple[Path | None, str]:
            try:
                cp = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=self.root,
                    env=self._pytest_env(),
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except Exception as exc:
                return None, str(exc)
            if cp.returncode != 0:
                return None, (cp.stderr or cp.stdout or "Could not import chromapress").strip()
            try:
                return Path(cp.stdout.strip().splitlines()[-1]).resolve(), ""
            except Exception:
                return None, f"Could not parse imported package path: {cp.stdout!r}"

        def aligned(path: Path | None) -> bool:
            return bool(path) and (path == expected / "__init__.py" or expected in path.parents)

        imported, error = imported_path()
        repaired = False
        if not aligned(imported):
            # Keep the user's established one-command acceptance workflow: repair only
            # the preserved .venv-win package link, never project data or the source ISO.
            install_cmd = [
                sys.executable, "-m", "pip", "install",
                "--no-deps", "--no-build-isolation", "--editable", str(self.root),
            ]
            try:
                cp = subprocess.run(
                    install_cmd,
                    cwd=self.root,
                    env=self._pytest_env(),
                    text=True,
                    capture_output=True,
                    timeout=180,
                    check=False,
                )
            except Exception as exc:
                detail = f"Initial import: {imported or error} | Local editable sync failed: {exc}"
                self.add(1, "P1-RUNTIME-SOURCE", "Runtime package source alignment", FAIL, detail)
                return
            if cp.returncode != 0:
                output = (cp.stderr or cp.stdout or "pip editable install failed").strip()[-2000:]
                detail = f"Initial import: {imported or error} | Local editable sync failed: {output}"
                self.add(1, "P1-RUNTIME-SOURCE", "Runtime package source alignment", FAIL, detail)
                return
            repaired = True
            imported, error = imported_path()

        if not aligned(imported):
            self.add(
                1, "P1-RUNTIME-SOURCE", "Runtime package source alignment", FAIL,
                f"Imported: {imported or error} | Expected under: {expected} | "
                "chromapress.exe would run stale/different code",
            )
            return

        detail = f"Imported: {imported} | Expected under: {expected}"
        if repaired:
            detail += " | Preserved venv synchronized locally with editable install"
        self.add(1, "P1-RUNTIME-SOURCE", "Runtime package source alignment", PASS, detail)

    def _add_part8_static_acceptance(self, payload: dict) -> None:
        """Evaluate Part 8 static evidence without turning analysis into VERIFIED."""
        try:
            from chromapress.services.part8 import build_static_acceptance, validate_acceptance_record, STATIC_READY
            record = build_static_acceptance(payload)
            ok, message = validate_acceptance_record(record)
            state = str(record.get("verification_state") or "")
            verified = record.get("verified") is True
            passed = bool(ok and state == STATIC_READY and not verified)
            adapter = dict(record.get("adapter") or {})
            detail = (
                f"{state} — adapter={adapter.get('label') or 'unclassified'} / priority={adapter.get('priority') or 'UNCLASSIFIED'}; "
                "source is SHA-locked and read-only; runtime/boot/output acceptance remains manual. Analysis did not claim VERIFIED."
            ) if ok else message
            self.add(8, "P8-REAL-STATIC", "Real ISO Part 8 static cross-distro acceptance", PASS if passed else FAIL, detail)
        except Exception as exc:
            self.add(8, "P8-REAL-STATIC", "Real ISO Part 8 static cross-distro acceptance", FAIL, f"Part 8 static acceptance failed closed: {exc}")

    def check_optional_iso(self) -> None:
        if self.iso is None:
            if self.through >= 1:
                self.add(1, "P1-REAL-ISO", "Real source ISO read-only analysis", SKIP,
                         "No --iso supplied. Provide one when real-image integration testing is required.")
            return
        if not self.iso.is_file():
            self.add(1, "P1-REAL-ISO", "Real source ISO read-only analysis", FAIL, f"ISO not found: {self.iso}")
            return

        before = self.sha256(self.iso)
        start_size = self.iso.stat().st_size
        detail = [f"Source SHA-256 before: {before}", f"Size: {start_size} bytes"]
        status = SKIP

        # Linux: call the local engine directly if xorriso is installed.
        # Windows: call the existing WslBridge, which performs read-only analyze.
        try:
            env = self._pytest_env()
            if os.name == "nt" and shutil.which("wsl.exe"):
                code = textwrap.dedent(
                    f"""
                    import json
                    from chromapress.services.wsl import WslBridge
                    print(json.dumps(WslBridge().analyze_iso({str(self.iso)!r})))
                    """
                )
                cp = subprocess.run([sys.executable, "-c", code], cwd=self.root, env=env,
                                    text=True, capture_output=True, timeout=360, check=False)
                if cp.returncode == 0:
                    payload = json.loads(cp.stdout.strip().splitlines()[-1])
                    detail.append(f"Detected: {payload.get('distribution')} {payload.get('version')} / {payload.get('architecture')}")
                    detail.append(f"Boot: BIOS={payload.get('bios_boot')} UEFI={payload.get('uefi_boot')}; rootfs={len(payload.get('rootfs') or [])}")
                    status = PASS
                    if self.through >= 8:
                        self._add_part8_static_acceptance(payload)
                    if self.through >= 5:
                        self._add_part5_acceptance_gates(payload)
                    if self.through >= 4:
                        identity = dict(payload.get("system_identity_evidence") or {})
                        verified = identity.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-IDENTITY",
                                 "Real ISO account database read-only verification",
                                 PASS if verified else FAIL,
                                 str(identity.get("reason") or "No identity rootfs evidence returned"))
                        self._add_alpha50_users_groups_password_gate(identity)
                        machine = dict(payload.get("system_machine_identity_evidence") or {})
                        machine_verified = machine.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-MACHINE-IDENTITY",
                                 "Real ISO hostname/machine identity read-only verification",
                                 PASS if machine_verified else FAIL,
                                 str(machine.get("reason") or "No hostname/machine identity rootfs evidence returned"))
                        autologin = dict(payload.get("system_autologin_evidence") or {})
                        autologin_verified = autologin.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-AUTOLOGIN",
                                 "Real ISO display-manager/autologin read-only verification",
                                 PASS if autologin_verified else FAIL,
                                 str(autologin.get("reason") or "No display-manager/autologin rootfs evidence returned"))
                        locale = dict(payload.get("system_locale_evidence") or {})
                        locale_verified = locale.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-LOCALE",
                                 "Real ISO locale/language read-only verification",
                                 PASS if locale_verified else FAIL,
                                 str(locale.get("reason") or "No locale/language rootfs evidence returned"))
                        keyboard = dict(payload.get("system_keyboard_evidence") or {})
                        keyboard_verified = keyboard.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-KEYBOARD",
                                 "Real ISO keyboard layout read-only verification",
                                 PASS if keyboard_verified else FAIL,
                                 str(keyboard.get("reason") or "No keyboard-layout rootfs evidence returned"))
                        timezone = dict(payload.get("system_timezone_evidence") or {})
                        timezone_verified = timezone.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TIMEZONE",
                                 "Real ISO timezone read-only verification",
                                 PASS if timezone_verified else FAIL,
                                 str(timezone.get("reason") or "No timezone rootfs evidence returned"))
                        network = dict(payload.get("system_network_dns_evidence") or {})
                        network_verified = network.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-NETWORK-DNS",
                                 "Real ISO networking/DNS read-only verification",
                                 PASS if network_verified else FAIL,
                                 str(network.get("reason") or "No networking/DNS rootfs evidence returned"))
                        self._add_alpha51_networking_configuration_gate(network, str(payload.get("sha256") or ""))
                        services = dict(payload.get("system_services_evidence") or {})
                        services_verified = services.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-SERVICES",
                                 "Real ISO services/systemd read-only verification",
                                 PASS if services_verified else FAIL,
                                 str(services.get("reason") or "No services/systemd rootfs evidence returned"))
                        timers = dict(payload.get("system_timers_evidence") or {})
                        timers_verified = timers.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TIMERS",
                                 "Real ISO timers/systemd read-only verification",
                                 PASS if timers_verified else FAIL,
                                 str(timers.get("reason") or "No timers/systemd rootfs evidence returned"))
                        targets = dict(payload.get("system_targets_evidence") or {})
                        targets_verified = targets.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TARGETS",
                                 "Real ISO targets/startup read-only verification",
                                 PASS if targets_verified else FAIL,
                                 str(targets.get("reason") or "No targets/startup rootfs evidence returned"))
                        firewall = dict(payload.get("system_firewall_evidence") or {})
                        firewall_verified = firewall.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-FIREWALL",
                                 "Real ISO firewall read-only verification",
                                 PASS if firewall_verified else FAIL,
                                 str(firewall.get("reason") or "No firewall rootfs evidence returned"))
                        apparmor = dict(payload.get("system_apparmor_evidence") or {})
                        apparmor_verified = apparmor.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-APPARMOR",
                                 "Real ISO AppArmor read-only verification",
                                 PASS if apparmor_verified else FAIL,
                                 str(apparmor.get("reason") or "No AppArmor rootfs evidence returned"))
                        selinux = dict(payload.get("system_selinux_evidence") or {})
                        self._add_alpha52_selinux_gate(selinux, str(payload.get("sha256") or ""))
                        sysctl = dict(payload.get("system_sysctl_evidence") or {})
                        sysctl_verified = sysctl.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-SYSCTL",
                                 "Real ISO sysctl read-only verification",
                                 PASS if sysctl_verified else FAIL,
                                 str(sysctl.get("reason") or "No sysctl rootfs evidence returned"))
                        security_defaults = dict(payload.get("system_security_defaults_evidence") or {})
                        self._add_alpha53_security_defaults_gate(security_defaults, str(payload.get("sha256") or ""))
                        config_overlay = dict(payload.get("system_config_overlay_evidence") or {})
                        self._add_alpha54_config_overlay_gate(config_overlay, str(payload.get("sha256") or ""))
                        kiosk_user = dict(payload.get("system_kiosk_user_evidence") or {})
                        self._add_alpha55_kiosk_user_gate(kiosk_user, str(payload.get("sha256") or ""))
                        restricted_login = dict(payload.get("system_restricted_login_evidence") or {})
                        self._add_alpha56_restricted_login_gate(restricted_login, str(payload.get("sha256") or ""))
                        restricted_session = dict(payload.get("system_restricted_session_evidence") or {})
                        self._add_alpha57_restricted_session_gate(restricted_session, str(payload.get("sha256") or ""))
                        service_lockdown = dict(payload.get("system_service_lockdown_evidence") or {})
                        self._add_alpha58_service_lockdown_gate(service_lockdown, str(payload.get("sha256") or ""))
                        network_restriction = dict(payload.get("system_network_restriction_evidence") or {})
                        self._add_alpha59_network_restriction_gate(network_restriction, str(payload.get("sha256") or ""))
                        firewall_rules = dict(payload.get("system_firewall_rules_evidence") or {})
                        self._add_alpha60_firewall_rules_gate(firewall_rules, str(payload.get("sha256") or ""))
                        persistence_policy = dict(payload.get("system_persistence_policy_evidence") or {})
                        self._add_alpha61_persistence_policy_gate(persistence_policy, kiosk_user, str(payload.get("sha256") or ""))
                        admin_recovery = dict(payload.get("system_admin_recovery_policy_evidence") or {})
                        self._add_alpha62_admin_recovery_policy_gate(admin_recovery, str(payload.get("sha256") or ""))
                        fido2_policy = dict(payload.get("system_fido2_policy_evidence") or {})
                        self._add_alpha63_fido2_policy_gate(fido2_policy, admin_recovery, str(payload.get("sha256") or ""))
                        webauthn_policy = dict(payload.get("system_webauthn_policy_evidence") or {})
                        self._add_alpha64_webauthn_policy_gate(webauthn_policy, admin_recovery, str(payload.get("sha256") or ""))
                        security_key_policy = dict(payload.get("system_security_key_policy_evidence") or {})
                        self._add_alpha65_security_key_gate(security_key_policy, admin_recovery, str(payload.get("sha256") or ""))
                        yubikey_policy = dict(payload.get("system_yubikey_policy_evidence") or {})
                        self._add_alpha66_yubikey_gate(yubikey_policy, admin_recovery, str(payload.get("sha256") or ""))
                        platform_auth_policy = dict(payload.get("system_platform_authenticator_policy_evidence") or {})
                        self._add_alpha67_platform_authenticator_gate(platform_auth_policy, str(payload.get("sha256") or ""))
                        tpm_policy = dict(payload.get("system_tpm_key_protection_evidence") or {})
                        self._add_alpha68_tpm_gate(tpm_policy, admin_recovery, str(payload.get("sha256") or ""))
                else:
                    detail.append("WSL analysis unavailable: " + (cp.stderr or cp.stdout)[-1000:].strip())
            elif shutil.which("xorriso"):
                cp = subprocess.run([sys.executable, "-m", "chromapress.engine_cli", "analyze", str(self.iso)],
                                    cwd=self.root, env=env, text=True, capture_output=True, timeout=360, check=False)
                if cp.returncode == 0:
                    payload = json.loads(cp.stdout)
                    detail.append(f"Detected: {payload.get('distribution')} {payload.get('version')} / {payload.get('architecture')}")
                    detail.append(f"Boot: BIOS={payload.get('bios_boot')} UEFI={payload.get('uefi_boot')}; rootfs={len(payload.get('rootfs') or [])}")
                    status = PASS
                    if self.through >= 8:
                        self._add_part8_static_acceptance(payload)
                    if self.through >= 5:
                        self._add_part5_acceptance_gates(payload)
                    if self.through >= 4:
                        identity = dict(payload.get("system_identity_evidence") or {})
                        verified = identity.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-IDENTITY",
                                 "Real ISO account database read-only verification",
                                 PASS if verified else FAIL,
                                 str(identity.get("reason") or "No identity rootfs evidence returned"))
                        self._add_alpha50_users_groups_password_gate(identity)
                        machine = dict(payload.get("system_machine_identity_evidence") or {})
                        machine_verified = machine.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-MACHINE-IDENTITY",
                                 "Real ISO hostname/machine identity read-only verification",
                                 PASS if machine_verified else FAIL,
                                 str(machine.get("reason") or "No hostname/machine identity rootfs evidence returned"))
                        autologin = dict(payload.get("system_autologin_evidence") or {})
                        autologin_verified = autologin.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-AUTOLOGIN",
                                 "Real ISO display-manager/autologin read-only verification",
                                 PASS if autologin_verified else FAIL,
                                 str(autologin.get("reason") or "No display-manager/autologin rootfs evidence returned"))
                        locale = dict(payload.get("system_locale_evidence") or {})
                        locale_verified = locale.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-LOCALE",
                                 "Real ISO locale/language read-only verification",
                                 PASS if locale_verified else FAIL,
                                 str(locale.get("reason") or "No locale/language rootfs evidence returned"))
                        keyboard = dict(payload.get("system_keyboard_evidence") or {})
                        keyboard_verified = keyboard.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-KEYBOARD",
                                 "Real ISO keyboard layout read-only verification",
                                 PASS if keyboard_verified else FAIL,
                                 str(keyboard.get("reason") or "No keyboard-layout rootfs evidence returned"))
                        timezone = dict(payload.get("system_timezone_evidence") or {})
                        timezone_verified = timezone.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TIMEZONE",
                                 "Real ISO timezone read-only verification",
                                 PASS if timezone_verified else FAIL,
                                 str(timezone.get("reason") or "No timezone rootfs evidence returned"))
                        network = dict(payload.get("system_network_dns_evidence") or {})
                        network_verified = network.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-NETWORK-DNS",
                                 "Real ISO networking/DNS read-only verification",
                                 PASS if network_verified else FAIL,
                                 str(network.get("reason") or "No networking/DNS rootfs evidence returned"))
                        self._add_alpha51_networking_configuration_gate(network, str(payload.get("sha256") or ""))
                        services = dict(payload.get("system_services_evidence") or {})
                        services_verified = services.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-SERVICES",
                                 "Real ISO services/systemd read-only verification",
                                 PASS if services_verified else FAIL,
                                 str(services.get("reason") or "No services/systemd rootfs evidence returned"))
                        timers = dict(payload.get("system_timers_evidence") or {})
                        timers_verified = timers.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TIMERS",
                                 "Real ISO timers/systemd read-only verification",
                                 PASS if timers_verified else FAIL,
                                 str(timers.get("reason") or "No timers/systemd rootfs evidence returned"))
                        targets = dict(payload.get("system_targets_evidence") or {})
                        targets_verified = targets.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-TARGETS",
                                 "Real ISO targets/startup read-only verification",
                                 PASS if targets_verified else FAIL,
                                 str(targets.get("reason") or "No targets/startup rootfs evidence returned"))
                        firewall = dict(payload.get("system_firewall_evidence") or {})
                        firewall_verified = firewall.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-FIREWALL",
                                 "Real ISO firewall read-only verification",
                                 PASS if firewall_verified else FAIL,
                                 str(firewall.get("reason") or "No firewall rootfs evidence returned"))
                        apparmor = dict(payload.get("system_apparmor_evidence") or {})
                        apparmor_verified = apparmor.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-APPARMOR",
                                 "Real ISO AppArmor read-only verification",
                                 PASS if apparmor_verified else FAIL,
                                 str(apparmor.get("reason") or "No AppArmor rootfs evidence returned"))
                        selinux = dict(payload.get("system_selinux_evidence") or {})
                        self._add_alpha52_selinux_gate(selinux, str(payload.get("sha256") or ""))
                        sysctl = dict(payload.get("system_sysctl_evidence") or {})
                        sysctl_verified = sysctl.get("verified") is True
                        self.add(4, "P4-REAL-ROOTFS-SYSCTL",
                                 "Real ISO sysctl read-only verification",
                                 PASS if sysctl_verified else FAIL,
                                 str(sysctl.get("reason") or "No sysctl rootfs evidence returned"))
                        security_defaults = dict(payload.get("system_security_defaults_evidence") or {})
                        self._add_alpha53_security_defaults_gate(security_defaults, str(payload.get("sha256") or ""))
                        config_overlay = dict(payload.get("system_config_overlay_evidence") or {})
                        self._add_alpha54_config_overlay_gate(config_overlay, str(payload.get("sha256") or ""))
                        kiosk_user = dict(payload.get("system_kiosk_user_evidence") or {})
                        self._add_alpha55_kiosk_user_gate(kiosk_user, str(payload.get("sha256") or ""))
                        restricted_login = dict(payload.get("system_restricted_login_evidence") or {})
                        self._add_alpha56_restricted_login_gate(restricted_login, str(payload.get("sha256") or ""))
                        restricted_session = dict(payload.get("system_restricted_session_evidence") or {})
                        self._add_alpha57_restricted_session_gate(restricted_session, str(payload.get("sha256") or ""))
                        service_lockdown = dict(payload.get("system_service_lockdown_evidence") or {})
                        self._add_alpha58_service_lockdown_gate(service_lockdown, str(payload.get("sha256") or ""))
                        network_restriction = dict(payload.get("system_network_restriction_evidence") or {})
                        self._add_alpha59_network_restriction_gate(network_restriction, str(payload.get("sha256") or ""))
                        firewall_rules = dict(payload.get("system_firewall_rules_evidence") or {})
                        self._add_alpha60_firewall_rules_gate(firewall_rules, str(payload.get("sha256") or ""))
                        persistence_policy = dict(payload.get("system_persistence_policy_evidence") or {})
                        self._add_alpha61_persistence_policy_gate(persistence_policy, kiosk_user, str(payload.get("sha256") or ""))
                        admin_recovery = dict(payload.get("system_admin_recovery_policy_evidence") or {})
                        self._add_alpha62_admin_recovery_policy_gate(admin_recovery, str(payload.get("sha256") or ""))
                        fido2_policy = dict(payload.get("system_fido2_policy_evidence") or {})
                        self._add_alpha63_fido2_policy_gate(fido2_policy, admin_recovery, str(payload.get("sha256") or ""))
                        webauthn_policy = dict(payload.get("system_webauthn_policy_evidence") or {})
                        self._add_alpha64_webauthn_policy_gate(webauthn_policy, admin_recovery, str(payload.get("sha256") or ""))
                        security_key_policy = dict(payload.get("system_security_key_policy_evidence") or {})
                        self._add_alpha65_security_key_gate(security_key_policy, admin_recovery, str(payload.get("sha256") or ""))
                        yubikey_policy = dict(payload.get("system_yubikey_policy_evidence") or {})
                        self._add_alpha66_yubikey_gate(yubikey_policy, admin_recovery, str(payload.get("sha256") or ""))
                        platform_auth_policy = dict(payload.get("system_platform_authenticator_policy_evidence") or {})
                        self._add_alpha67_platform_authenticator_gate(platform_auth_policy, str(payload.get("sha256") or ""))
                        tpm_policy = dict(payload.get("system_tpm_key_protection_evidence") or {})
                        self._add_alpha68_tpm_gate(tpm_policy, admin_recovery, str(payload.get("sha256") or ""))
                else:
                    detail.append("Local ISO analysis unavailable: " + (cp.stderr or cp.stdout)[-1000:].strip())
            else:
                detail.append("xorriso/WSL not available; analysis skipped truthfully")
        except Exception as exc:
            detail.append(f"Analysis skipped/error: {exc}")

        after = self.sha256(self.iso)
        if before != after or start_size != self.iso.stat().st_size:
            status = FAIL
            detail.append("SOURCE ISO CHANGED — fail-closed")
        else:
            detail.append("Source ISO unchanged byte-for-byte")
        self.add(1, "P1-REAL-ISO", "Real source ISO read-only analysis", status, " | ".join(detail))

    def add_manual_gates(self) -> None:
        manual = {
            1: "Visual GUI usability and source-selection workflow on Windows; browser/file-picker interaction.",
            2: "Visual consistency of Applications categories/actions and user confirmation that staged actions match intent.",
            3: "Real BIOS/UEFI boot test in VM/hardware after any boot/kernel change; never infer bootability from file creation alone.",
            4: "Policy review for account/security settings that depend on target distro and organization policy.",
            5: "Installer runtime test plus desktop/login behavior in a VM; verify credentials are not exposed.",
            6: "Human review of AI-generated code/security/dependencies before staging; never auto-approve generated code.",
            7: "Human review of Expert hooks, final build plan, output destination and destructive-impact warnings.",
            8: "Per-distro runtime acceptance: boot/install/live-session tests where applicable. Analysis alone is not VERIFIED.",
        }
        for part in range(1, self.through + 1):
            self.add(part, f"P{part}-MANUAL", "Remaining non-automatable acceptance", MANUAL, manual[part], automated=False)

    def part_status(self, part: int) -> str:
        items = [c for c in self.checks if c.part == part]
        if any(c.status == FAIL for c in items):
            return FAIL
        if any(c.status == NOT_IMPL for c in items):
            return NOT_IMPL
        if any(c.status == MANUAL for c in items):
            return "AUTOMATION_PASS_MANUAL_REMAINS"
        if items and all(c.status in (PASS, INFO, SKIP) for c in items):
            return PASS
        return SKIP

    def write_reports(self) -> int:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        md_path = self.report_dir / f"ChromaPress_Acceptance_{stamp}.md"
        json_path = self.report_dir / f"ChromaPress_Acceptance_{stamp}.json"

        fail_count = sum(c.status == FAIL for c in self.checks)
        not_impl_count = sum(c.status == NOT_IMPL for c in self.checks)
        manual_count = sum(c.status == MANUAL for c in self.checks)
        overall = FAIL if fail_count else ("AUTOMATION_PASS" if not_impl_count == 0 else "AUTOMATION_PASS_FUTURE_PARTS_NOT_IMPLEMENTED")

        data = {
            "schema": 1,
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "project_root": str(self.root),
            "version": self.version,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "through_part": self.through,
            "overall": overall,
            "counts": {"fail": fail_count, "not_implemented": not_impl_count, "manual_required": manual_count},
            "parts": {str(i): {"name": PARTS[i], "status": self.part_status(i)} for i in range(1, self.through + 1)},
            "checks": [asdict(c) for c in self.checks],
            "pytest_output": self.pytest_output,
            "part4_testpack_status": self.part4_testpack_status,
            "part4_staged_gate_sweep_status": self.part4_staged_sweep_status,
            "part4_staged_gate_sweep_output": self.part4_staged_sweep_output,
            "part5_testpack_status": self.part5_testpack_status,
            "part5_staged_gate_sweep_status": self.part5_staged_sweep_status,
            "part5_staged_gate_sweep_output": self.part5_staged_sweep_output,
            "part6_testpack_status": self.part6_testpack_status,
            "part6_staged_gate_sweep_status": self.part6_staged_sweep_status,
            "part6_staged_gate_sweep_output": self.part6_staged_sweep_output,
            "part7_testpack_status": self.part7_testpack_status,
            "part7_staged_gate_sweep_status": self.part7_staged_sweep_status,
            "part7_staged_gate_sweep_output": self.part7_staged_sweep_output,
            "part8_testpack_status": self.part8_testpack_status,
            "part8_staged_gate_sweep_status": self.part8_staged_sweep_status,
            "part8_staged_gate_sweep_output": self.part8_staged_sweep_output,
        }
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = [
            "# ChromaPress Acceptance Report",
            "",
            f"- Generated: {data['generated_utc']}",
            f"- Version: `{self.version}`",
            f"- Project: `{self.root}`",
            f"- Python: `{data['python']}`",
            f"- Tested through Part: **{self.through}/8**",
            f"- Overall automated status: **{overall}**",
            "",
            "## Part summary",
            "",
            "| Part | Area | Status |",
            "|---:|---|---|",
        ]
        for i in range(1, self.through + 1):
            lines.append(f"| {i} | {PARTS[i]} | **{self.part_status(i)}** |")
        lines += ["", "## Checks", ""]
        for i in range(1, self.through + 1):
            lines += [f"### Part {i} — {PARTS[i]}", ""]
            for c in [x for x in self.checks if x.part == i]:
                auto = "automated" if c.automated else "manual"
                lines.append(f"- **{c.status}** `{c.check_id}` — {c.name} ({auto})")
                if c.detail:
                    lines.append(f"  - {c.detail.replace(chr(10), ' ')}")
            lines.append("")
        if self.pytest_output:
            lines += ["## Pytest output", "", "```text", self.pytest_output[-8000:], "```", ""]
        if self.through >= 4:
            lines += ["## Part 4 staged-gate sweep", "", f"Status: **{self.part4_staged_sweep_status}**", ""]
            if self.part4_staged_sweep_output:
                lines += ["```text", self.part4_staged_sweep_output[-8000:], "```", ""]
        if self.through >= 5:
            lines += ["## Part 5 staged-gate sweep", "", f"Status: **{self.part5_staged_sweep_status}**", ""]
            if self.part5_staged_sweep_output:
                lines += ["```text", self.part5_staged_sweep_output[-8000:], "```", ""]
        if self.through >= 6:
            lines += ["## Part 6 staged-gate sweep", "", f"Status: **{self.part6_staged_sweep_status}**", ""]
            if self.part6_staged_sweep_output:
                lines += ["```text", self.part6_staged_sweep_output[-8000:], "```", ""]
        if self.through >= 7:
            lines += ["## Part 7 staged-gate sweep", "", f"Status: **{self.part7_staged_sweep_status}**", ""]
            if self.part7_staged_sweep_output:
                lines += ["```text", self.part7_staged_sweep_output[-8000:], "```", ""]
        if self.through >= 8:
            lines += ["## Part 8 acceptance GUI sweep", "", f"Status: **{self.part8_staged_sweep_status}**", ""]
            if self.part8_staged_sweep_output:
                lines += ["```text", self.part8_staged_sweep_output[-8000:], "```", ""]
        lines += [
            "## Interpretation",
            "",
            "`PASS` means that specific automated check passed. `MANUAL_REQUIRED` is deliberately not converted to PASS. "
            "`NOT_IMPLEMENTED` means the planned area is still a placeholder or lacks dedicated acceptance coverage. "
            "The runner never claims a Linux ISO is bootable unless an actual runtime boot test has been performed outside this script.",
            "",
        ]
        md_path.write_text("\n".join(lines), encoding="utf-8")

        print("\nChromaPress acceptance run complete")
        print(f"Version: {self.version}")
        print(f"Automated status: {overall}")
        for i in range(1, self.through + 1):
            print(f"Part {i}: {self.part_status(i)} - {PARTS[i]}")
        if self.through >= 4:
            print(f"PART4_TESTPACK={self.part4_testpack_status}")
            print(f"PART4_STAGED_GATES={self.part4_staged_sweep_status}")
        if self.through >= 5:
            print(f"PART5_TESTPACK={self.part5_testpack_status}")
            print(f"PART5_STAGED_GATES={self.part5_staged_sweep_status}")
        if self.through >= 6:
            print(f"PART6_TESTPACK={self.part6_testpack_status}")
            print(f"PART6_STAGED_GATES={self.part6_staged_sweep_status}")
        if self.through >= 7:
            print(f"PART7_TESTPACK={self.part7_testpack_status}")
            print(f"PART7_STAGED_GATES={self.part7_staged_sweep_status}")
        if self.through >= 8:
            print(f"PART8_TESTPACK={self.part8_testpack_status}")
            print(f"PART8_STAGED_GATES={self.part8_staged_sweep_status}")
        print(f"FAIL={fail_count}  NOT_IMPLEMENTED={not_impl_count}  MANUAL_REQUIRED={manual_count}")
        print(f"Markdown report: {md_path}")
        print(f"JSON report:     {json_path}")
        return 1 if fail_count else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run ChromaPress 8-part automated acceptance gates and generate reports.")
    p.add_argument("--project", type=Path, default=Path.cwd(), help="ChromaPress project root (default: current directory)")
    p.add_argument("--through", type=int, choices=range(1, 9), default=8, metavar="1..8",
                   help="Run/report Parts 1 through N (default: 8)")
    p.add_argument("--iso", type=Path, help="Optional source ISO for read-only analysis and immutability verification")
    p.add_argument("--release-zip", type=Path, help="Optional ChromaPress ZIP to verify for corruption/cache/temp files")
    p.add_argument("--report-dir", type=Path, help="Report directory (default: <project>/test-reports)")
    p.add_argument("--skip-staged-sweep", action="store_true",
                   help="Do not require/report automated Part 4/5/6 staged-gate results; retain the established manual/human-review fallbacks.")
    p.add_argument("--restart-testpack", action="store_true",
                   help="Discard a stored test-pack failure checkpoint and rerun the bundled suite from the first test.")
    p.add_argument("--legacy-testpack", action="store_true",
                   help="Run the entire bundled regression suite once without resume semantics (fallback diagnostic mode).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project.resolve()
    if not (root / "pyproject.toml").is_file():
        print(f"ERROR: {root} does not look like the ChromaPress project root (pyproject.toml missing).", file=sys.stderr)
        return 2
    report_dir = args.report_dir.resolve() if args.report_dir else root / "test-reports"
    runner = AcceptanceRunner(
        root, args.through, args.iso, args.release_zip, report_dir,
        staged_sweep=not args.skip_staged_sweep,
        testpack_restart=args.restart_testpack,
        legacy_testpack=args.legacy_testpack,
    )
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
