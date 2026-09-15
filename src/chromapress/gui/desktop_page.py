from __future__ import annotations
from chromapress.i18n import tr
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QLineEdit, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QMessageBox
from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.part5 import validate_desktop_payload, validate_kiosk_payload

class DesktopPage(QWidget):
    """Part 5 desktop-native defaults and generic kiosk modes."""
    stage_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis: dict = {}
        self.desktop_cap: dict = {}
        self.kiosk_cap: dict = {}
        layout = QVBoxLayout(self)
        title = QLabel(tr('Desktop'))
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        intro = QLabel(tr('Desktop settings are exposed only when a supported desktop family is positively detected. ChromaPress stages native-adapter intent and re-verifies exact target paths before apply. Generic kiosk modes never hard-code a website or provider.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        evidence = QGroupBox(tr('Detected desktop / kiosk capability'))
        ef = QFormLayout(evidence)
        self.desktop_value = QLabel(tr('UNKNOWN'))
        self.desktop_value.setWordWrap(True)
        self.adapter_value = QLabel(tr('—'))
        self.kiosk_value = QLabel(tr('UNKNOWN'))
        self.kiosk_value.setWordWrap(True)
        ef.addRow(tr('Desktop:'), self.desktop_value)
        ef.addRow(tr('Native adapter:'), self.adapter_value)
        ef.addRow(tr('Kiosk modes:'), self.kiosk_value)
        layout.addWidget(evidence)
        desktop = QGroupBox(tr('Desktop-native defaults — staged only'))
        df = QFormLayout(desktop)
        self.wallpaper = QLineEdit()
        self.wallpaper.setPlaceholderText(tr('/usr/share/backgrounds/company.jpg'))
        self.theme = QLineEdit()
        self.icons = QLineEdit()
        self.font = QLineEdit()
        self.panels = QLineEdit()
        self.panels.setPlaceholderText(tr('native layout/panel preset name'))
        self.menus = QLineEdit()
        self.shortcuts = QLineEdit()
        self.favorites = QLineEdit()
        self.desktop_icons = QComboBox()
        self.desktop_icons.addItem(tr('Preserve'), 'preserve')
        self.desktop_icons.addItem(tr('Enabled'), 'enabled')
        self.desktop_icons.addItem(tr('Disabled'), 'disabled')
        self.autostart = QLineEdit()
        self.autostart.setPlaceholderText(tr('/usr/bin/application --flag'))
        self.default_apps = QLineEdit()
        self.default_apps.setPlaceholderText(tr('browser=firefox.desktop, editor=org.kde.kate.desktop'))
        self.mime = QLineEdit()
        self.mime.setPlaceholderText(tr('text/plain=org.kde.kate.desktop'))
        self.display_manager = QComboBox()
        self.display_manager.addItem(tr('Preserve'), 'preserve')
        self.display_manager.addItem(tr('Normal login'), 'normal_login')
        self.login_behavior = QComboBox()
        self.login_behavior.addItem(tr('Preserve'), 'preserve')
        self.login_behavior.addItem(tr('Require explicit login'), 'explicit_login')
        self.layout_name = QLineEdit()
        self.layout_name.setPlaceholderText(tr('default-user-layout'))
        for label, widget in (('Wallpaper:', self.wallpaper), ('Theme:', self.theme), ('Icons:', self.icons), ('Font:', self.font), ('Panels:', self.panels), ('Menus:', self.menus), ('Shortcuts:', self.shortcuts), ('Favorites:', self.favorites), ('Desktop icons:', self.desktop_icons), ('Autostart:', self.autostart), ('Default applications:', self.default_apps), ('MIME associations:', self.mime), ('Display manager:', self.display_manager), ('Login behavior:', self.login_behavior), ('Default-user desktop layout:', self.layout_name)):
            df.addRow(tr(label), widget)
        self.stage_desktop_btn = QPushButton(tr('Stage desktop defaults'))
        df.addRow(self.stage_desktop_btn)
        layout.addWidget(desktop)
        kiosk = QGroupBox(tr('Kiosk / thin client — generic capability'))
        kf = QFormLayout(kiosk)
        self.kiosk_mode = QComboBox()
        self.kiosk_target = QLineEdit()
        self.kiosk_target.setPlaceholderText(tr('https://example.invalid or /usr/bin/my-app'))
        self.fullscreen = QCheckBox(tr('Fullscreen'))
        self.fullscreen.setChecked(True)
        self.kiosk_autostart = QCheckBox(tr('Autostart'))
        self.kiosk_autostart.setChecked(True)
        self.restricted_nav = QCheckBox(tr('Restricted navigation/session controls'))
        self.restricted_nav.setChecked(True)
        self.recovery_escape = QCheckBox(tr('Controlled administrator/recovery escape'))
        self.recovery_escape.setChecked(True)
        kf.addRow(tr('Mode:'), self.kiosk_mode)
        kf.addRow(tr('Browser URL / target executable:'), self.kiosk_target)
        kf.addRow(self.fullscreen)
        kf.addRow(self.kiosk_autostart)
        kf.addRow(self.restricted_nav)
        kf.addRow(self.recovery_escape)
        self.stage_kiosk_btn = QPushButton(tr('Stage kiosk/session policy'))
        kf.addRow(self.stage_kiosk_btn)
        layout.addWidget(kiosk)
        self.status = QLabel(tr('No source analyzed.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.stage_desktop_btn.clicked.connect(self._stage_desktop)
        self.stage_kiosk_btn.clicked.connect(self._stage_kiosk)
        self._set_desktop_enabled(False)
        self._set_kiosk_enabled(False)

    def _desktop_widgets(self):
        return (self.wallpaper, self.theme, self.icons, self.font, self.panels, self.menus, self.shortcuts, self.favorites, self.desktop_icons, self.autostart, self.default_apps, self.mime, self.display_manager, self.login_behavior, self.layout_name, self.stage_desktop_btn)

    def _set_desktop_enabled(self, enabled: bool) -> None:
        for w in self._desktop_widgets():
            w.setEnabled(enabled)

    def _set_kiosk_enabled(self, enabled: bool) -> None:
        for w in (self.kiosk_mode, self.kiosk_target, self.fullscreen, self.kiosk_autostart, self.restricted_nav, self.recovery_escape, self.stage_kiosk_btn):
            w.setEnabled(enabled)

    @staticmethod
    def _split_pairs(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw in text.split(','):
            if '=' not in raw:
                continue
            k, v = raw.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                out[k] = v
        return out

    def _desktop_controls(self) -> dict:
        controls: dict[str, object] = {}
        fields = {'wallpaper': self.wallpaper.text().strip(), 'theme': self.theme.text().strip(), 'icons': self.icons.text().strip(), 'font': self.font.text().strip(), 'panels': self.panels.text().strip(), 'menus': self.menus.text().strip(), 'shortcuts': self.shortcuts.text().strip(), 'favorites': self.favorites.text().strip(), 'autostart': self.autostart.text().strip(), 'default_user_desktop_layout': self.layout_name.text().strip()}
        controls.update({k: v for k, v in fields.items() if v})
        if self.desktop_icons.currentData() != 'preserve':
            controls['desktop_icons'] = self.desktop_icons.currentData()
        defaults = self._split_pairs(self.default_apps.text())
        mime = self._split_pairs(self.mime.text())
        if defaults:
            controls['default_applications'] = defaults
        if mime:
            controls['mime_associations'] = mime
        if self.display_manager.currentData() != 'preserve':
            controls['display_manager'] = self.display_manager.currentData()
        if self.login_behavior.currentData() != 'preserve':
            controls['login_behavior'] = self.login_behavior.currentData()
        return controls

    def _stage_desktop(self) -> None:
        cap = self.desktop_cap
        payload = {'config_type': 'part5_desktop_defaults', 'part': 5, 'gate_version': 'part5-complete', 'source_sha256': str(self.analysis.get('sha256') or '').strip().casefold(), 'analysis_scope': str(cap.get('analysis_scope') or ''), 'capability_status': str(cap.get('capability_status') or 'UNKNOWN'), 'active_desktop': str(cap.get('active_desktop') or ''), 'native_adapter': str(cap.get('native_adapter') or ''), 'controls': self._desktop_controls(), 'desktop_config_contents_read': False, 'host_desktop_state_accessed': False, 'require_native_adapter_reverification_before_apply': True, 'preserve_unrelated_desktop_configuration': True, 'source_read_only': True, 'stage_only': True}
        ok, msg = validate_desktop_payload(payload)
        if not ok:
            self.status.setText(tr(f'BLOCKED — {msg}'))
            QMessageBox.warning(self, tr('Desktop plan blocked'), tr(msg))
            return
        self.stage_requested.emit(ChangeItem('Part 5 desktop defaults', ChangeKind.CONFIG, f"{payload['active_desktop']} via {payload['native_adapter']}; {len(payload['controls'])} reviewed controls.", payload))
        self.status.setText(tr('STAGED — desktop-native paths must be re-verified before apply.'))

    def _stage_kiosk(self) -> None:
        cap = self.kiosk_cap
        payload = {'config_type': 'part5_kiosk_session', 'part': 5, 'gate_version': 'part5-complete', 'source_sha256': str(self.analysis.get('sha256') or '').strip().casefold(), 'analysis_scope': str(cap.get('analysis_scope') or ''), 'capability_status': str(cap.get('capability_status') or 'UNKNOWN'), 'supported_modes': list(cap.get('supported_modes') or []), 'mode': str(self.kiosk_mode.currentData() or ''), 'target': self.kiosk_target.text().strip(), 'weston_verified': cap.get('weston_verified') is True, 'browser_packages': list(cap.get('browser_packages') or []), 'fullscreen': self.fullscreen.isChecked(), 'autostart': self.kiosk_autostart.isChecked(), 'restricted_navigation': self.restricted_nav.isChecked(), 'restricted_session_controls': self.restricted_nav.isChecked(), 'controlled_recovery_escape': self.recovery_escape.isChecked(), 'provider_or_website_hardcoded': False, 'require_runtime_session_validation_before_apply': True, 'require_part4_security_review_before_apply': True, 'source_read_only': True, 'stage_only': True}
        ok, msg = validate_kiosk_payload(payload)
        if not ok:
            self.status.setText(tr(f'BLOCKED — {msg}'))
            QMessageBox.warning(self, tr('Kiosk plan blocked'), tr(msg))
            return
        self.stage_requested.emit(ChangeItem('Part 5 kiosk/session policy', ChangeKind.CONFIG, f"Generic mode {payload['mode']}; runtime session validation and recovery review required.", payload))
        self.status.setText(tr('STAGED — generic kiosk/session policy; runtime VM validation remains mandatory.'))

    def set_analysis(self, data: dict) -> None:
        self.analysis = dict(data or {})
        self.desktop_cap = dict(data.get('part5_desktop_evidence') or {})
        self.kiosk_cap = dict(data.get('part5_kiosk_evidence') or {})
        ds = str(self.desktop_cap.get('capability_status') or 'UNKNOWN')
        self.desktop_value.setText(tr(f"{ds} — {self.desktop_cap.get('active_desktop') or 'no single verified desktop'}"))
        self.adapter_value.setText(str(self.desktop_cap.get('native_adapter') or tr('—')))
        ks = str(self.kiosk_cap.get('capability_status') or 'UNKNOWN')
        modes = list(self.kiosk_cap.get('supported_modes') or [])
        self.kiosk_value.setText(tr(f'{ks} — ') + (', '.join(modes) if modes else tr('no verified generic kiosk mode')))
        self._set_desktop_enabled(ds in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'} and bool(data.get('sha256')))
        self.kiosk_mode.clear()
        labels = {'full_desktop': 'Full desktop', 'restricted_desktop': 'Restricted desktop', 'minimal_wayland_weston': 'Minimal Wayland / Weston', 'browser_kiosk': 'Browser kiosk', 'custom_application_kiosk': 'Custom application kiosk'}
        for mode in modes:
            self.kiosk_mode.addItem(labels.get(mode, mode), mode)
        self._set_kiosk_enabled(ks in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'} and bool(modes) and bool(data.get('sha256')))
        self.status.setText(str(self.desktop_cap.get('reason') or self.kiosk_cap.get('reason') or tr('Analyze a source ISO first.')))
