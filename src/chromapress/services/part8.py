from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
import json
import re

PART8_GATE = "part8-complete"
ACCEPTANCE_SCHEMA = 1
STATUS_PASS = "PASS"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_RUNTIME = "RUNTIME_REQUIRED"
STATUS_MANUAL = "MANUAL_REQUIRED"
STATUS_NA = "NOT_APPLICABLE"
STATUS_BLOCKED = "BLOCKED"
VERIFIED = "VERIFIED"
STATIC_READY = "STATIC_READY_RUNTIME_REQUIRED"
STATIC_INCOMPLETE = "STATIC_INCOMPLETE"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET = re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd|bearer[_-]?token|private[_-]?key)")

# Policy order is locked by Part 8.  These are adapter contracts / verification
# targets, not claims that any distribution has already passed runtime acceptance.
DISTRO_ADAPTERS: tuple[dict[str, Any], ...] = (
    {"id": "rhel", "label": "RHEL", "priority": "PRIMARY", "os_ids": ("rhel",), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "ubuntu-lts", "label": "Ubuntu LTS", "priority": "PRIMARY", "os_ids": ("ubuntu",), "package_format": "deb", "package_manager": "apt", "installer": "autoinstall", "initramfs": "update-initramfs"},
    {"id": "debian-stable", "label": "Debian Stable", "priority": "NEXT", "os_ids": ("debian",), "package_format": "deb", "package_manager": "apt", "installer": "preseed", "initramfs": "update-initramfs"},
    {"id": "rocky", "label": "Rocky Linux", "priority": "NEXT", "os_ids": ("rocky",), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "almalinux", "label": "AlmaLinux", "priority": "NEXT", "os_ids": ("almalinux", "alma"), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "oracle-linux", "label": "Oracle Linux", "priority": "NEXT", "os_ids": ("ol", "oracle", "oraclelinux"), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "fedora", "label": "Fedora", "priority": "SECONDARY", "os_ids": ("fedora",), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "linux-mint", "label": "Linux Mint", "priority": "SECONDARY", "os_ids": ("linuxmint",), "package_format": "deb", "package_manager": "apt", "installer": "detected-only", "initramfs": "update-initramfs"},
    {"id": "centos-stream", "label": "CentOS Stream", "priority": "SECONDARY", "os_ids": ("centos",), "package_format": "rpm", "package_manager": "dnf", "installer": "kickstart", "initramfs": "dracut"},
    {"id": "arch", "label": "Arch Linux", "priority": "COMMUNITY", "os_ids": ("arch",), "package_format": "pkg.tar", "package_manager": "pacman", "installer": "detected-only", "initramfs": "mkinitcpio"},
    {"id": "manjaro", "label": "Manjaro", "priority": "COMMUNITY", "os_ids": ("manjaro",), "package_format": "pkg.tar", "package_manager": "pacman", "installer": "detected-only", "initramfs": "mkinitcpio"},
    {"id": "opensuse", "label": "SUSE/openSUSE", "priority": "LATER", "os_ids": ("opensuse", "opensuse-leap", "opensuse-tumbleweed", "sles", "sled"), "package_format": "rpm", "package_manager": "zypper", "installer": "detected-only", "initramfs": "dracut"},
)

