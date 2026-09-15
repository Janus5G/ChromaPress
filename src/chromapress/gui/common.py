from __future__ import annotations
from chromapress.i18n import tr
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class PlaceholderPage(QWidget):

    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title_label = QLabel(tr(title))
        title_label.setObjectName('pageTitle')
        body = QLabel(tr(text))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title_label)
        layout.addWidget(body)
        layout.addStretch(1)
