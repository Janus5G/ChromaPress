from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import project_root, windows_to_wsl
from .storage import require_write_capacity


class WslError(RuntimeError):
    pass


def _subprocess_window_kwargs() -> dict:
    """Keep WSL/console helpers hidden when ChromaPress runs as a GUI .exe."""
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags} if flags else {}


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
