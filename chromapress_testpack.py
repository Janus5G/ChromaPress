#!/usr/bin/env python3
"""Run one consolidated ChromaPress Part test pack with fail-fast/resume semantics.

Each completed main Part owns one verified archive under testpack/partN_tests.zip.
Tests are unpacked only for the run and removed again afterwards. Pytest stepwise
stops at the first failure, and the next identical command resumes from that
checkpoint. After a successful resume, a clean full seal pass runs automatically.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

PASS = "TESTPACK_PASS"
FAIL = "TESTPACK_FAIL"
SKIP = "TESTPACK_SKIP"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(root: Path, part: int) -> dict[str, str]:
    p = root / "testpack" / f"part{part}_manifest.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in (data.get("files") or {}).items()}


def load_legacy_hashes(root: Path, part: int) -> dict[str, set[str]]:
    # Part 4 keeps the historical migration manifest. Later Parts may carry a
    # small part-specific legacy manifest so an interrupted generated test
    # directory from the immediately previous verified pack can be recovered
    # without accepting unknown user test files.
    p = root / "testpack" / ("legacy_manifest.json" if part == 4 else f"part{part}_legacy_manifest.json")
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for files in (data.get("accepted_legacy_sets") or {}).values():
        if not isinstance(files, dict):
            continue
        for rel, digest in files.items():
            out.setdefault(str(rel), set()).add(str(digest).lower())
    return out


def verify_bundle(root: Path, part: int) -> tuple[Path, str]:
    bundle = root / "testpack" / f"part{part}_tests.zip"
    sidecar = root / "testpack" / f"part{part}_tests.zip.sha256"
    if not bundle.is_file() or not sidecar.is_file():
        raise RuntimeError(f"Part {part} consolidated test bundle or SHA-256 sidecar is missing")
    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = sha256(bundle)
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
        raise RuntimeError(f"Part {part} test bundle SHA-256 mismatch: expected {expected}, got {actual}")
    return bundle, actual


def project_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    additions = [str(root / "src"), str(root)]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(additions + ([existing] if existing else []))
    return env


def _known_bundle_paths(root: Path) -> dict[str, str]:
    """Return verified manifest paths from all available Part bundles.

    This is used only for safe cleanup of temporary files left by an interrupted
    test-pack run.  It never makes another Part's tests part of the active run.
    """
    known: dict[str, str] = {}
    for manifest_path in sorted((root / "testpack").glob("part*_manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for rel, digest in (data.get("files") or {}).items():
            known[str(rel)] = str(digest).lower()
    return known


def safe_prepare_tests(root: Path, part: int, bundle: Path, manifest: dict[str, str], legacy_hashes: dict[str, set[str]]) -> tuple[list[Path], set[str], bool]:
    """Prepare only the active Part's files while preserving unrelated tests.

    A Part 4 run must not fail merely because valid Part 5 (or later) tests are
    present in ``tests/``.  Only paths owned by the active Part are validated
    for collision safety; unrelated files are left untouched and are excluded
    from collection/execution by explicit pytest path selection.
    """
    tests_dir = root / "tests"
    conflicts: list[str] = []
    preexisting_owned: set[str] = set()
    legacy_generated_marker = tests_dir / ".chromapress-testpack-generated"
    part_marker = tests_dir / f".chromapress-part{part}-testpack-generated"
    interrupted_generated = legacy_generated_marker.is_file() or part_marker.is_file()

    for rel, expected in manifest.items():
        if not (rel.startswith("tests/") and rel.endswith(".py")):
            continue
        path = root / rel
        if not path.is_file():
            continue
        preexisting_owned.add(rel)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        accepted_legacy = actual in legacy_hashes.get(rel, set())
        if actual != expected and not accepted_legacy:
            conflicts.append(f"modified existing test file owned by Part {part}: {rel}")

    if conflicts:
        raise RuntimeError("active Part test files were preserved because they do not match the verified test pack: " + "; ".join(conflicts[:8]))

    tests_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle, "r") as z:
        members = [n for n in z.namelist() if n in manifest and n.startswith("tests/") and n.endswith(".py")]
        for name in members:
            z.extract(name, root)
    part_marker.write_text("temporary; removed after test run\n", encoding="utf-8")
    test_paths = [root / rel for rel in manifest if rel.startswith("tests/") and rel.endswith(".py")]
    return test_paths, preexisting_owned, interrupted_generated


def cleanup_tests(root: Path, part: int, manifest: dict[str, str], preexisting_owned: set[str], interrupted_generated: bool) -> None:
    """Remove only files owned by the active Part; preserve all unrelated tests."""
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return
    part_marker = tests_dir / f".chromapress-part{part}-testpack-generated"
    if not part_marker.is_file():
        return

    for rel, expected in manifest.items():
        if not (rel.startswith("tests/") and rel.endswith(".py")):
            continue
        path = root / rel
        if not path.is_file():
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            continue
        # Files that existed before this run are preserved unless a prior
        # interrupted test-pack marker proves they were temporary generated files.
        if rel in preexisting_owned and not interrupted_generated:
            continue
        path.unlink(missing_ok=True)

    part_marker.unlink(missing_ok=True)

    # Retire the legacy generic marker once no verified bundle-owned test files
    # remain. Unknown/user tests never participate in this decision.
    legacy_marker = tests_dir / ".chromapress-testpack-generated"
    if legacy_marker.is_file():
        known = _known_bundle_paths(root)
        any_known_remaining = False
        for rel, expected in known.items():
            path = root / rel
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                any_known_remaining = True
                break
        if not any_known_remaining:
            legacy_marker.unlink(missing_ok=True)

    # Remove empty directories only; never remove unrelated files/assets.
    for d in sorted((p for p in tests_dir.rglob("*") if p.is_dir()), key=lambda x: len(x.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    try:
        tests_dir.rmdir()
    except OSError:
        pass


def parse_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for key in list(counts):
        singular = key[:-1] if key.endswith("s") else key
        matches = list(re.finditer(rf"(\d+)\s+{singular}(?:s)?\b", output))
        if matches:
            counts[key] = int(matches[-1].group(1))
    return counts


def first_failure_node(output: str) -> str:
    for pat in (r"^(tests[\\/][^\s]+::[^\s]+)\s+FAILED\b", r"^_+\s+([^\s]+)\s+_+$"):
        m = re.search(pat, output, re.M)
        if m:
            return m.group(1).replace("\\", "/")
    return "unknown"


def _pytest_targets(root: Path, test_paths: list[Path]) -> list[str]:
    return [str(path.relative_to(root)) for path in test_paths]


def collect_nodes(root: Path, cache_dir: Path, env: dict[str, str], test_paths: list[Path]) -> tuple[list[str], str, int]:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", f"cache_dir={cache_dir}", *_pytest_targets(root, test_paths)]
    cp = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True, timeout=180, check=False)
    out = (cp.stdout + (("\n" + cp.stderr) if cp.stderr else "")).strip()
    nodes = [line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if "::test_" in line]
    return nodes, out, cp.returncode


def run_pytest(root: Path, cache_dir: Path, junit: Path, env: dict[str, str], test_paths: list[Path], *, stepwise: bool) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-o", f"cache_dir={cache_dir}", f"--junitxml={junit}"]
    if stepwise:
        cmd.append("--stepwise")
    cmd.extend(_pytest_targets(root, test_paths))
    cp = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True, timeout=120, check=False)
    return cp.returncode, (cp.stdout + (("\n" + cp.stderr) if cp.stderr else "")).strip()


def _case_result(case) -> str:
    if case.find("failure") is not None: return "failed"
    if case.find("error") is not None: return "errors"
    if case.find("skipped") is not None: return "skipped"
    return "passed"


def junit_part4_summary(junit: Path) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if not junit.is_file(): return groups
    try: tree = ET.parse(junit)
    except Exception: return groups
    for case in tree.getroot().iter("testcase"):
        text = " ".join(str(case.attrib.get(k) or "") for k in ("file", "classname", "name")).replace("\\", "/")
        m = re.search(r"test_gui_alpha(\d+)", text)
        if not m: continue
        alpha = m.group(1)
        try: n = int(alpha)
        except ValueError: continue
        if n < 37: continue
        g = groups.setdefault(alpha, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
        g[_case_result(case)] += 1
    return groups


def junit_part5_summary(junit: Path) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if not junit.is_file(): return groups
    try: tree = ET.parse(junit)
    except Exception: return groups
    for case in tree.getroot().iter("testcase"):
        text = " ".join(str(case.attrib.get(k) or "") for k in ("file", "classname", "name")).replace("\\", "/")
        if "test_gui_part5" not in text: continue
        group = "part5"
        g = groups.setdefault(group, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
        g[_case_result(case)] += 1
    return groups

def junit_part6_summary(junit: Path) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if not junit.is_file(): return groups
    try: tree = ET.parse(junit)
    except Exception: return groups
    for case in tree.getroot().iter("testcase"):
        text = " ".join(str(case.attrib.get(k) or "") for k in ("file", "classname", "name")).replace("\\", "/")
        if "test_gui_part6" not in text: continue
        group = "part6"
        g = groups.setdefault(group, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
        g[_case_result(case)] += 1
    return groups


def junit_part7_summary(junit: Path) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if not junit.is_file(): return groups
    try: tree = ET.parse(junit)
    except Exception: return groups
    for case in tree.getroot().iter("testcase"):
        text = " ".join(str(case.attrib.get(k) or "") for k in ("file", "classname", "name")).replace("\\", "/")
        if "test_gui_part7" not in text: continue
        group = "part7"
        g = groups.setdefault(group, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
        g[_case_result(case)] += 1
    return groups


def junit_part8_summary(junit: Path) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if not junit.is_file(): return groups
    try: tree = ET.parse(junit)
    except Exception: return groups
    for case in tree.getroot().iter("testcase"):
        text = " ".join(str(case.attrib.get(k) or "") for k in ("file", "classname", "name")).replace("\\", "/")
        if "test_gui_part8" not in text: continue
        group = "part8"
        g = groups.setdefault(group, {"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
        g[_case_result(case)] += 1
    return groups


def status_for_gates(groups: dict[str, dict[str, int]]) -> str:
    if not groups: return "AUTOMATED_GATE_SKIP"
    if any(v["failed"] or v["errors"] for v in groups.values()): return "AUTOMATED_GATE_FAIL"
    if all(v["passed"] == 0 and v["skipped"] > 0 for v in groups.values()): return "AUTOMATED_GATE_SKIP"
    if any(v["skipped"] for v in groups.values()): return "AUTOMATED_GATE_PASS_WITH_SKIPS"
    return "AUTOMATED_GATE_PASS"


def write_report(report_dir: Path, payload: dict, explicit_json: Path | None = None) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    part = int(payload.get("part") or 0)
    json_path = explicit_json or (report_dir / f"ChromaPress_Part{part}_TestPack_{stamp}.json")
    md_path = report_dir / f"ChromaPress_Part{part}_TestPack_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"# ChromaPress Part {part} Consolidated Test Pack", "",
        f"- Status: **{payload['status']}**", f"- Bundle SHA-256: `{payload['bundle_sha256']}`",
        f"- Collected: **{payload['collected_count']}**", f"- Resume checkpoint used: **{payload['resumed_from_checkpoint']}**",
        f"- Seal pass performed: **{payload['seal_pass_performed']}**", f"- Staged GUI gates: **{payload['staged_gate_status']}**", "",
    ]
    if payload.get("failed_node"): lines += [f"- Failed/checkpoint node: `{payload['failed_node']}`", ""]
    lines += ["## Result counts", "", "```text", json.dumps(payload.get("counts", {}), indent=2), "```", ""]
    if payload.get("pytest_output"): lines += ["## Pytest output", "", "```text", payload["pytest_output"][-16000:], "```", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one consolidated ChromaPress Part regression pack with stop/resume checkpointing.")
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--part", type=int, choices=range(1, 9), default=4)
    p.add_argument("--report-dir", type=Path)
    p.add_argument("--json-report", type=Path)
    p.add_argument("--restart", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--legacy-full", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args(); part = int(args.part); root = args.project.resolve()
    report_dir = args.report_dir.resolve() if args.report_dir else root / "test-reports"
    checkpoint = report_dir / f"ChromaPress_Part{part}_TestPack_checkpoint.json"
    cache_dir = report_dir / f".chromapress-part{part}-testpack-cache"
    work_dir = report_dir / f".chromapress-part{part}-testpack-work"; work_dir.mkdir(parents=True, exist_ok=True)
    if args.restart:
        checkpoint.unlink(missing_ok=True); shutil.rmtree(cache_dir, ignore_errors=True)
    try:
        bundle, bundle_sha = verify_bundle(root, part); manifest = load_manifest(root, part); legacy_hashes = load_legacy_hashes(root, part)
    except Exception as exc:
        payload = {"schema": 3, "part": part, "status": FAIL, "bundle_sha256": "unknown", "collected_count": 0, "counts": {},
                   "resumed_from_checkpoint": False, "seal_pass_performed": False, "failed_node": "bundle-verification",
                   "staged_gate_status": "AUTOMATED_GATE_FAIL", "staged_gates": {}, "pytest_output": str(exc)}
        md, js = write_report(report_dir, payload, args.json_report.resolve() if args.json_report else None)
        print(f"CHROMAPRESS_PART{part}_TESTPACK={FAIL}\nFAILED_AT=bundle-verification\nMarkdown report: {md}\nJSON report:     {js}")
        return 1
    had_checkpoint = checkpoint.is_file() and not args.legacy_full
    if had_checkpoint:
        try:
            checkpoint_data = json.loads(checkpoint.read_text(encoding="utf-8"))
            if str(checkpoint_data.get("bundle_sha256") or "").lower() != bundle_sha.lower():
                checkpoint.unlink(missing_ok=True); shutil.rmtree(cache_dir, ignore_errors=True); had_checkpoint = False
        except Exception:
            checkpoint.unlink(missing_ok=True); shutil.rmtree(cache_dir, ignore_errors=True); had_checkpoint = False
    env = project_env(root); junit = work_dir / "pytest-results.xml"; collected=[]; collect_output=""; pytest_output=""; seal_output=""; failed_node=""; groups={}; seal_performed=False; status=FAIL; rc=1
    test_paths: list[Path] = []; preexisting_owned: set[str] = set(); interrupted_generated = False
    try:
        test_paths, preexisting_owned, interrupted_generated = safe_prepare_tests(root, part, bundle, manifest, legacy_hashes)
        collected, collect_output, collect_rc = collect_nodes(root, cache_dir, env, test_paths)
        if collect_rc not in (0,5) or not collected:
            failed_node="collection"; pytest_output=collect_output; raise RuntimeError("test collection failed")
        rc, pytest_output = run_pytest(root, cache_dir, junit, env, test_paths, stepwise=not args.legacy_full)
        groups = junit_part4_summary(junit) if part == 4 else junit_part5_summary(junit) if part == 5 else junit_part6_summary(junit) if part == 6 else junit_part7_summary(junit) if part == 7 else junit_part8_summary(junit) if part == 8 else {}
        if rc != 0:
            failed_node=first_failure_node(pytest_output); checkpoint.parent.mkdir(parents=True,exist_ok=True)
            checkpoint.write_text(json.dumps({"schema":1,"bundle_sha256":bundle_sha,"failed_node":failed_node,"updated_utc":dt.datetime.now(dt.timezone.utc).isoformat()},indent=2),encoding="utf-8")
        else:
            if had_checkpoint and not args.legacy_full:
                seal_performed=True; shutil.rmtree(cache_dir,ignore_errors=True); junit_seal=work_dir/"pytest-seal-results.xml"
                rc2, seal_output=run_pytest(root,cache_dir,junit_seal,env,test_paths,stepwise=True)
                groups=(junit_part4_summary(junit_seal) if part==4 else junit_part5_summary(junit_seal) if part==5 else junit_part6_summary(junit_seal) if part==6 else junit_part7_summary(junit_seal) if part==7 else junit_part8_summary(junit_seal) if part==8 else {}) or groups
                if rc2 != 0:
                    rc=rc2; failed_node=first_failure_node(seal_output); checkpoint.write_text(json.dumps({"schema":1,"bundle_sha256":bundle_sha,"failed_node":failed_node,"updated_utc":dt.datetime.now(dt.timezone.utc).isoformat()},indent=2),encoding="utf-8")
                else:
                    checkpoint.unlink(missing_ok=True); status=PASS; rc=0
            else:
                checkpoint.unlink(missing_ok=True); status=PASS; rc=0
    except Exception as exc:
        if not pytest_output: pytest_output=str(exc)
        if not failed_node: failed_node="testpack-runner"
        status=FAIL; rc=1
    finally:
        cleanup_tests(root, part, manifest, preexisting_owned, interrupted_generated)
    combined=pytest_output + (("\n\n--- FULL SEAL PASS AFTER RESUME ---\n"+seal_output) if seal_output else "")
    gate_status=status_for_gates(groups)
    payload={"schema":3,"part":part,"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"project_root":str(root),"status":status,
             "bundle_sha256":bundle_sha,"collected_count":len(collected),"collected_tests":collected,"counts":parse_counts(seal_output or pytest_output),
             "resumed_from_checkpoint":had_checkpoint,"seal_pass_performed":seal_performed,"failed_node":failed_node,"staged_gate_status":gate_status,
             "staged_gates":groups,"pytest_output":combined,"collection_output":collect_output}
    if part==4:
        payload["part4_staged_gate_status"]=gate_status; payload["part4_staged_gates"]=groups
    if part==5:
        payload["part5_staged_gate_status"]=gate_status; payload["part5_staged_gates"]=groups
    if part==6:
        payload["part6_staged_gate_status"]=gate_status; payload["part6_staged_gates"]=groups
    if part==7:
        payload["part7_staged_gate_status"]=gate_status; payload["part7_staged_gates"]=groups
    if part==8:
        payload["part8_staged_gate_status"]=gate_status; payload["part8_staged_gates"]=groups
    md,js=write_report(report_dir,payload,args.json_report.resolve() if args.json_report else None)
    print(f"CHROMAPRESS_PART{part}_TESTPACK={status}"); print(f"COLLECTED={len(collected)}"); print(f"PART{part}_STAGED_GATES={gate_status}")
    if failed_node: print(f"FAILED_AT={failed_node}\nNEXT_RUN=RESUME_FROM_FAILURE")
    elif seal_performed: print("RESUME_AND_FULL_SEAL=PASS")
    else: print("FULL_RUN=PASS")
    print(f"Markdown report: {md}\nJSON report:     {js}")
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
