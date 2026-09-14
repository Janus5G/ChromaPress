from __future__ import annotations

from pathlib import Path, PureWindowsPath
import re
import sys


def windows_to_wsl(path: str) -> str:
    value = path.strip()
    if value.startswith("/"):
        return value
    p = PureWindowsPath(value)
    drive = p.drive.rstrip(":").lower()
    if not drive or not re.fullmatch(r"[a-z]", drive):
        raise ValueError(f"Cannot convert path to WSL path: {path}")
    tail = "/".join(p.parts[1:])
    return f"/mnt/{drive}/{tail}"


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[3]


def asset_path(name: str) -> Path:
    """Return a ChromaPress asset path in source and frozen PyInstaller builds."""
    candidates: list[Path] = []
    try:
        root = project_root()
        candidates.append(root / "src" / "chromapress" / "assets" / name)
    except Exception:
        pass

    # Normal package layout (editable/source installs).
    candidates.append(Path(__file__).resolve().parents[1] / "assets" / name)

    # PyInstaller one-file extraction root. Raw Linux-engine sources/assets are
    # intentionally bundled below _MEIPASS/src/chromapress.
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.insert(0, Path(meipass) / "src" / "chromapress" / "assets" / name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else Path(name)
