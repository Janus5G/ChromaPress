from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any
import json
import re

from chromapress.models import ChangeItem, ChangeKind

PART6_GATE = "part6-complete"
PROJECT_MANIFEST = "chromapress-app.json"
_MAX_FILES = 200
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_PROJECT_BYTES = 12 * 1024 * 1024

_FILE_HEADER = re.compile(r"(?m)^---\s+([^\r\n]+?)\s+---\s*$")
_SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@/-]{0,127}$")
_SAFE_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?im)\b(api[_-]?key|access[_-]?token|secret|password|passwd|bearer[_-]?token)\b\s*[:=]\s*[\"']([^\"'\r\n]{12,})[\"']"
)
_SAFE_SECRET_WORDS = ("placeholder", "example", "dummy", "changeme", "replace_me", "redacted", "your_", "test", "fake", "none", "null", "env", "${", "<")


@dataclass(frozen=True)
class ProjectFile:
    path: str
    content: str

    @property
    def size(self) -> int:
        return len(self.content.encode("utf-8"))

    @property
    def digest(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()


def _safe_rel_path(raw: str) -> str:
    value = str(raw or "").strip().replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"unsafe generated project path: {raw}")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe generated project path: {raw}")
    if len(path.parts) > 20 or len(value) > 240:
        raise ValueError(f"generated project path is too deep/long: {raw}")
    return path.as_posix()


def parse_generated_project(text: str) -> list[ProjectFile]:
    """Parse the explicit `--- path ---` project envelope returned by providers.

    No path is written to disk here. The result remains an inspectable in-memory
    project until the user explicitly stages it.
    """
    raw = str(text or "")
    matches = list(_FILE_HEADER.finditer(raw))
    if not matches:
        raise ValueError("generated response contains no explicit project file separators")
    if raw[: matches[0].start()].strip():
        raise ValueError("generated response contains unscoped text before the first project file")
    if len(matches) > _MAX_FILES:
        raise ValueError(f"generated project exceeds the {_MAX_FILES}-file safety limit")
    files: list[ProjectFile] = []
    seen: set[str] = set()
    total = 0
    for index, match in enumerate(matches):
        path = _safe_rel_path(match.group(1))
        if path in seen:
            raise ValueError(f"duplicate generated project path: {path}")
        seen.add(path)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        content = raw[start:end]
        if content.startswith("\r\n"):
            content = content[2:]
        elif content.startswith("\n"):
            content = content[1:]
        content = content.rstrip("\r\n") + "\n"
        size = len(content.encode("utf-8"))
        if size > _MAX_FILE_BYTES:
            raise ValueError(f"generated file exceeds 2 MiB safety limit: {path}")
        total += size
        if total > _MAX_PROJECT_BYTES:
            raise ValueError("generated project exceeds 12 MiB safety limit")
        files.append(ProjectFile(path, content))
    return files


def _manifest(files: list[ProjectFile]) -> dict[str, Any]:
    item = next((f for f in files if f.path == PROJECT_MANIFEST), None)
    if item is None:
        raise ValueError(f"generated project must include {PROJECT_MANIFEST}")
    try:
        data = json.loads(item.content)
    except Exception as exc:
        raise ValueError(f"{PROJECT_MANIFEST} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{PROJECT_MANIFEST} must contain a JSON object")
    return data


def _string_list(value: Any, field: str, *, service_names: bool = False) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"manifest field {field} must be a list")
    out: list[str] = []
    pattern = _SAFE_SERVICE if service_names else None
    for item in value:
        text = str(item or "").strip()
        if not text or len(text) > 240 or any(ch in text for ch in ("\x00", "\r", "\n")):
            raise ValueError(f"manifest field {field} contains an invalid value")
        if pattern and not pattern.fullmatch(text):
            raise ValueError(f"manifest field {field} contains an unsafe service name: {text}")
        out.append(text)
    return out


