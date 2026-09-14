# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

# The raw source tree is intentionally included as data because the Windows
# front-end launches the Linux engine inside WSL with PYTHONPATH=src.
datas = [
    (str(ROOT / "pyproject.toml"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "packaging" / "LGPL-3.0.txt"), "licenses"),
    (str(SRC / "chromapress"), "src/chromapress"),
    (str(ROOT / "bundled_apps"), "bundled_apps"),
    (str(ROOT / "bundled_docs"), "bundled_docs"),
]

a = Analysis(
    [str(ROOT / "packaging" / "windows_entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["chromapress.engine_cli"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ChromaPress",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "packaging" / "chromapress.ico")],
    version=str(ROOT / "packaging" / "version_info.txt"),
)
