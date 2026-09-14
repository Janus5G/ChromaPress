from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the final ChromaPress release gate before EXE/DEB packaging.")
    ap.add_argument("--iso", type=Path, required=True, help="Real source ISO used for the final read-only acceptance run")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="ChromaPress project root")
    args = ap.parse_args()
    root = args.project.resolve()
    iso = args.iso.resolve()
    report_dir = root / "test-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    results: list[dict] = []

    if not (root / "pyproject.toml").is_file():
        print("FINAL_RELEASE_GATE=FAIL — pyproject.toml missing")
        return 2
    if not iso.is_file():
        print(f"FINAL_RELEASE_GATE=FAIL — ISO not found: {iso}")
        return 2
    if importlib.util.find_spec("PySide6") is None:
        print("FINAL_RELEASE_GATE=FAIL — PySide6 is not installed in this Python environment; GUI release checks cannot be accepted.")
        return 2

    tests = root / "final_testpack" / "tests"
    code, output = run([sys.executable, "-m", "pytest", "-q", str(tests)], root)
    results.append({"gate": "final_release_regressions", "status": "PASS" if code == 0 else "FAIL", "output": output})
    print(output, end="" if output.endswith("\n") else "\n")
    if code != 0:
        overall = "FAIL"
    else:
        acceptance_cmd = [
            sys.executable, "chromapress_acceptance.py", "--through", "8",
            "--restart-testpack", "--iso", str(iso),
        ]
        acode, aoutput = run(acceptance_cmd, root)
        results.append({"gate": "parts_1_through_8_acceptance", "status": "PASS" if acode == 0 else "FAIL", "output": aoutput})
        print(aoutput, end="" if aoutput.endswith("\n") else "\n")
        overall = "PASS" if acode == 0 else "FAIL"

    important = [
        root / "LICENSE",
        root / "pyproject.toml",
        root / "src/chromapress/gui/about_dialog.py",
        root / "src/chromapress/gui/components_page.py",
        root / "src/chromapress/services/ai.py",
        root / "src/chromapress/services/part6.py",
        root / "testpack/part4_tests.zip",
    ]
    hashes = {str(p.relative_to(root)): sha256(p) for p in important if p.is_file()}
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0a72",
        "overall": overall,
        "iso": str(iso),
        "iso_sha256": sha256(iso),
        "results": results,
        "release_gate_hashes": hashes,
        "manual_runtime_note": "MANUAL_REQUIRED items from the 8-Part acceptance remain truthful and are not converted into PASS by this release gate.",
    }
    json_path = report_dir / f"ChromaPress_Final_Release_Gate_{stamp}.json"
    md_path = report_dir / f"ChromaPress_Final_Release_Gate_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# ChromaPress Final Release Gate",
        "",
        f"- Version: `1.0.0a72`",
        f"- Overall: **{overall}**",
        f"- ISO: `{iso}`",
        f"- ISO SHA-256: `{payload['iso_sha256']}`",
        "",
        "## Gates",
        "",
    ]
    for row in results:
        lines += [f"- **{row['status']}** — {row['gate']}", "", "```text", row['output'][-12000:], "```", ""]
    lines += ["## Release-gate file hashes", ""]
    for name, digest in hashes.items():
        lines.append(f"- `{digest}`  `{name}`")
    lines += ["", "## Manual boundary", "", payload["manual_runtime_note"], ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"FINAL_RELEASE_GATE={overall}")
    print(f"Markdown report: {md_path}")
    print(f"JSON report:     {json_path}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