def _packages(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("manifest field packages must be a list")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            name, reason = item.strip(), "AI App Studio dependency"
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            reason = str(item.get("reason") or "AI App Studio dependency").strip()
        else:
            raise ValueError("manifest packages entries must be strings or objects")
        if not _SAFE_PACKAGE.fullmatch(name):
            raise ValueError(f"unsafe package dependency name: {name}")
        if name not in seen:
            out.append({"name": name, "reason": reason[:240]})
            seen.add(name)
    return out


def _command_block(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"manifest field {field} must be an object")
    command = str(value.get("command") or "").strip()
    if not command or len(command) > 1000 or "\x00" in command:
        raise ValueError(f"manifest {field}.command is required")
    return {
        "command": command,
        "requires_network": bool(value.get("requires_network", False)),
        "working_directory": _safe_rel_path(str(value.get("working_directory") or ".").replace(".", "project", 1)) if str(value.get("working_directory") or ".") != "." else ".",
    }


def validate_manifest(data: dict[str, Any], files: list[ProjectFile]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    version = str(data.get("version") or "").strip()
    entrypoint = _safe_rel_path(str(data.get("entrypoint") or ""))
    if not name or len(name) > 120:
        raise ValueError("manifest application name is required")
    if not version or len(version) > 80:
        raise ValueError("manifest application version is required")
    if entrypoint not in {f.path for f in files}:
        raise ValueError("manifest entrypoint does not exist in generated project")
    build = _command_block(data.get("build"), "build")
    test = _command_block(data.get("test"), "test")
    security = _string_list(data.get("security_implications"), "security_implications")
    return {
        "name": name,
        "version": version,
        "entrypoint": entrypoint,
        "packages": _packages(data.get("packages")),
        "services": _string_list(data.get("services"), "services", service_names=True),
        "permissions": _string_list(data.get("permissions"), "permissions"),
        "autostart": _string_list(data.get("autostart"), "autostart"),
        "desktop_integration": _string_list(data.get("desktop_integration"), "desktop_integration"),
        "security_implications": security,
        "build": build,
        "test": test,
    }


def scan_generated_secrets(files: list[ProjectFile], generation_credential: str = "") -> list[str]:
    findings: list[str] = []
    exact = str(generation_credential or "").strip()
    for item in files:
        if exact and len(exact) >= 8 and exact in item.content:
            findings.append(f"{item.path}: generation credential appears in generated source")
        for match in _SECRET_ASSIGNMENT.finditer(item.content):
            value = match.group(2).strip().casefold()
            if not any(marker in value for marker in _SAFE_SECRET_WORDS):
                findings.append(f"{item.path}: possible embedded {match.group(1)}")
                break
        if ("-----BEGIN " + "PRIVATE KEY-----") in item.content:
            findings.append(f"{item.path}: private key material")
    return findings


def review_generated_project(text: str, *, generation_credential: str = "") -> dict[str, Any]:
    files = parse_generated_project(text)
    manifest = validate_manifest(_manifest(files), files)
    secrets = scan_generated_secrets(files, generation_credential)
    fingerprints = scan_chromapress_fingerprint(files)
    errors = list(secrets) + list(fingerprints)
    metadata = [{"path": f.path, "size": f.size, "sha256": f.digest} for f in files]
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "warnings": [
            "Build and test commands are plans only; execute them later in an explicitly reviewed isolated build environment.",
            "Security review is static and does not replace human code review.",
        ],
        "manifest": manifest,
        "files": metadata,
        "project_files": [{"path": f.path, "content": f.content, "sha256": f.digest, "size": f.size} for f in files],
        "file_count": len(files),
        "project_sha256": sha256("".join(f"{f.path}\0{f.digest}\n" for f in files).encode("utf-8")).hexdigest(),
    }



def scan_chromapress_fingerprint(files: list[ProjectFile]) -> list[str]:
    """Reject ChromaPress fingerprints from deployable generated-app files.

    The control manifest is internal review metadata and is deliberately excluded.
    Generated applications should be neutral unless a future explicit user option
    intentionally adds attribution.
    """
    findings: list[str] = []
    for item in files:
        if item.path == PROJECT_MANIFEST:
            continue
        if "chromapress" in item.path.casefold() or "chromapress" in item.content.casefold():
            findings.append(f"{item.path}: ChromaPress fingerprint is not allowed in deployable output")
    return findings


def deployable_project_files(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only files that may be shipped with the generated application.

    Internal ChromaPress review/control files never cross this boundary.
    """
    rows = []
    reconstructed: list[ProjectFile] = []
    for row in list(review.get("project_files") or []):
        path = _safe_rel_path(str(row.get("path") or ""))
        if path == PROJECT_MANIFEST:
            continue
        content = str(row.get("content") or "")
        digest = sha256(content.encode("utf-8")).hexdigest()
        if digest != str(row.get("sha256") or ""):
            raise ValueError(f"generated project file hash mismatch: {path}")
        item = ProjectFile(path, content)
        reconstructed.append(item)
        rows.append({"path": path, "content": content, "sha256": digest, "size": item.size})
    findings = scan_chromapress_fingerprint(reconstructed)
    if findings:
        raise ValueError(findings[0])
    if not rows:
        raise ValueError("generated application has no deployable project files")
    return rows

def target_context_from_source(source: Any, scenario_label: str = "", scenario_context: str = "") -> dict[str, Any]:
    desktop = dict(getattr(source, "part5_desktop_evidence", {}) or {})
    package_format = str(getattr(source, "package_format", "") or "unknown")
    manager = {"deb": "apt/dpkg", "rpm": "dnf/rpm", "pkg.tar": "pacman"}.get(package_format.casefold(), "unknown")
    libraries: list[str] = []
    for row in list(getattr(source, "system_package_evidence", []) or []):
        if isinstance(row, dict):
            name = str(row.get("package") or "").strip()
            if name and name not in libraries:
                libraries.append(name)
    return {
        "distribution": str(getattr(source, "distribution", "") or "unknown"),
        "version": str(getattr(source, "version", "") or "unknown"),
        "architecture": str(getattr(source, "architecture", "") or "unknown"),
        "desktop": str(desktop.get("active_desktop") or "unknown"),
        "package_format": package_format,
        "package_manager": manager,
        "available_libraries": libraries[:120],
        "installer_type": str(getattr(source, "installer", "") or "unknown"),
        "source_sha256": str(getattr(source, "sha256", "") or "").strip().casefold(),
        "scenario": scenario_label,
        "scenario_context": scenario_context,
    }


def validate_target_context(context: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(context, dict):
        return False, "Target Linux context is missing."
    source_sha = str(context.get("source_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        return False, "Analyze a source ISO before staging an AI-generated application."
    for key in ("distribution", "version", "architecture", "desktop", "package_manager", "installer_type"):
        if not str(context.get(key) or "").strip():
            return False, f"Target Linux context is missing {key}."
    if not isinstance(context.get("available_libraries"), list):
        return False, "Target Linux library context is invalid."
    return True, "Target Linux context is source-hash bound."


def dependency_change_items(review: dict[str, Any], target_context: dict[str, Any], project_id: str) -> list[ChangeItem]:
    manager = {"deb": "apt", "rpm": "dnf", "pkg.tar": "pacman"}.get(str(target_context.get("package_format") or "").casefold(), "repository")
    out: list[ChangeItem] = []
    for dep in review.get("manifest", {}).get("packages", []):
        out.append(ChangeItem(
            f"AI app dependency: {dep['name']}",
            ChangeKind.PACKAGE_REPOSITORY,
            dep.get("reason") or "AI App Studio dependency",
            {
                "package": dep["name"], "manager": manager, "source": "ai_app_dependency",
                "ai_project_id": project_id, "part": 6, "stage_only": True,
            },
        ))
    return out


def ai_app_payload(review: dict[str, Any], target_context: dict[str, Any], *, provider: str, model: str, toolchain: str, prompt: str, human_review_acknowledged: bool = False) -> dict[str, Any]:
    ok, message = validate_target_context(target_context)
    if not ok:
        raise ValueError(message)
    if review.get("status") != "PASS":
        raise ValueError("Generated project must pass inspection before staging.")
    if human_review_acknowledged is not True:
        raise ValueError("Human review must be explicitly acknowledged before staging.")
    prompt_text = str(prompt or "")
    project_id = str(review.get("project_sha256") or "")[:24]
    manifest = dict(review.get("manifest") or {})
    deployment_files = deployable_project_files(review)
    return {
        "config_type": "part6_ai_app_project",
        "part": 6,
        "gate_version": PART6_GATE,
        "source_sha256": target_context["source_sha256"],
        "provider": str(provider or ""),
        "model": str(model or ""),
        "toolchain": str(toolchain or "Auto"),
        "prompt_sha256": sha256(prompt_text.encode("utf-8")).hexdigest(),
        "prompt_body_staged": False,
        "generation_credential_staged": False,
        "runtime_credential_staged": False,
        "generation_and_runtime_credentials_separate": True,
        "credential_storage_policy": "generation_session_only",
        "target_context": dict(target_context),
        "project_id": project_id,
        "project_sha256": review["project_sha256"],
        "project_files": list(review.get("project_files") or []),
        "file_count": int(review.get("file_count") or 0),
        "deployable_project_files": deployment_files,
        "deployable_file_count": len(deployment_files),
        "internal_control_files": [PROJECT_MANIFEST],
        "internal_control_files_deployed": False,
        "generated_output_fingerprint_policy": "neutral_no_chromapress_markers",
        "generated_output_telemetry": False,
        "generated_output_shared_chromapress_runtime": False,
        "manifest": manifest,
        "files_reviewed": True,
        "human_review_acknowledged": True,
        "dependency_review_required": True,
        "security_review_required": True,
        "build_review_required": True,
        "test_review_required": True,
        "build_test_execution_policy": "isolated_explicit_user_action_required",
        "never_blindly_inject": True,
        "requires_human_review_before_apply": True,
        "apply_blocked_until_build_test_security_dependency_gates_pass": True,
        "source_read_only": True,
        "preserve_unrelated": True,
        "stage_only": True,
    }


def validate_ai_app_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if str(payload.get("config_type") or "") != "part6_ai_app_project" or str(payload.get("gate_version") or "") != PART6_GATE:
        return False, "Part 6 AI application payload schema/gate is invalid."
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("source_sha256") or "")):
        return False, "Part 6 AI application is not locked to a source SHA-256."
    ok, msg = validate_target_context(dict(payload.get("target_context") or {}))
    if not ok:
        return False, msg
    if str(payload.get("target_context", {}).get("source_sha256") or "") != str(payload.get("source_sha256") or ""):
        return False, "Part 6 target context does not match the source SHA-256."
    for key in ("generation_credential_staged", "runtime_credential_staged", "prompt_body_staged"):
        if payload.get(key) is not False:
            return False, f"Part 6 secret/privacy invariant failed: {key} must be false."
    if payload.get("generation_and_runtime_credentials_separate") is not True or payload.get("credential_storage_policy") != "generation_session_only":
        return False, "Generation and runtime credentials must remain separate and generation credentials session-only."
    if payload.get("human_review_acknowledged") is not True:
        return False, "AI-generated projects require explicit human-review acknowledgement before staging."
    if payload.get("never_blindly_inject") is not True or payload.get("requires_human_review_before_apply") is not True:
        return False, "AI-generated projects must remain inspectable and human-reviewed before apply."
    if payload.get("apply_blocked_until_build_test_security_dependency_gates_pass") is not True:
        return False, "Build/test/security/dependency gates must block apply."
    if payload.get("source_read_only") is not True or payload.get("preserve_unrelated") is not True or payload.get("stage_only") is not True:
        return False, "Part 6 AI application must remain preservation-first and staging-only."
    if payload.get("internal_control_files_deployed") is not False:
        return False, "Internal ChromaPress control files must never be deployed with generated applications."
    if payload.get("generated_output_fingerprint_policy") != "neutral_no_chromapress_markers":
        return False, "Generated application output must use the neutral no-ChromaPress-fingerprint policy."
    if payload.get("generated_output_telemetry") is not False or payload.get("generated_output_shared_chromapress_runtime") is not False:
        return False, "Generated applications must not receive ChromaPress telemetry or a shared ChromaPress runtime."
    deployable = payload.get("deployable_project_files")
    if not isinstance(deployable, list) or not deployable:
        return False, "Part 6 AI application has no deployable output file set."
    deployable_paths: set[str] = set()
    deployable_reconstructed: list[ProjectFile] = []
    for row in deployable:
        if not isinstance(row, dict):
            return False, "Part 6 deployable project file metadata is invalid."
        try:
            path = _safe_rel_path(str(row.get("path") or ""))
        except ValueError as exc:
            return False, str(exc)
        if path == PROJECT_MANIFEST:
            return False, "Internal ChromaPress manifest must not be present in deployable output."
        content = str(row.get("content") or "")
        digest = sha256(content.encode("utf-8")).hexdigest()
        if digest != str(row.get("sha256") or ""):
            return False, f"Part 6 deployable project file hash mismatch: {path}"
        deployable_paths.add(path)
        deployable_reconstructed.append(ProjectFile(path, content))
    if scan_chromapress_fingerprint(deployable_reconstructed):
        return False, "Generated application contains a ChromaPress fingerprint in deployable output."
    files = payload.get("project_files")
    if not isinstance(files, list) or not files:
        return False, "Part 6 AI application has no inspectable project files."
    reconstructed: list[ProjectFile] = []
    for row in files:
        if not isinstance(row, dict):
            return False, "Part 6 project file metadata is invalid."
        try:
            path = _safe_rel_path(str(row.get("path") or ""))
        except ValueError as exc:
            return False, str(exc)
        content = str(row.get("content") or "")
        digest = sha256(content.encode("utf-8")).hexdigest()
        if digest != str(row.get("sha256") or ""):
            return False, f"Part 6 project file hash mismatch: {path}"
        reconstructed.append(ProjectFile(path, content))
    if scan_generated_secrets(reconstructed):
        return False, "Part 6 project contains possible embedded credential/private-key material."
    expected_deployable = {f.path for f in reconstructed if f.path != PROJECT_MANIFEST}
    if deployable_paths != expected_deployable:
        return False, "Deployable project file set does not exactly match reviewed non-control files."
    try:
        validate_manifest(dict(payload.get("manifest") or {}), reconstructed)
    except ValueError as exc:
        return False, str(exc)
    return True, "Part 6 AI app is source-hash bound, inspectable, credential-separated, dependency/security/build/test gated and staging-only."
