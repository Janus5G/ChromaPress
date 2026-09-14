# ChromaPress release build

The accepted source baseline is version `1.0.0a72`.

## Windows

From the accepted Windows project directory:

```powershell
.\packaging\build_windows_release.ps1
```

Output:

- `dist\ChromaPress.exe`
- `dist\ChromaPress.exe.sha256`

The Windows executable deliberately includes a raw copy of the ChromaPress
Linux engine under its temporary PyInstaller resource tree so WSL can execute
that engine with the same source as the GUI.

## Debian / Ubuntu

```bash
./packaging/build_deb.sh
```

Output:

- `dist/chromapress_1.0.0~a72-1_all.deb`
- matching `.sha256`

The Debian package uses the native Linux engine rather than `wsl.exe`.

## GitHub release

The included `.github/workflows/release.yml` builds both artifacts. Pushing a
`v*` tag creates a GitHub Release and attaches the Windows EXE, Debian package,
and SHA-256 files.
