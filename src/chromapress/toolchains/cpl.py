from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CplToolchain:
    root: str = ""

    def validate(self) -> tuple[bool, str]:
        if not self.root:
            return False, "CPL/CPA toolchain path is not configured yet."
        root = Path(self.root)
        if not root.exists():
            return False, "Configured CPL/CPA toolchain path does not exist."
        markers = ["chromaplex", "chromaplex_os", "compiler.py", "cpl_compiler.py"]
        names = {p.name for p in root.rglob("*") if p.is_file()}
        if not any(m in names for m in markers[-2:]) and not any((root / m).exists() for m in markers[:2]):
            return False, "No recognized ChromaPlex compiler layout was found."
        return True, "CPL/CPA toolchain path looks usable."


CPL_KEYWORDS = re.compile(r"\b(?:potens|tal|streng|konstant|pixel|skriv_voxel|kanal|rød|grøn|blå|violet|uv|var|store|load|print|HALT)\b", re.I)