# Runtime checks are deliberately not auto-passed by source analysis.
CHECK_DEFS: tuple[dict[str, str], ...] = (
    {"id": "source_iso_readable", "label": "Source ISO readable", "kind": "static"},
    {"id": "distribution_detected", "label": "Distribution correctly detected", "kind": "static"},
    {"id": "boot_architecture_detected", "label": "Boot architecture detected", "kind": "static"},
    {"id": "rootfs_detected", "label": "Root filesystem detected", "kind": "static"},
    {"id": "installed_inventory_correct", "label": "Installed inventory correct", "kind": "evidence"},
    {"id": "repository_configuration_correct", "label": "Repository configuration correct", "kind": "evidence"},
    {"id": "package_operations_correct", "label": "Package operations correct", "kind": "runtime"},
    {"id": "installer_profile_generation_correct", "label": "Installer profile generation correct", "kind": "static"},
    {"id": "kernel_initramfs_handling_correct", "label": "Kernel/initramfs handling correct", "kind": "static"},
    {"id": "filesystem_preservation_correct", "label": "Filesystem preservation correct", "kind": "runtime"},
    {"id": "unknown_custom_content_preserved", "label": "Unknown/custom content preserved", "kind": "runtime"},
    {"id": "iso_rebuild_succeeds", "label": "ISO rebuild succeeds when required", "kind": "runtime"},
    {"id": "bios_boot_preserved", "label": "BIOS boot preserved where applicable", "kind": "conditional-runtime"},
    {"id": "uefi_boot_preserved", "label": "UEFI boot preserved where applicable", "kind": "conditional-runtime"},
    {"id": "rootfs_contains_staged_modifications", "label": "Resulting rootfs contains staged modifications", "kind": "runtime"},
    {"id": "no_unintended_modifications", "label": "No unintended modifications", "kind": "runtime"},
    {"id": "diagnostics_available", "label": "Diagnostics available", "kind": "static"},
    {"id": "output_checksum_generated", "label": "Output checksum generated", "kind": "runtime"},
    {"id": "static_validation_passes", "label": "Static validation passes", "kind": "static-summary"},
    {"id": "manual_runtime_test_passes", "label": "Manual runtime test passes where required", "kind": "manual"},
)


def _dict(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if is_dataclass(source):
        return asdict(source)
    if hasattr(source, "__dict__"):
        return dict(source.__dict__)
    return {}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256.fullmatch(str(value or "").strip().lower()))


def _is_ubuntu_lts(version: str) -> bool:
    m = re.fullmatch(r"(\d{2})\.04(?:\.\d+)?", str(version or "").strip())
    return bool(m and int(m.group(1)) % 2 == 0)


def distro_matrix() -> list[dict[str, Any]]:
    return [dict(row, verification_state="UNVERIFIED") for row in DISTRO_ADAPTERS]


def match_distribution_adapter(source: Any) -> dict[str, Any]:
    data = _dict(source)
    osrel = dict(data.get("os_release_evidence") or {})
    os_id = str(osrel.get("id") or "").strip().casefold()
    distribution = str(data.get("distribution") or "").strip()
    version = str(osrel.get("version_id") or data.get("version") or "").strip()
    label = distribution.casefold()

    candidate: dict[str, Any] | None = None
    basis = ""
    if os_id:
        for row in DISTRO_ADAPTERS:
            if os_id in row["os_ids"]:
                candidate = dict(row); basis = "rootfs-os-release"; break
    if candidate is None:
        aliases = {
            "rhel": "rhel", "red hat enterprise linux": "rhel",
            "ubuntu": "ubuntu-lts", "lubuntu": "ubuntu-lts",
            "debian stable": "debian-stable", "debian": "debian-stable",
            "rocky linux": "rocky", "rocky": "rocky", "almalinux": "almalinux", "alma linux": "almalinux",
            "oracle linux": "oracle-linux", "fedora": "fedora", "linux mint": "linux-mint",
            "centos stream": "centos-stream", "arch linux": "arch", "manjaro": "manjaro",
            "opensuse": "opensuse", "suse": "opensuse", "sles": "opensuse",
        }
        wanted = aliases.get(label)
        if wanted:
            candidate = next(dict(row) for row in DISTRO_ADAPTERS if row["id"] == wanted)
            basis = "analyzer-label"

    if candidate is None:
        family = "rpm" if "rpm" in label else "arch" if "arch" in label else "unknown"
        return {
            "matched": False, "id": "", "label": distribution or "Unknown Linux", "priority": "UNCLASSIFIED",
            "match_basis": "family-only" if family != "unknown" else "none", "release_qualified": False,
            "verification_state": "UNVERIFIED", "reason": "No exact Part 8 distribution adapter can be selected from current evidence.",
        }

    release_qualified = True
    reason = "Exact distribution evidence matched a Part 8 adapter contract."
    if candidate["id"] == "ubuntu-lts" and not _is_ubuntu_lts(version):
        release_qualified = False
        reason = "Ubuntu family detected, but the source evidence does not establish an Ubuntu LTS release."
    elif candidate["id"] == "debian-stable" and "stable" not in label and str(osrel.get("version_codename") or "").casefold() not in {"stable"}:
        # Debian ID/version identifies the family, not whether a mirror/release is the current Stable channel.
        release_qualified = False
        reason = "Debian family detected; Stable-channel qualification still requires explicit release evidence."
    candidate.update({
        "matched": True, "match_basis": basis, "version": version,
        "release_qualified": release_qualified, "verification_state": "UNVERIFIED", "reason": reason,
    })
    return candidate


