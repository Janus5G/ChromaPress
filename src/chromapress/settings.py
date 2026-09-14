from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSettings:
    # User-facing root. Workspace/cache remain explicit internally so the
    # storage engine can later validate the exact device before large writes.
    storage_root: str = ""
    wsl_distro: str = "Ubuntu"
    workspace_dir: str = ""
    cache_dir: str = ""
    reserve_gb: int = 20

    # AI provider/model are safe to persist. The API key is intentionally
    # runtime-only until Windows Credential Manager/keyring integration lands.
    ai_provider: str = "openai"
    ai_model: str = "gpt-5.6-sol"
    ai_endpoint: str = ""
    ai_api_key: str = ""

    cpl_toolchain_path: str = ""

    @staticmethod
    def defaults(base: Path) -> "AppSettings":
        # Large-data locations are intentionally unset on first start.
        # ChromaPress must never silently choose C:, WSL root, or another disk.
        return AppSettings(storage_root="", workspace_dir="", cache_dir="")
