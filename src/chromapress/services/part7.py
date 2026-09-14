from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import json
import re

from chromapress.models import ChangeItem, ChangeKind, ChangeStatus, ProjectState

PART7_GATE = "part7-complete"
PROFILE_SCHEMA = 1
BUILD_PLAN_SCHEMA = 1
COMPRESSION_CHOICES = ("preserve", "xz", "zstd", "gzip", "lz4", "lzo")
VERIFICATION_POLICIES = ("sha256", "sha256_boot_structure", "strict_runtime_required")
HOOK_PHASES = ("pre_build", "post_build", "pre_verify", "post_verify")
HOOK_INTERPRETERS = ("bash", "sh", "python3")
_SECRET_KEY = re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd|bearer[_-]?token|private[_-]?key)")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,79}$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.iso$", re.I)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _contains_secret_key(value: Any, path: str = "") -> list[str]:
    """Find actual persisted secret-like values without flagging safety metadata.

    ChromaPress carries many booleans such as ``secret_read=False`` and policy
    fields such as ``password_policy``. Those are evidence, not credentials.
    """
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_s = str(key); lower = key_s.casefold()
            here = f"{path}.{key_s}" if path else key_s
            if _SECRET_KEY.search(key_s):
                metadata = any(token in lower for token in ("policy", "read", "staged", "included", "contains", "required", "redact", "leak", "secret_material"))
                empty = item in (None, "", False) or item == [] or item == {}
                placeholder = isinstance(item, str) and any(token in item.casefold() for token in ("placeholder", "redacted", "example", "dummy", "changeme", "replace_me", "${", "<secret", "<password"))
                if not (metadata or empty or placeholder):
                    hits.append(here)
            hits.extend(_contains_secret_key(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_contains_secret_key(item, f"{path}[{index}]"))
    return hits


def _change_record(change: ChangeItem) -> dict[str, Any]:
    # IDs/timestamps/test status are deliberately excluded: a reusable profile
    # describes intended configuration, not one historical UI instance.
    return {
        "title": str(change.title),
        "kind": change.kind.value,
        "detail": str(change.detail),
        "payload": deepcopy(change.payload),
    }


def plan_changes(project: ProjectState) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for change in project.changes:
        # A production build plan must never recursively capture itself.
        if change.kind == ChangeKind.CONFIG and str(change.payload.get("config_type") or "") == "part7_production_build_plan":
            continue
        out.append(_change_record(change))
    return out


def source_identity(project: ProjectState) -> dict[str, Any]:
    source = project.source
    return {
        "sha256": str(source.sha256 or "").strip().lower(),
        "distribution": str(source.distribution or ""),
        "version": str(source.version or ""),
        "architecture": str(source.architecture or ""),
        "installer": str(source.installer or ""),
        "package_format": str(source.package_format or ""),
        "volume_id": str(source.volume_id or ""),
    }


def create_profile(project: ProjectState, name: str, production: dict[str, Any] | None = None) -> dict[str, Any]:
    name = str(name or "").strip()
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError("Profile name must be 1-80 safe printable characters.")
    source = source_identity(project)
    if not _SHA256.fullmatch(source["sha256"]):
        raise ValueError("A verified source SHA-256 is required before a reusable profile can be created.")
    changes = plan_changes(project)
    profile = {
        "schema": PROFILE_SCHEMA,
        "kind": "chromapress-customization-profile",
        "name": name,
        "scenario": str(project.scenario or ""),
        "source": source,
        "changes": changes,
        "production": deepcopy(production or {}),
        "secret_material_included": False,
        "profile_fingerprint": "",
    }
    hits = _contains_secret_key(profile)
    if hits:
        raise ValueError("Profile export blocked because secret-like fields were found: " + ", ".join(hits[:6]))
    fingerprint_base = dict(profile)
    fingerprint_base.pop("profile_fingerprint", None)
    profile["profile_fingerprint"] = _digest(fingerprint_base)
    return profile


def validate_profile(profile: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(profile, dict) or profile.get("schema") != PROFILE_SCHEMA or profile.get("kind") != "chromapress-customization-profile":
        return False, "Unsupported or invalid ChromaPress profile schema."
    if not _SAFE_NAME.fullmatch(str(profile.get("name") or "")):
        return False, "Profile name is invalid."
    source = profile.get("source")
    if not isinstance(source, dict) or not _SHA256.fullmatch(str(source.get("sha256") or "").lower()):
        return False, "Profile is not locked to a valid source SHA-256."
    changes = profile.get("changes")
    if not isinstance(changes, list) or len(changes) > 1000:
        return False, "Profile change plan is invalid or unreasonably large."
    for row in changes:
        if not isinstance(row, dict):
            return False, "Profile contains a malformed change record."
        try:
            ChangeKind(str(row.get("kind") or ""))
        except Exception:
            return False, "Profile contains an unsupported change kind."
        if not isinstance(row.get("payload"), dict):
            return False, "Profile change payload must be an object."
    hits = _contains_secret_key(profile)
    if hits:
        return False, "Profile contains secret-like fields and cannot be imported."
    if profile.get("secret_material_included") is not False:
        return False, "Profile must explicitly state that secret material is excluded."
    supplied = str(profile.get("profile_fingerprint") or "").lower()
    if not _SHA256.fullmatch(supplied):
        return False, "Profile fingerprint is missing or invalid."
    base = deepcopy(profile); base.pop("profile_fingerprint", None)
    if _digest(base) != supplied:
        return False, "Profile fingerprint mismatch; the profile may have been modified."
    return True, "Profile schema, source lock, change records, secret exclusion and fingerprint passed."


def save_profile(profile: dict[str, Any], path: Path) -> None:
    ok, message = validate_profile(profile)
    if not ok:
        raise ValueError(message)
    path = Path(path)
    if path.suffix.lower() not in {".json", ".chromapress-profile"}:
        raise ValueError("Profiles must use .json or .chromapress-profile.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")


def load_profile(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ok, message = validate_profile(data)
    if not ok:
        raise ValueError(message)
    return data


def profile_change_items(profile: dict[str, Any], current_source_sha256: str) -> list[ChangeItem]:
    ok, message = validate_profile(profile)
    if not ok:
        raise ValueError(message)
    expected = str(profile["source"]["sha256"]).lower()
    actual = str(current_source_sha256 or "").strip().lower()
    if actual != expected:
        raise ValueError("Profile source SHA-256 does not match the currently selected ISO.")
    items: list[ChangeItem] = []
    for row in profile["changes"]:
        items.append(ChangeItem(
            title=str(row.get("title") or "Imported change"),
            kind=ChangeKind(str(row["kind"])),
            detail=str(row.get("detail") or "Imported from verified ChromaPress profile"),
            payload=deepcopy(row.get("payload") or {}),
        ))
    return items


def compare_sources(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    keys = ("sha256", "distribution", "version", "architecture", "installer", "package_format", "volume_id")
    diffs = {key: {"left": a.get(key), "right": b.get(key)} for key in keys if a.get(key) != b.get(key)}
    return {"same": not diffs, "differences": diffs}


def compare_change_plans(left: Iterable[dict[str, Any]], right: Iterable[dict[str, Any]]) -> dict[str, Any]:
    a = list(left); b = list(right)
    a_map = {_digest(row): row for row in a}; b_map = {_digest(row): row for row in b}
    return {
        "same": set(a_map) == set(b_map),
        "left_count": len(a), "right_count": len(b),
        "removed": [a_map[d] for d in sorted(set(a_map) - set(b_map))],
        "added": [b_map[d] for d in sorted(set(b_map) - set(a_map))],
    }


def diff_profiles(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    for profile in (left, right):
        ok, message = validate_profile(profile)
        if not ok:
            raise ValueError(message)
    return {
        "same": left["profile_fingerprint"] == right["profile_fingerprint"],
        "source": compare_sources(left["source"], right["source"]),
        "changes": compare_change_plans(left["changes"], right["changes"]),
        "scenario": {"left": left.get("scenario"), "right": right.get("scenario"), "same": left.get("scenario") == right.get("scenario")},
        "production_same": left.get("production") == right.get("production"),
    }


def _config_changes(project: ProjectState, config_type: str) -> list[ChangeItem]:
    return [c for c in project.changes if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type") or "") == config_type]


def available_production_presets(project: ProjectState) -> list[dict[str, str]]:
    """Expose named production presets only when their prerequisites are really staged."""
    kiosk_modes = {str(c.payload.get("mode") or "") for c in _config_changes(project, "part5_kiosk_session")}
    volatile = any(str(c.payload.get("integration_target") or "") == "volatile_overlay" for c in _config_changes(project, "runtime_integration"))
    restricted_session = bool(_config_changes(project, "restricted_session"))
    presets: list[dict[str, str]] = []
    if "browser_kiosk" in kiosk_modes and volatile:
        presets.append({"id": "immutable_browser_kiosk", "label": "Immutable Browser Kiosk"})
    if volatile and kiosk_modes.intersection({"browser_kiosk", "custom_application_kiosk", "restricted_desktop"}):
        presets.append({"id": "volatile_kiosk", "label": "Volatile Kiosk"})
    if "restricted_desktop" in kiosk_modes:
        presets.append({"id": "thin_client", "label": "Thin Client"})
    if "custom_application_kiosk" in kiosk_modes and restricted_session:
        presets.append({"id": "restricted_application_terminal", "label": "Restricted Application Terminal"})
    return presets


def make_expert_hook(path: Path, phase: str, interpreter: str, human_reviewed: bool) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ValueError("Expert hook script does not exist.")
    phase = str(phase or "")
    interpreter = str(interpreter or "")
    if phase not in HOOK_PHASES or interpreter not in HOOK_INTERPRETERS:
        raise ValueError("Unsupported expert hook phase or interpreter.")
    data = path.read_bytes()
    if len(data) > 1024 * 1024:
        raise ValueError("Expert hook exceeds the 1 MiB review limit.")
    return {
        "phase": phase,
        "interpreter": interpreter,
        "source_path": str(path),
        "sha256": sha256(data).hexdigest(),
        "human_reviewed": bool(human_reviewed),
        "execute_only_in_isolated_wsl_build_workspace": True,
        "may_bypass_preflight": False,
        "may_mutate_source_iso": False,
    }


def _safe_output_dir(value: str) -> bool:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in ("\x00", "\r", "\n")):
        return False
    return bool(re.match(r"^[A-Za-z]:[\\/].+", value) or value.startswith("/"))


def create_build_plan_payload(
    project: ProjectState, *, output_dir: str, output_name: str,
    compression: str = "preserve", verification_policy: str = "sha256_boot_structure",
    diagnostics_bundle: bool = True, preset_id: str = "", expert_hooks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = source_identity(project)
    if not _SHA256.fullmatch(source["sha256"]):
        raise ValueError("A verified source SHA-256 is required before production planning.")
    output_name = str(output_name or "").strip()
    output_dir = str(output_dir or "").strip()
    if not _SAFE_OUTPUT_NAME(output_name):
        raise ValueError("Output filename must be a safe .iso filename.")
    if not _safe_output_dir(output_dir):
        raise ValueError("Output location must be an absolute Windows or Linux path.")
    compression = str(compression or "")
    if compression not in COMPRESSION_CHOICES:
        raise ValueError("Unsupported compression choice.")
    verification_policy = str(verification_policy or "")
    if verification_policy not in VERIFICATION_POLICIES:
        raise ValueError("Unsupported verification policy.")
    presets = {p["id"] for p in available_production_presets(project)}
    if preset_id and preset_id not in presets:
        raise ValueError("Requested production preset is not backed by the currently staged capabilities.")
    hooks = deepcopy(expert_hooks or [])
    changes = plan_changes(project)
    payload = {
        "schema": BUILD_PLAN_SCHEMA,
        "part": 7,
        "gate_version": PART7_GATE,
        "config_type": "part7_production_build_plan",
        "source_sha256": source["sha256"],
        "source_path": str(project.source.path or ""),
        "source_read_only": True,
        "preserve_unrelated": True,
        "project_name": str(project.name or ""),
        "scenario": str(project.scenario or ""),
        "change_count": len(changes),
        "change_plan_fingerprint": _digest(changes),
        "output_dir": output_dir,
        "output_name": output_name,
        "overwrite_existing_output": False,
        "compression": compression,
        "verification_policy": verification_policy,
        "diagnostics_bundle": bool(diagnostics_bundle),
        "preset_id": str(preset_id or ""),
        "expert_hooks": hooks,
        "hooks_require_human_review": True,
        "hooks_execute_only_in_isolated_wsl_build_workspace": True,
        "hooks_may_bypass_chromapress_safety": False,
        "preflight_required": True,
        "build_plan_review_required": True,
        "output_path_review_required": True,
        "verification_required_after_build": True,
        "stage_only": True,
        "secret_material_included": False,
    }
    ok, message = validate_build_plan_payload(payload)
    if not ok:
        raise ValueError(message)
    return payload


def _SAFE_OUTPUT_NAME(value: str) -> bool:
    return bool(_SAFE_FILENAME.fullmatch(str(value or ""))) and "/" not in value and "\\" not in value


def validate_build_plan_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(payload, dict) or payload.get("schema") != BUILD_PLAN_SCHEMA or payload.get("part") != 7:
        return False, "Part 7 production plan schema is invalid."
    if payload.get("gate_version") != PART7_GATE or payload.get("config_type") != "part7_production_build_plan":
        return False, "Part 7 production plan gate identity is invalid."
    source_sha = str(payload.get("source_sha256") or "").lower()
    if not _SHA256.fullmatch(source_sha):
        return False, "Production build plan is not locked to a valid source SHA-256."
    if not _safe_output_dir(str(payload.get("output_dir") or "")) or not _SAFE_OUTPUT_NAME(str(payload.get("output_name") or "")):
        return False, "Production output path/name is unsafe or not absolute."
    if str(payload.get("compression") or "") not in COMPRESSION_CHOICES:
        return False, "Production compression choice is unsupported."
    if str(payload.get("verification_policy") or "") not in VERIFICATION_POLICIES:
        return False, "Production verification policy is unsupported."
    if not isinstance(payload.get("change_count"), int) or payload.get("change_count") < 0:
        return False, "Production change count is invalid."
    if not _SHA256.fullmatch(str(payload.get("change_plan_fingerprint") or "").lower()):
        return False, "Production change-plan fingerprint is invalid."
    hooks = payload.get("expert_hooks")
    if not isinstance(hooks, list):
        return False, "Expert hook plan must be a list."
    for hook in hooks:
        if not isinstance(hook, dict):
            return False, "Expert hook entry is malformed."
        if hook.get("phase") not in HOOK_PHASES or hook.get("interpreter") not in HOOK_INTERPRETERS:
            return False, "Expert hook phase/interpreter is unsupported."
        if not _SHA256.fullmatch(str(hook.get("sha256") or "").lower()):
            return False, "Expert hook is not SHA-256 locked."
        if hook.get("human_reviewed") is not True:
            return False, "Every Expert hook requires explicit human review."
        if hook.get("execute_only_in_isolated_wsl_build_workspace") is not True or hook.get("may_bypass_preflight") is not False or hook.get("may_mutate_source_iso") is not False:
            return False, "Expert hooks may not bypass ChromaPress safety or mutate the source ISO."
    required_true = (
        "source_read_only", "preserve_unrelated", "hooks_require_human_review",
        "hooks_execute_only_in_isolated_wsl_build_workspace", "preflight_required",
        "build_plan_review_required", "output_path_review_required", "verification_required_after_build", "stage_only",
    )
    if any(payload.get(key) is not True for key in required_true):
        return False, "Production build plan is missing mandatory preservation/review/verification gates."
    if payload.get("overwrite_existing_output") is not False or payload.get("hooks_may_bypass_chromapress_safety") is not False or payload.get("secret_material_included") is not False:
        return False, "Production plan must not overwrite implicitly, bypass safety, or include secrets."
    if _contains_secret_key(payload):
        return False, "Production build plan contains secret-like fields."
    src = re.sub(r"/+", "/", str(payload.get("source_path") or "").strip().replace("\\", "/")).casefold()
    out = re.sub(r"/+", "/", (str(payload.get("output_dir") or "").rstrip("\\/") + "/" + str(payload.get("output_name") or "")).replace("\\", "/")).casefold()
    if src and src == out:
        return False, "Production output may not overwrite the selected source ISO."
    return True, "Production plan is source-hash locked, output-bounded, hook-reviewed, preservation-first and verification-gated."


def production_change(payload: dict[str, Any]) -> ChangeItem:
    ok, message = validate_build_plan_payload(payload)
    if not ok:
        raise ValueError(message)
    return ChangeItem(
        "Production build plan", ChangeKind.CONFIG,
        f"{payload['output_name']} • {payload['compression']} • {payload['verification_policy']} • {payload['change_count']} staged change(s)",
        deepcopy(payload),
    )


def profile_summary_against_project(profile: dict[str, Any], project: ProjectState) -> dict[str, Any]:
    ok, message = validate_profile(profile)
    if not ok:
        raise ValueError(message)
    current_source = source_identity(project)
    current_changes = plan_changes(project)
    return {
        "source": compare_sources(profile["source"], current_source),
        "changes": compare_change_plans(profile["changes"], current_changes),
        "same_scenario": str(profile.get("scenario") or "") == str(project.scenario or ""),
        "profile_fingerprint": profile["profile_fingerprint"],
    }
