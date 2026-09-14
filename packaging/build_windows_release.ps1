param(
    [switch]$SkipInstall
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Python = Join-Path $Root ".venv-win\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing .venv-win. Run from the accepted ChromaPress project that already contains the Windows venv."
}

if (-not $SkipInstall) {
    & $Python -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }
}

Remove-Item -Recurse -Force "$Root\build\chromapress" -ErrorAction SilentlyContinue
Remove-Item -Force "$Root\dist\ChromaPress.exe" -ErrorAction SilentlyContinue

& $Python -m PyInstaller --noconfirm --clean "$Root\packaging\chromapress.spec"
if ($LASTEXITCODE -ne 0) { throw "Windows build failed." }

$Exe = "$Root\dist\ChromaPress.exe"
if (-not (Test-Path $Exe)) { throw "Build completed without dist\ChromaPress.exe" }
$Hash = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
"$Hash  ChromaPress.exe" | Set-Content -Encoding ascii "$Exe.sha256"

Write-Host "WINDOWS_BUILD=PASS"
Write-Host "EXE=$Exe"
Write-Host "SHA256=$Hash"
