from __future__ import annotations
from chromapress.i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFormLayout, QGroupBox

class OverviewPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title = QLabel(tr('Overview'))
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        box = QGroupBox(tr('Image'))
        form = QFormLayout(box)
        self.fields = {}
        for key, label in [('distribution', 'Distribution'), ('version', 'Version'), ('architecture', 'Architecture'), ('volume_id', 'Volume ID'), ('installer', 'Installer'), ('package_format', 'Package format'), ('boot', 'Boot'), ('rootfs', 'Root filesystem layers'), ('sha256', 'SHA-256'), ('path', 'Source path')]:
            value = QLabel(tr('—'))
            value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            form.addRow(tr(label + ':'), value)
            self.fields[key] = value
        layout.addWidget(box)
        layout.addStretch(1)

    def set_analysis(self, data: dict):
        self.fields['distribution'].setText(data.get('distribution') or tr('Unknown'))
        self.fields['version'].setText(data.get('version') or tr('Unknown'))
        self.fields['architecture'].setText(data.get('architecture') or tr('Unknown'))
        self.fields['volume_id'].setText(data.get('volume_id') or tr('—'))
        self.fields['installer'].setText(data.get('installer') or tr('Unknown'))
        self.fields['package_format'].setText(data.get('package_format') or tr('Unknown'))
        boot = ', '.join((x for x, ok in (('BIOS', data.get('bios_boot')), ('UEFI', data.get('uefi_boot'))) if ok)) or 'Unknown'
        self.fields['boot'].setText(boot)
        self.fields['rootfs'].setText('\n'.join(data.get('rootfs') or []) or tr('Not detected'))
        self.fields['sha256'].setText(data.get('sha256') or tr('—'))
        self.fields['path'].setText(data.get('path') or tr('—'))
