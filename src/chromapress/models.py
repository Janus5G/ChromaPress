from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json
import time
import uuid


class ChangeKind(str, Enum):
    PACKAGE_REPOSITORY = "package_repository"
    PACKAGE_REMOVE = "package_remove"
    PACKAGE_REPLACE = "package_replace"
    DIRECT_URL = "direct_url"
    LOCAL_PACKAGE = "local_package"
    GIT = "git"
    AI_APP = "ai_app"
    FILE = "file"
    CONFIG = "config"


class ChangeStatus(str, Enum):
    STAGED = "STAGED"
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class ChangeItem:
    title: str
    kind: ChangeKind
    detail: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: ChangeStatus = ChangeStatus.STAGED
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChangeItem":
        return cls(
            title=str(data["title"]),
            kind=ChangeKind(data["kind"]),
            detail=str(data.get("detail", "")),
            payload=dict(data.get("payload", {})),
            status=ChangeStatus(data.get("status", "STAGED")),
            id=str(data.get("id") or uuid.uuid4().hex),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class SourceState:
    kind: str = ""
    path: str = ""
    distribution: str = ""
    version: str = ""
    architecture: str = ""
    sha256: str = ""
    volume_id: str = ""
    installer: str = ""
    installer_evidence: list[dict[str, Any]] = field(default_factory=list)
    installer_config_files: list[str] = field(default_factory=list)
    installer_modes: list[str] = field(default_factory=list)
    part5_installer_evidence: dict[str, Any] = field(default_factory=dict)
    part5_custom_content_evidence: dict[str, Any] = field(default_factory=dict)
    part5_desktop_evidence: dict[str, Any] = field(default_factory=dict)
    part5_kiosk_evidence: dict[str, Any] = field(default_factory=dict)
    os_release_evidence: dict[str, Any] = field(default_factory=dict)
    package_format: str = ""
    bios_boot: bool = False
    uefi_boot: bool = False
    el_torito_boot: bool = False
    hybrid_boot: bool = False
    bootloaders: list[str] = field(default_factory=list)
    boot_catalog: str = ""
    boot_config_files: list[str] = field(default_factory=list)
    efi_images: list[str] = field(default_factory=list)
    kernel_images: list[str] = field(default_factory=list)
    initramfs_images: list[str] = field(default_factory=list)
    firmware_hints: list[str] = field(default_factory=list)
    boot_entries: list[dict[str, Any]] = field(default_factory=list)
    boot_defaults: list[str] = field(default_factory=list)
    boot_timeouts: list[str] = field(default_factory=list)
    kernel_arguments: list[dict[str, Any]] = field(default_factory=list)
    initramfs_mechanism: str = ""
    hardware_package_hints: list[dict[str, Any]] = field(default_factory=list)
    component_inventory: list[dict[str, Any]] = field(default_factory=list)
    system_package_evidence: list[dict[str, Any]] = field(default_factory=list)
    system_rootfs_verification: list[str] = field(default_factory=list)
    system_identity_evidence: dict[str, Any] = field(default_factory=dict)
    system_machine_identity_evidence: dict[str, Any] = field(default_factory=dict)
    system_autologin_evidence: dict[str, Any] = field(default_factory=dict)
    system_locale_evidence: dict[str, Any] = field(default_factory=dict)
    system_keyboard_evidence: dict[str, Any] = field(default_factory=dict)
    system_timezone_evidence: dict[str, Any] = field(default_factory=dict)
    system_network_dns_evidence: dict[str, Any] = field(default_factory=dict)
    system_services_evidence: dict[str, Any] = field(default_factory=dict)
    system_timers_evidence: dict[str, Any] = field(default_factory=dict)
    system_targets_evidence: dict[str, Any] = field(default_factory=dict)
    system_firewall_evidence: dict[str, Any] = field(default_factory=dict)
    system_apparmor_evidence: dict[str, Any] = field(default_factory=dict)
    system_selinux_evidence: dict[str, Any] = field(default_factory=dict)
    system_sysctl_evidence: dict[str, Any] = field(default_factory=dict)
    system_config_overlay_evidence: dict[str, Any] = field(default_factory=dict)
    system_kiosk_user_evidence: dict[str, Any] = field(default_factory=dict)
    system_restricted_login_evidence: dict[str, Any] = field(default_factory=dict)
    system_restricted_session_evidence: dict[str, Any] = field(default_factory=dict)
    system_service_lockdown_evidence: dict[str, Any] = field(default_factory=dict)
    system_security_defaults_evidence: dict[str, Any] = field(default_factory=dict)
    system_network_restriction_evidence: dict[str, Any] = field(default_factory=dict)
    system_firewall_rules_evidence: dict[str, Any] = field(default_factory=dict)
    system_persistence_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_admin_recovery_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_fido2_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_webauthn_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_security_key_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_yubikey_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_platform_authenticator_policy_evidence: dict[str, Any] = field(default_factory=dict)
    system_tpm_key_protection_evidence: dict[str, Any] = field(default_factory=dict)
    rootfs: list[str] = field(default_factory=list)
    rootfs_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectState:
    name: str = "Untitled ChromaPress Project"
    source: SourceState = field(default_factory=SourceState)
    scenario: str = ""
    changes: list[ChangeItem] = field(default_factory=list)
    project_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "name": self.name,
            "source": asdict(self.source),
            "scenario": self.scenario,
            "changes": [c.to_dict() for c in self.changes],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        self.project_path = str(path)

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != 1:
            raise ValueError("Unsupported ChromaPress project schema")
        project = cls(
            name=str(raw.get("name", "Untitled ChromaPress Project")),
            source=SourceState(**dict(raw.get("source", {}))),
            scenario=str(raw.get("scenario", "")),
            changes=[ChangeItem.from_dict(x) for x in raw.get("changes", [])],
            project_path=str(path),
        )
        return project
