ChromaPress Windows build path fix

Fixes packaging/chromapress.spec so SPECPATH resolves the project root correctly.
Extract this ZIP directly over the accepted ChromaPress project folder and replace the file.
Then run:
  .\packaging\build_windows_release.ps1 -SkipInstall
