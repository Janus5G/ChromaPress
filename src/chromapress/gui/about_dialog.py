from __future__ import annotations
from chromapress.i18n import tr, current_language
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox, QTextBrowser, QPushButton, QMessageBox, QFrame
from chromapress import __version__
from chromapress.services.paths import asset_path

def chromapress_icon() -> QIcon:
    for name in ('chromapress.png', 'chromapress.svg', 'chromapress-placeholder.png', 'chromapress-placeholder.svg'):
        asset = asset_path(name)
        if asset.is_file():
            icon = QIcon(str(asset))
            if not icon.isNull():
                return icon
    return QIcon()

def license_text() -> str:
    asset = asset_path('CHROMAPRESS_LICENSE.txt')
    if asset.is_file():
        original = asset.read_text(encoding='utf-8')
    else:
        original = 'MIT License\n\nCopyright (c) 2026 Janus Rokkjær\n\nThe full license text is unavailable in this installation.'
    if current_language() != 'da':
        return original
    danish = 'MIT-licens — uofficiel dansk oversættelse\n\nCopyright (c) 2026 Janus Rokkjær\n\nDer gives hermed gratis tilladelse til enhver person, der modtager en kopi af denne software og tilhørende dokumentationsfiler ("Softwaren"), til uden begrænsning at anvende Softwaren, herunder uden begrænsning retten til at bruge, kopiere, ændre, sammenflette, udgive, distribuere, underlicensere og/eller sælge kopier af Softwaren samt at tillade personer, som Softwaren leveres til, at gøre det samme, på følgende betingelser:\n\nOvenstående ophavsretsmeddelelse og denne tilladelsesmeddelelse skal medtages i alle kopier eller væsentlige dele af Softwaren.\n\nSOFTWAREN LEVERES "SOM DEN ER", UDEN NOGEN FORM FOR GARANTI, HVERKEN UDTRYKKELIG ELLER UNDERFORSTÅET, HERUNDER MEN IKKE BEGRÆNSET TIL GARANTIER FOR SALGBARHED, EGNETHED TIL ET BESTEMT FORMÅL OG IKKE-KRÆNKELSE. FORFATTERNE ELLER OPHAVSRETSINDEHAVERNE KAN UNDER INGEN OMSTÆNDIGHEDER HOLDES ANSVARLIGE FOR KRAV, SKADER ELLER ANDET ANSVAR, HVERKEN I HENHOLD TIL KONTRAKT, ERSTATNINGSRET ELLER PÅ ANDEN MÅDE, SOM OPSTÅR AF, UD FRA ELLER I FORBINDELSE MED SOFTWAREN ELLER BRUGEN AF ELLER ANDRE FORHOLD VEDRØRENDE SOFTWAREN.\n\nBemærk: Den danske tekst er kun en vejledende oversættelse. Den originale engelske MIT-licens nedenfor er den autoritative licenstekst.\n\n--- Original MIT License (English) ---\n\n'
    return danish + original

def share_text() -> str:
    if current_language() == 'da':
        return "ChromaPress — gratis open source-tilpasning af Linux-ISO'er til Windows og Linux.\nMIT-licenseret. Hvis ChromaPress er nyttigt for dig, må du meget gerne dele den officielle udgivelse."
    return 'ChromaPress — free and open-source Linux ISO customization for Windows and Linux.\nMIT licensed. If ChromaPress is useful to you, please help spread the word and share the official release.'

class AboutDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('About ChromaPress'))
        self.setWindowIcon(chromapress_icon())
        self.resize(820, 720)
        self.setMinimumSize(720, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        info_panel = QFrame()
        info_panel.setObjectName('aboutInfoPanel')
        info_panel.setStyleSheet(
            "QFrame#aboutInfoPanel {"
            " background: #f4f8fb;"
            " border: 1px solid #c8d6e2;"
            " border-radius: 6px;"
            "}"
            "QFrame#aboutInfoPanel QLabel {"
            " background: transparent;"
            " border: 0;"
            "}"
        )

        info_layout = QHBoxLayout(info_panel)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(14)

        icon = QLabel()
        pixmap = chromapress_icon().pixmap(72, 72)
        if not pixmap.isNull():
            icon.setPixmap(pixmap)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        info_layout.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(3)

        title = QLabel(tr('ChromaPress'))
        title.setObjectName('dialogTitle')

        version = QLabel(tr(f'Version {__version__}'))
        version.setStyleSheet('font-weight: 700;')

        description = QLabel(
            tr('Professional Linux ISO customization and image-servicing workbench.')
        )
        description.setWordWrap(True)

        copyright_label = QLabel(tr('Copyright © 2026 Janus Rokkjær'))
        copyright_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        license_label = QLabel(tr('License: MIT License'))

        share_note = QLabel(
            tr(
                'ChromaPress is free and open source. '
                'If it helps you, please help spread the word.'
            )
        )
        share_note.setWordWrap(True)

        text.addWidget(title)
        text.addWidget(version)
        text.addWidget(description)
        text.addWidget(copyright_label)
        text.addWidget(license_label)
        text.addWidget(share_note)

        info_layout.addLayout(text, 1)
        layout.addWidget(info_panel)

        logo_asset = asset_path('chromapress-logo.png')
        if logo_asset.is_file():
            logo_pixmap = QPixmap(str(logo_asset))
            if not logo_pixmap.isNull():
                logo = QLabel()
                logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                logo.setPixmap(
                    logo_pixmap.scaledToWidth(
                        560,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
                layout.addWidget(logo)

        license_view = QTextBrowser()
        license_view.setPlainText(license_text())
        license_view.setMinimumHeight(190)
        layout.addWidget(license_view, 1)

        buttons = QDialogButtonBox()

        share_button = buttons.addButton(
            tr('Share ChromaPress'),
            QDialogButtonBox.ButtonRole.ActionRole
        )
        share_button.setObjectName('shareChromaPressButton')
        share_button.setToolTip(
            tr('Copy a short ChromaPress sharing message to the clipboard')
        )
        share_button.clicked.connect(self._share)

        close_button = buttons.addButton(
            QDialogButtonBox.StandardButton.Close
        )
        close_button.setText(tr('Close'))
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)
    def _share(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(share_text())
        QMessageBox.information(self, tr('Share ChromaPress'), tr('A short ChromaPress sharing message has been copied to the clipboard.'))
