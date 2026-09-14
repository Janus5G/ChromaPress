from __future__ import annotations

from pathlib import Path
import shutil


class StoragePreflightError(RuntimeError):
    pass


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    if not current.exists():
        raise StoragePreflightError(f"Storage location is not reachable: {path}")
    return current


def require_write_capacity(path: Path, reserve_gb: int, required_bytes: int = 0) -> None:
    """Fail closed before a large write.

    The exact configured path is used; this function never substitutes another
    directory or filesystem. `required_bytes` is conservative headroom for the
    pending operation and the safety reserve must still remain afterwards.
    """
    if not str(path).strip():
        raise StoragePreflightError("No storage location is configured.")

    existing = _nearest_existing(path)
    usage = shutil.disk_usage(existing)
    reserve_bytes = int(reserve_gb) * 1024**3
    needed = reserve_bytes + max(0, int(required_bytes))
    if usage.free < needed:
        free_gb = usage.free / 1024**3
        need_gb = needed / 1024**3
        raise StoragePreflightError(
            f"Storage blocked: {free_gb:.1f} GB free, but at least {need_gb:.1f} GB "
            f"is required to keep the {reserve_gb} GB safety reserve. "
            f"Configured location: {path}"
        )
