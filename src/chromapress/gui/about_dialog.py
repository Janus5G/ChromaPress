from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDialogButtonBox, QTextBrowser, QPushButton, QMessageBox,
)

from chromapress import __version__
from chromapress.services.paths import asset_path


def chromapress_icon() -> QIcon:
    # Prefer PNG in frozen Windows builds so the application icon does not
    # depend on the Qt SVG image plugin being available at runtime.
    for name in ("chromapress.png", "chromapress.svg", "chromapress-placeholder.png", "chromapress-placeholder.svg"):
        asset = asset_path(name)
        if asset.is_file():
            icon = QIcon(str(asset))
            if not icon.isNull():
                return icon
    return QIcon()


def license_text() -> str:
    asset = asset_path("CHROMAPRESS_LICENSE.txt")
    if asset.is_file():
        return asset.read_text(encoding="utf-8")
    return (
        "MIT License\n\n"
        "Copyright (c) 2026 Janus Rokkjær\n\n"
        "The full license text is unavailable in this installation."
    )


def share_text() -> str:
    return (
        "ChromaPress — free and open-source Linux ISO customization for Windows and Linux.\n"
        "MIT licensed. If ChromaPress is useful to you, please help spread the word and share the official release."
    )


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About ChromaPress")
        self.setWindowIcon(chromapress_icon())
        self.resize(660, 620)
        self.setMinimumSize(560, 500)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        icon = QLabel()
        pixmap = chromapress_icon().pixmap(64, 64)
        if not pixmap.isNull():
            icon.setPixmap(pixmap)
        text = QVBoxLayout()
        title = QLabel("ChromaPress")
        title.setObjectName("dialogTitle")
        version = QLabel(f"Version {__version__}")
        description = QLabel("Professional Linux ISO customization and image-servicing workbench.")
        description.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(version)
        text.addWidget(description)
        header.addWidget(icon)
        header.addLayout(text, 1)
        layout.addLayout(header)

        copyright_label = QLabel("Copyright © 2026 Janus Rokkjær")
        copyright_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(copyright_label)
        layout.addWidget(QLabel("License: MIT License"))

        share_note = QLabel("ChromaPress is free and open source. If it helps you, please help spread the word.")
        share_note.setWordWrap(True)
        layout.addWidget(share_note)
        share_button = QPushButton("Share ChromaPress")
        share_button.setObjectName("shareChromaPressButton")
        share_button.setToolTip("Copy a short ChromaPress sharing message to the clipboard")
        share_button.clicked.connect(self._share)
        layout.addWidget(share_button)

        license_view = QTextBrowser()
        license_view.setPlainText(license_text())
        layout.addWidget(license_view, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _share(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(share_text())
        QMessageBox.information(
            self,
            "Share ChromaPress",
            "A short ChromaPress sharing message has been copied to the clipboard.",
        )