def _check(check_id: str, status: str, evidence: str) -> dict[str, str]:
    label = next(row["label"] for row in CHECK_DEFS if row["id"] == check_id)
    return {"id": check_id, "label": label, "status": status, "evidence": str(evidence or "")}


def _supported_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    status = str(value.get("status") or value.get("capability_status") or "").upper()
    return status in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS", "PASS"} or value.get("verified") is True


def build_static_acceptance(source: Any) -> dict[str, Any]:
    data = _dict(source)
    source_sha = str(data.get("sha256") or "").strip().lower()
    adapter = match_distribution_adapter(data)
    arch = str(data.get("architecture") or "").strip()
    roots = list(data.get("rootfs") or [])
    package_format = str(data.get("package_format") or "unknown").strip().casefold()
    initramfs = str(data.get("initramfs_mechanism") or "").strip()
    kernel_images = list(data.get("kernel_images") or [])
    initramfs_images = list(data.get("initramfs_images") or [])
    inventory = list(data.get("system_package_evidence") or [])
    rootfs_verification = list(data.get("system_rootfs_verification") or [])
    installer_evidence = dict(data.get("part5_installer_evidence") or {})

    checks: list[dict[str, str]] = []
    checks.append(_check("source_iso_readable", STATUS_PASS if _valid_sha(source_sha) else STATUS_BLOCKED,
                         "Analyzed source has a SHA-256 fingerprint." if _valid_sha(source_sha) else "No verified source SHA-256."))
    checks.append(_check("distribution_detected", STATUS_PASS if adapter.get("matched") else STATUS_UNKNOWN,
                         f"{adapter.get('label')} via {adapter.get('match_basis')}; adapter remains UNVERIFIED."))
    checks.append(_check("boot_architecture_detected", STATUS_PASS if arch and arch.casefold() != "unknown" else STATUS_UNKNOWN,
                         f"Architecture: {arch or 'unknown'}."))
    checks.append(_check("rootfs_detected", STATUS_PASS if roots else STATUS_UNKNOWN,
                         f"Detected {len(roots)} rootfs layer(s)." if roots else "No rootfs layer detected."))
    checks.append(_check("installed_inventory_correct", STATUS_PASS if inventory and rootfs_verification else STATUS_UNKNOWN,
                         f"Inventory evidence entries: {len(inventory)}; rootfs verification markers: {len(rootfs_verification)}."))
    checks.append(_check("repository_configuration_correct", STATUS_UNKNOWN,
                         "Repository correctness is not inferred from package format or distribution family."))
    checks.append(_check("package_operations_correct", STATUS_RUNTIME,
                         "Package-operation behavior must be proven against the selected target/build result."))
    checks.append(_check("installer_profile_generation_correct", STATUS_PASS if _supported_evidence(installer_evidence) else STATUS_UNKNOWN,
                         str(installer_evidence.get("reason") or "No verified installer-generation capability evidence.")))

    expected_initramfs = str(adapter.get("initramfs") or "") if adapter.get("matched") else ""
    initramfs_ok = bool(initramfs and expected_initramfs and initramfs == expected_initramfs and (kernel_images or initramfs_images))
    checks.append(_check("kernel_initramfs_handling_correct", STATUS_PASS if initramfs_ok else STATUS_UNKNOWN,
                         f"Detected mechanism={initramfs or 'unknown'}, adapter expectation={expected_initramfs or 'unknown'}, kernels={len(kernel_images)}, initramfs={len(initramfs_images)}."))
    checks.append(_check("filesystem_preservation_correct", STATUS_RUNTIME, "Must be compared against the rebuilt output; source analysis is insufficient."))
    checks.append(_check("unknown_custom_content_preserved", STATUS_RUNTIME, "Must be compared against the rebuilt output; unknown content is preservation-first."))
    checks.append(_check("iso_rebuild_succeeds", STATUS_RUNTIME, "Requires an actual rebuild when the plan requires one."))
    checks.append(_check("bios_boot_preserved", STATUS_RUNTIME if bool(data.get("bios_boot")) else STATUS_NA,
                         "Source advertises BIOS boot; output boot must be tested." if data.get("bios_boot") else "Source did not advertise BIOS boot."))
    checks.append(_check("uefi_boot_preserved", STATUS_RUNTIME if bool(data.get("uefi_boot")) else STATUS_NA,
                         "Source advertises UEFI boot; output boot must be tested." if data.get("uefi_boot") else "Source did not advertise UEFI boot."))
    checks.append(_check("rootfs_contains_staged_modifications", STATUS_RUNTIME, "Requires inspection of the produced rootfs."))
    checks.append(_check("no_unintended_modifications", STATUS_RUNTIME, "Requires output/source and intended-plan comparison."))
    checks.append(_check("diagnostics_available", STATUS_PASS, "Part 8 acceptance framework can export inspectable diagnostics metadata."))
    checks.append(_check("output_checksum_generated", STATUS_RUNTIME, "Requires the produced output artifact and its SHA-256."))

    static_ids = {"source_iso_readable", "distribution_detected", "boot_architecture_detected", "rootfs_detected"}
    status_by_id = {row["id"]: row["status"] for row in checks}
    static_ok = all(status_by_id.get(cid) == STATUS_PASS for cid in static_ids)
    if adapter.get("matched") and package_format not in {"", "unknown"} and package_format != str(adapter.get("package_format") or ""):
        static_ok = False
    checks.append(_check("static_validation_passes", STATUS_PASS if static_ok else STATUS_UNKNOWN,
                         "Core static source gates passed; this is not runtime verification." if static_ok else "One or more core static source gates remain unverified."))
    checks.append(_check("manual_runtime_test_passes", STATUS_MANUAL, "Manual/VM/hardware runtime acceptance remains required where applicable."))

    state = STATIC_READY if static_ok else STATIC_INCOMPLETE
    record = {
        "schema": ACCEPTANCE_SCHEMA,
        "kind": "chromapress-cross-distro-acceptance",
        "gate": PART8_GATE,
        "source_sha256": source_sha,
        "source": {
            "distribution": str(data.get("distribution") or ""),
            "version": str(data.get("version") or ""),
            "architecture": arch,
            "package_format": package_format,
            "rootfs_layers": len(roots),
            "bios_boot": bool(data.get("bios_boot")),
            "uefi_boot": bool(data.get("uefi_boot")),
        },
        "adapter": adapter,
        "checks": checks,
        "verification_state": state,
        "analysis_only": True,
        "verified": False,
        "source_read_only": True,
        "acceptance_fingerprint": "",
    }
    base = deepcopy(record); base.pop("acceptance_fingerprint", None)
    record["acceptance_fingerprint"] = _digest(base)
    return record


