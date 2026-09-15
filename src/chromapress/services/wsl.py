from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import project_root, windows_to_wsl
from .storage import require_write_capacity
import time
import uuid


class WslError(RuntimeError):
    pass


def _subprocess_window_kwargs() -> dict:
    """Keep WSL/console helpers hidden when ChromaPress runs as a GUI .exe."""
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags} if flags else {}


def _running_under_wsl() -> bool:
    # Detect a Linux process hosted by Windows Subsystem for Linux.
    distro = os.environ.get("WSL_DISTRO_NAME", "").strip()
    if not distro:
        return False
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except OSError:
        return False
    return "microsoft" in release


def _engine_error(label: str, cp: subprocess.CompletedProcess[str]) -> str:
    detail = (cp.stderr or cp.stdout or "").strip()
    # 0xC000013A / -1073741510 is Windows STATUS_CONTROL_C_EXIT, usually seen
    # when a transient console window is closed/interrupted. ChromaPress now
    # launches WSL hidden, but keep a useful diagnostic if an external tool
    # still interrupts it.
    if cp.returncode in (3221225786, -1073741510):
        return detail or f"{label} engine was interrupted before analysis completed (0xC000013A)."
    return detail or f"{label} engine exited {cp.returncode}"


class WslBridge:
    def __init__(self, distro: str = "Ubuntu") -> None:
        self.distro = distro

    def _run(self, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
        if os.name == "nt":
            cmd = ["wsl.exe", "-d", self.distro, "--exec", *args]
            label = "WSL"
        else:
            cmd = list(args)
            label = "Linux"
        cp = subprocess.run(
            cmd, text=True, capture_output=True, timeout=timeout, check=False,
            **_subprocess_window_kwargs(),
        )
        if cp.returncode != 0:
            raise WslError(_engine_error(label, cp))
        return cp

    def probe(self) -> str:
        return self._run(["/bin/true"], timeout=20).stdout

    def _engine(self, args: list[str], timeout: int, *, as_root: bool = False) -> dict:
        root = project_root()
        if os.name == "nt":
            wsl_root = windows_to_wsl(str(root))
            cmd = ["wsl.exe", "-d", self.distro]
            if as_root:
                cmd += ["--user", "root"]
            cmd += [
                "--cd", wsl_root,
                "--exec", "/usr/bin/env", "PYTHONPATH=src",
                "python3", "-m", "chromapress.engine_cli", *args,
            ]
            env = None
            cwd = None
            label = "WSL"
        else:
            src = root / "src"
            env = os.environ.copy()
            current = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(src) if not current else str(src) + os.pathsep + current
            base = [sys.executable, "-m", "chromapress.engine_cli", *args]
            cmd = base
            cwd = str(root)
            label = "Linux"
            geteuid = getattr(os, "geteuid", None)
            if as_root and geteuid is not None and geteuid() != 0:
                distro = os.environ.get("WSL_DISTRO_NAME", "").strip()
                wsl_exe = shutil.which("wsl.exe") if _running_under_wsl() else None
                if wsl_exe and distro:
                    cmd = [
                        wsl_exe,
                        "-d",
                        distro,
                        "--user",
                        "root",
                        "--cd",
                        str(root),
                        "--exec",
                        "/usr/bin/env",
                        f"PYTHONPATH={env['PYTHONPATH']}",
                        sys.executable,
                        "-m",
                        "chromapress.engine_cli",
                        *args,
                    ]
                    env = None
                    cwd = None
                    label = "WSL"
                else:
                    pkexec = shutil.which("pkexec")
                    env_bin = shutil.which("env") or "/usr/bin/env"
                    if pkexec:
                        cmd = [pkexec, env_bin, f"PYTHONPATH={env['PYTHONPATH']}", *base]
                        env = None

        cp = subprocess.run(
            cmd, text=True, capture_output=True, timeout=timeout, check=False, cwd=cwd, env=env,
            **_subprocess_window_kwargs(),
        )
        if cp.returncode != 0:
            raise WslError(_engine_error(label, cp))
        try:
            return json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            raise WslError(f"Invalid JSON from ChromaPress Linux engine: {exc}\n{cp.stdout[-2000:]}") from exc

    def analyze_iso(self, windows_path: str) -> dict:
        # Only read-only source analysis runs as WSL root. This permits a
        # tightly scoped loop,ro fallback for embedded SquashFS inspection
        # without sudo prompts when direct byte-offset reads are unsupported.
        return self._engine(["analyze", windows_to_wsl(windows_path)], timeout=300, as_root=(os.name == "nt"))

    def application_catalog(
        self,
        windows_path: str,
        workspace_windows: str,
        reserve_gb: int,
        cache_windows: str = "",
        cache_key: str = "",
    ) -> dict:
        workspace = Path(workspace_windows)
        # Fast path reads SquashFS directly inside the ISO by offset and writes
        # only small metadata. Keep conservative fallback headroom in case the
        # installed unsquashfs cannot use -offset.
        require_write_capacity(workspace, reserve_gb=reserve_gb, required_bytes=4 * 1024**3)
        args = ["catalog", windows_to_wsl(windows_path), "--workspace", windows_to_wsl(workspace_windows)]
        if cache_windows:
            args += ["--cache-dir", windows_to_wsl(cache_windows)]
        if cache_key:
            args += ["--cache-key", cache_key]
        return self._engine(args, timeout=900)

    def _engine_build_progress(
        self,
        args: list[str],
        timeout: int,
        *,
        progress_host_path: Path,
        progress_callback=None,
        as_root: bool = False,
    ) -> dict:
        root = project_root()
        if os.name == "nt":
            wsl_root = windows_to_wsl(str(root))
            cmd = ["wsl.exe", "-d", self.distro]
            if as_root:
                cmd += ["--user", "root"]
            cmd += [
                "--cd", wsl_root,
                "--exec", "/usr/bin/env", "PYTHONPATH=src",
                "python3", "-m", "chromapress.engine_cli", *args,
            ]
            env = None
            cwd = None
            label = "WSL"
        else:
            src = root / "src"
            env = os.environ.copy()
            current = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(src) if not current else str(src) + os.pathsep + current
            base = [sys.executable, "-m", "chromapress.engine_cli", *args]
            cmd = base
            cwd = str(root)
            label = "Linux"
            geteuid = getattr(os, "geteuid", None)
            if as_root and geteuid is not None and geteuid() != 0:
                distro = os.environ.get("WSL_DISTRO_NAME", "").strip()
                wsl_exe = shutil.which("wsl.exe") if _running_under_wsl() else None
                if wsl_exe and distro:
                    cmd = [
                        wsl_exe,
                        "-d",
                        distro,
                        "--user",
                        "root",
                        "--cd",
                        str(root),
                        "--exec",
                        "/usr/bin/env",
                        f"PYTHONPATH={env['PYTHONPATH']}",
                        sys.executable,
                        "-m",
                        "chromapress.engine_cli",
                        *args,
                    ]
                    env = None
                    cwd = None
                    label = "WSL"
                else:
                    pkexec = shutil.which("pkexec")
                    env_bin = shutil.which("env") or "/usr/bin/env"
                    if pkexec:
                        cmd = [pkexec, env_bin, f"PYTHONPATH={env['PYTHONPATH']}", *base]
                        env = None

        process = subprocess.Popen(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            **_subprocess_window_kwargs(),
        )
        started = time.monotonic()
        last_serialized = ""

        def publish_progress() -> None:
            nonlocal last_serialized
            if progress_callback is None or not progress_host_path.is_file():
                return
            try:
                payload = json.loads(progress_host_path.read_text(encoding="utf-8"))
                serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if serialized != last_serialized:
                    last_serialized = serialized
                    progress_callback(payload)
            except Exception:
                pass

        while process.poll() is None:
            publish_progress()
            if time.monotonic() - started > timeout:
                process.kill()
                stdout, stderr = process.communicate()
                raise WslError(
                    f"{label} build engine timed out after {timeout} seconds.\n"
                    + (stderr or stdout or "").strip()
                )
            time.sleep(0.15)

        stdout, stderr = process.communicate()
        publish_progress()
        cp = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
        if cp.returncode != 0:
            raise WslError(_engine_error(label, cp))
        try:
            return json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            raise WslError(
                f"Invalid JSON from ChromaPress Linux engine: {exc}\n{cp.stdout[-2000:]}"
            ) from exc

    def build_iso(self, execution_plan: dict, progress_callback=None) -> dict:
        plan = json.loads(json.dumps(execution_plan))
        production = plan.get("production")
        if not isinstance(production, dict):
            raise WslError("Build execution plan is missing production metadata.")

        output_dir_host = str(production.get("output_dir") or "").strip()
        output_name = str(production.get("output_name") or "").strip()
        workspace_host = str(plan.get("workspace_dir") or "").strip()
        if not output_dir_host or not output_name or not workspace_host:
            raise WslError("Build requires output directory, output filename and configured workspace.")

        Path(output_dir_host).mkdir(parents=True, exist_ok=True)
        progress_host_path = Path(output_dir_host) / f".chromapress-progress-{uuid.uuid4().hex}.json"

        if os.name == "nt":
            production["source_path"] = windows_to_wsl(str(production.get("source_path") or ""))
            production["output_dir"] = windows_to_wsl(output_dir_host)
            plan["workspace_dir"] = windows_to_wsl(workspace_host)
            plan["progress_path"] = windows_to_wsl(str(progress_host_path))
        else:
            plan["progress_path"] = str(progress_host_path)

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix=".chromapress-build-",
                dir=output_dir_host,
                delete=False,
            ) as handle:
                json.dump(plan, handle, ensure_ascii=False, indent=2)
                temp_path = handle.name

            engine_plan_path = windows_to_wsl(temp_path) if os.name == "nt" else temp_path
            result = self._engine_build_progress(
                ["build", engine_plan_path],
                timeout=10800,
                progress_host_path=progress_host_path,
                progress_callback=progress_callback,
                as_root=True,
            )
            result["output_path"] = str(Path(output_dir_host) / output_name)
            return result
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                progress_host_path.unlink(missing_ok=True)
                progress_host_path.with_name(progress_host_path.name + ".tmp").unlink(missing_ok=True)
            except OSError:
                pass
