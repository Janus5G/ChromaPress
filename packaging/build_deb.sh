#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="1.0.0~a72-1"
WORKROOT="$(mktemp -d /tmp/chromapress-deb.XXXXXX)"
trap 'rm -rf "${WORKROOT}"' EXIT
PKGROOT="${WORKROOT}/chromapress_${VERSION}_all"
OUT="${ROOT}/dist"
mkdir -p \
  "${PKGROOT}/DEBIAN" \
  "${PKGROOT}/opt/chromapress" \
  "${PKGROOT}/usr/bin" \
  "${PKGROOT}/usr/share/applications" \
  "${PKGROOT}/usr/share/icons/hicolor/256x256/apps" \
  "${PKGROOT}/usr/share/doc/chromapress" \
  "${OUT}"

# Shared workspaces may inherit setgid bits; dpkg requires normal control-dir permissions.
chmod 0755 "${PKGROOT}" "${PKGROOT}/DEBIAN"
chmod g-s "${PKGROOT}" "${PKGROOT}/DEBIAN"

cat > "${PKGROOT}/DEBIAN/control" <<'EOF'
Package: chromapress
Version: 1.0.0~a72-1
Section: devel
Priority: optional
Architecture: all
Maintainer: Janus Rokkjær
Depends: python3 (>= 3.11), python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, xorriso, squashfs-tools
Recommends: pkexec
Description: Linux ISO customization and image-servicing workbench
 ChromaPress is a graphical workbench for analyzing, customizing, building,
 and verifying Linux installation images. The Linux package uses the native
 Linux engine; the Windows build uses WSL for Linux-native image tooling.
EOF

# Runtime tree. Keep pyproject at the runtime root because ChromaPress uses it
# as a stable resource root for bundled apps/docs and the WSL/native engine.
cp -a "${ROOT}/src" "${PKGROOT}/opt/chromapress/"
cp "${ROOT}/pyproject.toml" "${ROOT}/LICENSE" "${ROOT}/README.md" "${ROOT}/THIRD_PARTY_NOTICES.md" "${PKGROOT}/opt/chromapress/"
cp -a "${ROOT}/bundled_apps" "${ROOT}/bundled_docs" "${PKGROOT}/opt/chromapress/"

cat > "${PKGROOT}/usr/bin/chromapress" <<'EOF'
#!/bin/sh
export PYTHONPATH="/opt/chromapress/src${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m chromapress.app "$@"
EOF
cat > "${PKGROOT}/usr/bin/chromapress-engine" <<'EOF'
#!/bin/sh
export PYTHONPATH="/opt/chromapress/src${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m chromapress.engine_cli "$@"
EOF
chmod 0755 "${PKGROOT}/usr/bin/chromapress" "${PKGROOT}/usr/bin/chromapress-engine"

cat > "${PKGROOT}/usr/share/applications/chromapress.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=ChromaPress
Comment=Build and customize Linux installation images
Exec=chromapress
Icon=chromapress
Terminal=false
Categories=Development;System;
Keywords=Linux;ISO;image;builder;customization;
EOF
cp "${ROOT}/packaging/chromapress-256.png" "${PKGROOT}/usr/share/icons/hicolor/256x256/apps/chromapress.png"
cp "${ROOT}/LICENSE" "${PKGROOT}/usr/share/doc/chromapress/LICENSE"
cp "${ROOT}/THIRD_PARTY_NOTICES.md" "${PKGROOT}/usr/share/doc/chromapress/THIRD_PARTY_NOTICES.md"
cp "${ROOT}/packaging/LGPL-3.0.txt" "${PKGROOT}/usr/share/doc/chromapress/LGPL-3.0.txt"

# Debian packages should not contain writable source/build cache artefacts.
find "${PKGROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} + || true
find "${PKGROOT}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete || true

# Normalize runtime source permissions after copying from Windows/WSL mounts.
# Directories are traversable; source/assets are read-only for normal users.
find "${PKGROOT}/opt/chromapress/src" -type d -exec chmod 0755 {} +
find "${PKGROOT}/opt/chromapress/src" -type f -exec chmod 0644 {} +

# Some shared build filesystems inherit setgid on every created directory.
find "${PKGROOT}" -type d -exec chmod g-s {} +

dpkg-deb --root-owner-group --build "${PKGROOT}" "${OUT}/chromapress_${VERSION}_all.deb" >/dev/null
(cd "${OUT}" && sha256sum "chromapress_${VERSION}_all.deb" > "chromapress_${VERSION}_all.deb.sha256")
echo "DEB_BUILD=PASS"
cat "${OUT}/chromapress_${VERSION}_all.deb.sha256"
