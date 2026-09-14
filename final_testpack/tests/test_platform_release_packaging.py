from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_linux_native_bridge_and_windows_wsl_paths_both_exist():
    source = (ROOT / "src/chromapress/services/wsl.py").read_text(encoding="utf-8")
    assert 'if os.name == "nt"' in source
    assert '"wsl.exe"' in source
    assert 'sys.executable, "-m", "chromapress.engine_cli"' in source
    assert 'shutil.which("pkexec")' in source


def test_release_builders_and_workflow_are_present():
    assert (ROOT / "packaging/build_windows_release.ps1").is_file()
    assert (ROOT / "packaging/build_deb.sh").is_file()
    assert (ROOT / "packaging/chromapress.spec").is_file()
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "ubuntu-latest" in workflow
    assert "gh release create" in workflow


def test_windows_bundle_carries_raw_linux_engine_for_wsl():
    spec = (ROOT / "packaging/chromapress.spec").read_text(encoding="utf-8")
    assert '(str(SRC / "chromapress"), "src/chromapress")' in spec
    assert '(str(ROOT / "bundled_apps"), "bundled_apps")' in spec
    assert '(str(ROOT / "bundled_docs"), "bundled_docs")' in spec


def test_deb_launcher_uses_native_engine():
    script = (ROOT / "packaging/build_deb.sh").read_text(encoding="utf-8")
    assert 'exec /usr/bin/python3 -m chromapress.app' in script
    assert 'exec /usr/bin/python3 -m chromapress.engine_cli' in script
    assert "wsl.exe" not in script
