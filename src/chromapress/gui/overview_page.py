from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFormLayout, QGroupBox


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel("Overview")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        box = QGroupBox("Image")
        form = QFormLayout(box)
        self.fields = {}
        for key, label in [
            ("distribution", "Distribution"), ("version", "Version"), ("architecture", "Architecture"),
            ("volume_id", "Volume ID"), ("installer", "Installer"), ("package_format", "Package format"),
            ("boot", "Boot"), ("rootfs", "Root filesystem layers"), ("sha256", "SHA-256"), ("path", "Source path"),
        ]:
            value = QLabel("—")
            value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            form.addRow(label + ":", value)
            self.fields[key] = value
        layout.addWidget(box)
        layout.addStretch(1)

    def set_analysis(self, data: dict):
        self.fields["distribution"].setText(data.get("distribution") or "Unknown")
        self.fields["version"].setText(data.get("version") or "Unknown")
        self.fields["architecture"].setText(data.get("architecture") or "Unknown")
        self.fields["volume_id"].setText(data.get("volume_id") or "—")
        self.fields["installer"].setText(data.get("installer") or "Unknown")
        self.fields["package_format"].setText(data.get("package_format") or "Unknown")
        boot = ", ".join(x for x, ok in (("BIOS", data.get("bios_boot")), ("UEFI", data.get("uefi_boot"))) if ok) or "Unknown"
        self.fields["boot"].setText(boot)
        self.fields["rootfs"].setText("\n".join(data.get("rootfs") or []) or "Not detected")
        self.fields["sha256"].setText(data.get("sha256") or "—")
        self.fields["path"].setText(data.get("path") or "—")