def validate_acceptance_record(record: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(record, dict) or record.get("schema") != ACCEPTANCE_SCHEMA or record.get("kind") != "chromapress-cross-distro-acceptance":
        return False, "Unsupported Part 8 acceptance schema."
    if not _valid_sha(record.get("source_sha256")):
        return False, "Acceptance record is not locked to a valid source SHA-256."
    checks = record.get("checks")
    if not isinstance(checks, list) or {str(x.get("id")) for x in checks if isinstance(x, dict)} != {x["id"] for x in CHECK_DEFS}:
        return False, "Acceptance checklist is incomplete or malformed."
    if record.get("source_read_only") is not True:
        return False, "Acceptance must preserve the source ISO read-only."
    supplied = str(record.get("acceptance_fingerprint") or "").lower()
    if not _valid_sha(supplied):
        return False, "Acceptance fingerprint is missing or invalid."
    base = deepcopy(record); base.pop("acceptance_fingerprint", None)
    if _digest(base) != supplied:
        return False, "Acceptance fingerprint mismatch; evidence may have been modified."
    if record.get("analysis_only") is True and (record.get("verified") is True or record.get("verification_state") == VERIFIED):
        return False, "Analysis-only evidence must never claim VERIFIED."
    return True, "Part 8 acceptance schema, source lock, checklist and fingerprint passed."


def apply_runtime_results(record: dict[str, Any], results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ok, message = validate_acceptance_record(record)
    if not ok:
        raise ValueError(message)
    out = deepcopy(record)
    runtime_ids = {x["id"] for x in CHECK_DEFS if x["kind"] in {"evidence", "runtime", "conditional-runtime", "manual"}}
    rows = {row["id"]: row for row in out["checks"]}
    for check_id, result in results.items():
        if check_id not in runtime_ids or check_id not in rows:
            raise ValueError(f"{check_id} is not an explicit-evidence/runtime Part 8 acceptance gate.")
        status = str(result.get("status") or "").upper()
        evidence = str(result.get("evidence") or "").strip()
        if status not in {STATUS_PASS, STATUS_NA, STATUS_BLOCKED}:
            raise ValueError(f"Unsupported runtime status for {check_id}.")
        if status == STATUS_PASS and not evidence:
            raise ValueError(f"Runtime PASS for {check_id} requires explicit evidence.")
        rows[check_id]["status"] = status
        rows[check_id]["evidence"] = evidence or rows[check_id]["evidence"]

    all_ok = all(row["status"] in {STATUS_PASS, STATUS_NA} for row in out["checks"])
    out["analysis_only"] = False
    out["verified"] = bool(all_ok)
    out["verification_state"] = VERIFIED if all_ok else STATIC_READY
    out["acceptance_fingerprint"] = ""
    base = deepcopy(out); base.pop("acceptance_fingerprint", None)
    out["acceptance_fingerprint"] = _digest(base)
    return out


def diagnostics_payload(record: dict[str, Any]) -> dict[str, Any]:
    ok, message = validate_acceptance_record(record)
    if not ok:
        raise ValueError(message)
    # Do not include source path, credentials or environment details. The payload
    # is intentionally inspectable and shareable.
    payload = {
        "schema": 1,
        "kind": "chromapress-part8-diagnostics",
        "source_sha256": record["source_sha256"],
        "source": deepcopy(record["source"]),
        "adapter": deepcopy(record["adapter"]),
        "verification_state": record["verification_state"],
        "verified": bool(record["verified"]),
        "checks": deepcopy(record["checks"]),
        "acceptance_fingerprint": record["acceptance_fingerprint"],
    }
    def secret_paths(value: Any, path: str = "") -> list[str]:
        hits: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                here = f"{path}.{key}" if path else str(key)
                if _SECRET.search(str(key)) and item not in (None, "", False, [], {}):
                    hits.append(here)
                hits.extend(secret_paths(item, here))
        elif isinstance(value, list):
            for i, item in enumerate(value): hits.extend(secret_paths(item, f"{path}[{i}]"))
        return hits
    hits = secret_paths(payload)
    if hits:
        raise ValueError("Diagnostics export blocked because secret-like fields were found: " + ", ".join(hits[:5]))
    payload["diagnostics_fingerprint"] = _digest(payload)
    return payload


def save_diagnostics(record: dict[str, Any], path: Path) -> None:
    payload = diagnostics_payload(record)
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Part 8 diagnostics must be exported as .json.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def acceptance_summary(record: dict[str, Any]) -> str:
    ok, message = validate_acceptance_record(record)
    if not ok:
        return "BLOCKED — " + message
    counts: dict[str, int] = {}
    for row in record["checks"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    adapter = record["adapter"]
    target = adapter.get("label") or record["source"].get("distribution") or "Unknown Linux"
    return (
        f"{record['verification_state']} — {target} • priority {adapter.get('priority','UNCLASSIFIED')} • "
        f"PASS {counts.get(STATUS_PASS,0)} • runtime {counts.get(STATUS_RUNTIME,0)} • manual {counts.get(STATUS_MANUAL,0)} • "
        f"unknown {counts.get(STATUS_UNKNOWN,0)}. Analysis alone never marks a distro VERIFIED."
    )
