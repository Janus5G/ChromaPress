from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
    QFileDialog, QMessageBox, QToolBar, QLabel, QSplitter, QToolButton,
    QScrollArea, QFrame
)

from chromapress.models import ProjectState, SourceState, ChangeItem, ChangeStatus
from chromapress.scenarios import scenario_by_id
from chromapress.settings import AppSettings
from .source_page import SourcePage
from .overview_page import OverviewPage
from .applications_page import ApplicationsPage
from .components_page import ComponentsPage
from .about_dialog import AboutDialog, chromapress_icon
from chromapress import __version__
from .ai_studio import AiStudioPage
from .changes import ChangesPanel
from .settings_dialog import SettingsDialog
from .review_pages import ProjectPlanPage
from .production_page import ProductionWorkflowPage
from .boot_hardware_page import BootHardwarePage
from .installer_page import InstallerPage
from .files_page import FilesPage
from .desktop_page import DesktopPage
from .system_page import SystemPage


NAV = [
    "Source", "Overview", "Applications", "Components", "Files", "System",
    "Boot & Hardware", "Installer", "Desktop", "AI App Studio", "Changes", "Build & Verify"
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChromaPress")
        self.setWindowIcon(chromapress_icon())
        self.resize(1500, 900)
        self.project = ProjectState()
        self.qsettings = QSettings("ChromaPress", "ChromaPress")
        base = Path.home() / "ChromaPress"
        self.settings = AppSettings.defaults(base)
        self._load_settings()

        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        new_action = QAction("New Project", self); open_action = QAction("Open Project", self); save_action = QAction("Save Project", self); settings_action = QAction("Settings", self); about_action = QAction("About", self)
        toolbar.addAction(new_action); toolbar.addAction(open_action); toolbar.addAction(save_action); toolbar.addSeparator(); toolbar.addAction(settings_action); toolbar.addSeparator(); toolbar.addAction(about_action)
        new_action.triggered.connect(self.new_project); open_action.triggered.connect(self.open_project); save_action.triggered.connect(self.save_project); settings_action.triggered.connect(self.open_settings); about_action.triggered.connect(self.open_about)

        central = QWidget(); outer = QHBoxLayout(central); outer.setContentsMargins(0,0,0,0)
        self.nav = QListWidget(); self.nav.setFixedWidth(220)
        self.stack = QStackedWidget()
        self.changes = ChangesPanel(); self.changes.set_changes(self.project.changes)
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.addWidget(self.stack)
        self.content_splitter.addWidget(self.changes)
        self.content_splitter.setCollapsible(0, False)
        self.content_splitter.setCollapsible(1, True)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 0)
        self.content_splitter.setSizes([1120, 320])
        self._last_changes_width = 320
        self.changes_toggle = QToolButton()
        self.changes_toggle.setText("▶")
        self.changes_toggle.setToolTip("Collapse Changes panel")
        self.changes_toggle.setFixedWidth(28)
        self.changes_toggle.clicked.connect(self._toggle_changes_panel)
        outer.addWidget(self.nav)
        outer.addWidget(self.content_splitter, 1)
        outer.addWidget(self.changes_toggle)
        self.setCentralWidget(central)

        self.source = SourcePage(self.settings)
        self.overview = OverviewPage()
        self.apps = ApplicationsPage(self.settings)
        self.components = ComponentsPage()
        self.ai = AiStudioPage(self.settings)
        self.boot_hardware = BootHardwarePage()
        self.system_page = SystemPage()
        self.installer = InstallerPage()
        self.files_page = FilesPage()
        self.desktop_page = DesktopPage()
        self.live_plan = ProjectPlanPage(final_review=False)
        self.production = ProductionWorkflowPage()
        pages = [
            self.source,
            self.overview,
            self.apps,
            self.components,
            self.files_page,
            self.system_page,
            self.boot_hardware,
            self.installer,
            self.desktop_page,
            self.ai,
            self.live_plan,
            self.production,
        ]
        self.page_hosts = []
        for name, page in zip(NAV, pages):
            self.nav.addItem(QListWidgetItem(name))
            host = QScrollArea()
            host.setObjectName("pageScrollHost")
            host.setWidgetResizable(True)
            host.setFrameShape(QFrame.Shape.NoFrame)
            host.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            host.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            host.setWidget(page)
            self.page_hosts.append(host)
            self.stack.addWidget(host)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)

        self.source.source_analyzed.connect(self.set_analysis)
        self.apps.change_requested.connect(self.add_change)
        self.components.change_requested.connect(self.add_change)
        self.boot_hardware.stage_requested.connect(self._stage_boot_change)
        self.system_page.stage_requested.connect(self._stage_system_change)
        self.installer.stage_requested.connect(self._stage_part5_change)
        self.files_page.stage_requested.connect(self._stage_part5_change)
        self.desktop_page.stage_requested.connect(self._stage_part5_change)
        self.apps.scenario_changed.connect(self.set_scenario)
        self.apps.open_ai_requested.connect(lambda: self.nav.setCurrentRow(NAV.index("AI App Studio")))
        self.apps.catalog_changed.connect(lambda _summary: self._refresh_review_pages())
        self.apps.undo_remove_requested.connect(self.changes.undo_package_remove)
        self.apps.undo_installed_change_requested.connect(self.changes.undo_installed_change)
        self.apps.undo_add_requested.connect(self.changes.undo_package_add)
        self.ai.change_requested.connect(self.add_change)
        self.ai.settings_requested.connect(self.open_settings)
        self.ai.configuration_changed.connect(self._save_settings)
        self.production.stage_requested.connect(self._stage_part7_change)
        self.production.import_requested.connect(self._import_part7_profile)
        self.changes.changed.connect(self._project_changed)
        self.changes.review_requested.connect(lambda: self.nav.setCurrentRow(NAV.index("Changes")))
        self.statusBar().addPermanentWidget(QLabel(__version__))
        self._apply_style()
        self._refresh_review_pages()

    def _toggle_changes_panel(self) -> None:
        if self.changes.isVisible():
            sizes = self.content_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 0:
                self._last_changes_width = max(280, sizes[1])
            self.changes.hide()
            self.changes_toggle.setText("◀")
            self.changes_toggle.setToolTip("Expand Changes panel")
        else:
            self.changes.show()
            total = max(600, sum(self.content_splitter.sizes()))
            width = min(max(280, self._last_changes_width), max(280, total // 2))
            self.content_splitter.setSizes([max(320, total - width), width])
            self.changes_toggle.setText("▶")
            self.changes_toggle.setToolTip("Collapse Changes panel")

    def _refresh_review_pages(self) -> None:
        summary = self.apps.catalog_summary() if hasattr(self, "apps") else {}
        self.live_plan.update_plan(self.project, summary)
        self.production.set_project(self.project)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f6f7f9; color: #20242a; font-size: 13px; }
            QToolBar { background: #ffffff; border-bottom: 1px solid #d8dde5; spacing: 8px; padding: 6px; }
            QListWidget { background: #202631; color: #e8edf5; border: 0; padding: 10px 0; font-size: 14px; }
            QListWidget::item { padding: 10px 14px; margin: 1px 6px; border-radius: 5px; }
            QListWidget::item:selected { background: #3a4658; }
            QGroupBox { background: #ffffff; border: 1px solid #d8dde5; border-radius: 7px; margin-top: 12px; padding: 14px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QPushButton { background: #ffffff; border: 1px solid #c8ced8; border-radius: 5px; padding: 7px 11px; }
            QPushButton:hover { background: #eef2f7; }
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget, QTreeWidget { background: #ffffff; border: 1px solid #cfd5df; border-radius: 4px; padding: 5px; }
            QLabel#pageTitle { font-size: 24px; font-weight: 700; padding: 4px 0 8px 0; }
            QLabel#panelTitle { font-size: 18px; font-weight: 700; }
            QLabel#dialogTitle { font-size: 20px; font-weight: 700; padding: 4px 0 8px 0; }
            QToolButton { background: transparent; border: 0; padding: 5px 2px; font-weight: 600; }
            QScrollArea#pageScrollHost { background: #f6f7f9; border: 0; }
        """)

    def _load_settings(self):
        from chromapress.services.ai_catalog import normalize_provider_id, normalized_model_id

        s = self.qsettings
        self.settings.storage_root = s.value("storage_root", self.settings.storage_root)
        self.settings.wsl_distro = s.value("wsl_distro", self.settings.wsl_distro)
        self.settings.workspace_dir = s.value("workspace_dir", self.settings.workspace_dir)
        self.settings.cache_dir = s.value("cache_dir", self.settings.cache_dir)
        self.settings.reserve_gb = int(s.value("reserve_gb", self.settings.reserve_gb))
        self.settings.ai_provider = normalize_provider_id(s.value("ai_provider", self.settings.ai_provider))
        self.settings.ai_model = normalized_model_id(
            self.settings.ai_provider, s.value("ai_model", self.settings.ai_model)
        )
        self.settings.ai_endpoint = s.value("ai_endpoint", self.settings.ai_endpoint)
        self.settings.cpl_toolchain_path = s.value("cpl_toolchain_path", self.settings.cpl_toolchain_path)

        # Migrate the alpha-1 two-path setup into the simple storage root when
        # both paths share one parent.
        if not self.settings.storage_root and self.settings.workspace_dir and self.settings.cache_dir:
            w_parent = Path(self.settings.workspace_dir).parent
            c_parent = Path(self.settings.cache_dir).parent
            if w_parent == c_parent:
                self.settings.storage_root = str(w_parent)

    def _save_settings(self):
        s = self.qsettings
        for key in (
            "storage_root", "wsl_distro", "workspace_dir", "cache_dir",
            "reserve_gb", "ai_provider", "ai_model", "ai_endpoint",
            "cpl_toolchain_path",
        ):
            s.setValue(key, getattr(self.settings, key))
        # ai_api_key is deliberately NOT written to QSettings.
        self.source.settings = self.settings
        self.apps.set_settings(self.settings)
        self.ai.settings = self.settings

    def open_about(self):
        AboutDialog(self).exec()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            dialog.apply()
            self._save_settings()
            self.ai.refresh_from_settings()

    def _refresh_ai_target_context(self):
        from chromapress.services.part6 import target_context_from_source
        scenario_label = ""
        scenario_context = ""
        if self.project.scenario:
            scenario = scenario_by_id(self.project.scenario)
            scenario_label = scenario.label
            scenario_context = scenario.ai_context
        self.ai.set_target_context(target_context_from_source(self.project.source, scenario_label, scenario_context))

    def set_scenario(self, scenario_id: str):
        self.project.scenario = scenario_id
        self._refresh_ai_target_context()
        self._refresh_review_pages()
        self.statusBar().showMessage(f"SYSTEM USE SET — {scenario_by_id(scenario_id).label}", 5000)

    def add_change(self, change: ChangeItem):
        self.changes.add_change(change)

    def _stage_boot_change(self, change: ChangeItem):
        # Keep one staged plan per Part 3 configuration type. Replacing a plan is
        # explicit and safe; source bytes remain untouched at this gate.
        config_type = str(change.payload.get("config_type", "")).strip()
        self.project.changes[:] = [
            existing for existing in self.project.changes
            if not (
                existing.kind.value == "config"
                and str(existing.payload.get("config_type", "")).strip() == config_type
            )
        ]
        self.changes.add_change(change)

    def _stage_system_change(self, change: ChangeItem):
        # One active staged plan per Part 4 logical target. Alpha 50+ account plans
        # may safely coexist for different target users/groups via plan_slot;
        # re-staging the same slot replaces only that target plan.
        config_type = str(change.payload.get("config_type", "")).strip()
        plan_slot = str(change.payload.get("plan_slot", "")).strip()
        def same_logical_plan(existing: ChangeItem) -> bool:
            if existing.kind.value != "config":
                return False
            if str(existing.payload.get("config_type", "")).strip() != config_type:
                return False
            if config_type == "system_identity" and plan_slot:
                return str(existing.payload.get("plan_slot", "")).strip() == plan_slot
            return True
        self.project.changes[:] = [existing for existing in self.project.changes if not same_logical_plan(existing)]
        self.changes.add_change(change)

    def _stage_part5_change(self, change: ChangeItem):
        config_type = str(change.payload.get("config_type", "")).strip()
        self.project.changes[:] = [
            existing for existing in self.project.changes
            if not (existing.kind.value == "config" and str(existing.payload.get("config_type", "")).strip() == config_type)
        ]
        self.changes.add_change(change)

    def _guard_part5_plan_source(self, source_sha256: str) -> None:
        source_sha256 = str(source_sha256 or "").strip().casefold()
        changed = False
        for change in self.project.changes:
            config_type = str(change.payload.get("config_type", "")).strip()
            if change.kind.value != "config" or config_type not in {
                "part5_installer_profile", "part5_custom_content", "part5_desktop_defaults", "part5_kiosk_session",
            }:
                continue
            locked = str(change.payload.get("source_sha256", "")).strip().casefold()
            if source_sha256 and locked and source_sha256 != locked:
                change.status = ChangeStatus.BLOCKED
                marker = "Source changed after this Part 5 plan was staged; restage it for the current ISO."
                if marker not in change.detail:
                    change.detail = f"{change.detail} {marker}".strip()
                changed = True
        if changed:
            self.changes.refresh(select_fallback=True)

    def _guard_part6_plan_source(self, source_sha256: str) -> None:
        source_sha256 = str(source_sha256 or "").strip().casefold()
        changed = False
        for change in self.project.changes:
            if change.kind.value != "ai_app" or str(change.payload.get("config_type", "")).strip() != "part6_ai_app_project":
                continue
            locked = str(change.payload.get("source_sha256", "")).strip().casefold()
            if source_sha256 and locked and source_sha256 != locked:
                change.status = ChangeStatus.BLOCKED
                marker = "Source changed after this Part 6 AI app was staged; regenerate/restage it for the current ISO."
                if marker not in change.detail:
                    change.detail = f"{change.detail} {marker}".strip()
                changed = True
        if changed:
            self.changes.refresh(select_fallback=True)

    def _stage_part7_change(self, change: ChangeItem):
        config_type = str(change.payload.get("config_type", "")).strip()
        self.project.changes[:] = [
            existing for existing in self.project.changes
            if not (existing.kind.value == "config" and str(existing.payload.get("config_type", "")).strip() == config_type)
        ]
        self.changes.add_change(change)

    def _import_part7_profile(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        changes = payload.get("changes")
        if not isinstance(changes, list) or not all(isinstance(x, ChangeItem) for x in changes):
            QMessageBox.warning(self, "Profile import blocked", "Imported profile did not contain a valid verified change plan.")
            return
        # The Production page has already preflighted each imported change. Replace
        # the declarative plan only; never mutate the selected source image here.
        self.project.changes[:] = changes
        scenario = str(payload.get("scenario") or "")
        if scenario:
            try:
                scenario_by_id(scenario)
                self.project.scenario = scenario
                self.apps.set_scenario(scenario, emit=False)
            except Exception:
                pass
        self.changes.set_changes(self.project.changes)
        self._project_changed()
        self.statusBar().showMessage("VERIFIED PROFILE PLAN IMPORTED — source ISO unchanged", 7000)

    def _guard_part7_plan_source(self, source_sha256: str) -> None:
        source_sha256 = str(source_sha256 or "").strip().casefold()
        changed = False
        for change in self.project.changes:
            if change.kind.value != "config" or str(change.payload.get("config_type", "")).strip() != "part7_production_build_plan":
                continue
            locked = str(change.payload.get("source_sha256", "")).strip().casefold()
            if source_sha256 and locked and source_sha256 != locked:
                change.status = ChangeStatus.BLOCKED
                marker = "Source changed after this Part 7 production plan was staged; preflight/restage it for the current ISO."
                if marker not in change.detail:
                    change.detail = f"{change.detail} {marker}".strip()
                changed = True
        if changed:
            self.changes.refresh(select_fallback=True)

    def _guard_system_plan_source(self, source_sha256: str) -> None:
        source_sha256 = str(source_sha256 or "").strip().casefold()
        changed = False
        for change in self.project.changes:
            config_type = str(change.payload.get("config_type", "")).strip()
            if change.kind.value != "config" or config_type not in {
                "system_identity", "system_machine_identity", "system_autologin", "system_locale",
                "system_keyboard", "system_timezone", "system_network_dns", "system_services",
                "system_timers", "system_targets", "system_firewall", "system_apparmor",
                "system_selinux", "system_sysctl", "system_security_defaults", "system_config_overlay",
                "dedicated_kiosk_user", "restricted_login", "restricted_session", "service_lockdown",
                "network_restriction", "firewall_rule", "persistence_policy", "administrator_recovery_policy", "fido2_policy", "webauthn_policy",
                "security_key_policy", "yubikey_policy", "platform_authenticator_policy", "tpm_key_protection",
            }:
                continue
            locked = str(change.payload.get("source_sha256", "")).strip().casefold()
            if source_sha256 and locked and source_sha256 != locked:
                change.status = ChangeStatus.BLOCKED
                marker = "Source changed after this Part 4 plan was staged; restage it for the current ISO."
                if marker not in change.detail:
                    change.detail = f"{change.detail} {marker}".strip()
                changed = True
        if changed:
            self.changes.refresh(select_fallback=True)

    def _guard_boot_plan_source(self, source_sha256: str) -> None:
        source_sha256 = str(source_sha256 or "").strip().casefold()
        changed = False
        for change in self.project.changes:
            config_type = str(change.payload.get("config_type", "")).strip()
            if change.kind.value != "config" or config_type not in {"boot", "boot_metadata", "kernel_initramfs", "hardware_package", "rootfs_squashfs", "immutable_runtime", "controlled_persistence", "runtime_integration"}:
                continue
            locked = str(change.payload.get("source_sha256", "")).strip().casefold()
            if source_sha256 and locked and source_sha256 != locked:
                change.status = ChangeStatus.BLOCKED
                marker = "Source changed after this Part 3 plan was staged; restage it for the current ISO."
                if marker not in change.detail:
                    change.detail = f"{change.detail} {marker}".strip()
                changed = True
        if changed:
            self.changes.refresh(select_fallback=True)

    def _project_changed(self):
        # Rebuild row action widgets after the current click/Undo event has
        # returned to Qt. This avoids deleting the clicked button mid-signal.
        QTimer.singleShot(0, lambda: self.apps.set_staged_changes(self.project.changes))
        QTimer.singleShot(0, lambda: self.components.set_staged_changes(self.project.changes))
        self.boot_hardware.set_staged_changes(self.project.changes)
        self._refresh_review_pages()
        n = len(self.project.changes)
        self.changes_toggle.setToolTip(
            ("Collapse Changes panel" if self.changes.isVisible() else "Expand Changes panel")
            + (f" — {n} staged" if n else " — no staged changes")
        )

    def set_analysis(self, data: dict):
        self._guard_boot_plan_source(str(data.get("sha256") or ""))
        self._guard_system_plan_source(str(data.get("sha256") or ""))
        self._guard_part5_plan_source(str(data.get("sha256") or ""))
        self._guard_part6_plan_source(str(data.get("sha256") or ""))
        self._guard_part7_plan_source(str(data.get("sha256") or ""))
        self.overview.set_analysis(data)
        self.project.source = SourceState(
            kind=data.get("source_kind", "existing"), path=data.get("path", ""), distribution=data.get("distribution", ""),
            version=data.get("version", ""), architecture=data.get("architecture", ""), sha256=data.get("sha256", ""),
            volume_id=data.get("volume_id", ""), installer=data.get("installer", ""),
            installer_evidence=list(data.get("installer_evidence") or []),
            installer_config_files=list(data.get("installer_config_files") or []),
            installer_modes=list(data.get("installer_modes") or []),
            part5_installer_evidence=dict(data.get("part5_installer_evidence") or {}),
            part5_custom_content_evidence=dict(data.get("part5_custom_content_evidence") or {}),
            part5_desktop_evidence=dict(data.get("part5_desktop_evidence") or {}),
            part5_kiosk_evidence=dict(data.get("part5_kiosk_evidence") or {}),
            os_release_evidence=dict(data.get("os_release_evidence") or {}),
            package_format=data.get("package_format", ""),
            bios_boot=bool(data.get("bios_boot")), uefi_boot=bool(data.get("uefi_boot")),
            el_torito_boot=bool(data.get("el_torito_boot")), hybrid_boot=bool(data.get("hybrid_boot")),
            bootloaders=list(data.get("bootloaders") or []), boot_catalog=data.get("boot_catalog", ""),
            boot_config_files=list(data.get("boot_config_files") or []), efi_images=list(data.get("efi_images") or []),
            kernel_images=list(data.get("kernel_images") or []), initramfs_images=list(data.get("initramfs_images") or []),
            firmware_hints=list(data.get("firmware_hints") or []),
            boot_entries=list(data.get("boot_entries") or []), boot_defaults=list(data.get("boot_defaults") or []),
            boot_timeouts=list(data.get("boot_timeouts") or []), kernel_arguments=list(data.get("kernel_arguments") or []),
            initramfs_mechanism=str(data.get("initramfs_mechanism") or ""),
            hardware_package_hints=list(data.get("hardware_package_hints") or []),
            component_inventory=list(data.get("component_inventory") or []),
            system_package_evidence=list(data.get("system_package_evidence") or []),
            system_rootfs_verification=list(data.get("system_rootfs_verification") or []),
            system_identity_evidence=dict(data.get("system_identity_evidence") or {}),
            system_machine_identity_evidence=dict(data.get("system_machine_identity_evidence") or {}),
            system_autologin_evidence=dict(data.get("system_autologin_evidence") or {}),
            system_locale_evidence=dict(data.get("system_locale_evidence") or {}),
            system_keyboard_evidence=dict(data.get("system_keyboard_evidence") or {}),
            system_timezone_evidence=dict(data.get("system_timezone_evidence") or {}),
            system_network_dns_evidence=dict(data.get("system_network_dns_evidence") or {}),
            system_services_evidence=dict(data.get("system_services_evidence") or {}),
            system_timers_evidence=dict(data.get("system_timers_evidence") or {}),
            system_targets_evidence=dict(data.get("system_targets_evidence") or {}),
            system_firewall_evidence=dict(data.get("system_firewall_evidence") or {}),
            system_apparmor_evidence=dict(data.get("system_apparmor_evidence") or {}),
            system_selinux_evidence=dict(data.get("system_selinux_evidence") or {}),
            system_sysctl_evidence=dict(data.get("system_sysctl_evidence") or {}),
            system_config_overlay_evidence=dict(data.get("system_config_overlay_evidence") or {}),
            system_kiosk_user_evidence=dict(data.get("system_kiosk_user_evidence") or {}),
            system_restricted_login_evidence=dict(data.get("system_restricted_login_evidence") or {}),
            system_restricted_session_evidence=dict(data.get("system_restricted_session_evidence") or {}),
            system_service_lockdown_evidence=dict(data.get("system_service_lockdown_evidence") or {}),
            system_security_defaults_evidence=dict(data.get("system_security_defaults_evidence") or {}),
            system_network_restriction_evidence=dict(data.get("system_network_restriction_evidence") or {}),
            system_firewall_rules_evidence=dict(data.get("system_firewall_rules_evidence") or {}),
            system_persistence_policy_evidence=dict(data.get("system_persistence_policy_evidence") or {}),
            system_admin_recovery_policy_evidence=dict(data.get("system_admin_recovery_policy_evidence") or {}),
            system_fido2_policy_evidence=dict(data.get("system_fido2_policy_evidence") or {}),
            system_webauthn_policy_evidence=dict(data.get("system_webauthn_policy_evidence") or {}),
            system_security_key_policy_evidence=dict(data.get("system_security_key_policy_evidence") or {}),
            system_yubikey_policy_evidence=dict(data.get("system_yubikey_policy_evidence") or {}),
            system_platform_authenticator_policy_evidence=dict(data.get("system_platform_authenticator_policy_evidence") or {}),
            system_tpm_key_protection_evidence=dict(data.get("system_tpm_key_protection_evidence") or {}),
            rootfs=list(data.get("rootfs") or []), rootfs_details=list(data.get("rootfs_details") or []),
        )
        self.components.set_analysis(data)
        self.components.set_staged_changes(self.project.changes)
        self.system_page.set_analysis(data)
        self.boot_hardware.set_analysis(data)
        self.boot_hardware.set_staged_changes(self.project.changes)
        self.installer.set_analysis(data)
        self.files_page.set_analysis(data)
        self.desktop_page.set_analysis(data)
        self._refresh_ai_target_context()
        self.apps.set_scenario(self.project.scenario, emit=False)
        self.apps.set_source(data)
        self.apps.set_staged_changes(self.project.changes)
        self._refresh_review_pages()
        self.nav.setCurrentRow(NAV.index("Overview"))
        self.statusBar().showMessage("IMAGE ANALYZED — source remains read-only", 8000)

    def new_project(self):
        if self.project.changes:
            if QMessageBox.question(self, "New project", "Discard the current staged changes?") != QMessageBox.StandardButton.Yes:
                return
        self.project = ProjectState(); self.changes.set_changes(self.project.changes); self.overview.set_analysis({}); self.components.set_analysis({}); self.components.set_staged_changes(self.project.changes); self.system_page.set_analysis({}); self.boot_hardware.set_analysis({}); self.boot_hardware.set_staged_changes(self.project.changes); self.installer.set_analysis({}); self.files_page.set_analysis({}); self.desktop_page.set_analysis({}); self.apps.set_source({}); self.apps.set_scenario("", emit=False); self.apps.set_staged_changes(self.project.changes); self._refresh_ai_target_context(); self._refresh_review_pages(); self.nav.setCurrentRow(0)

    def save_project(self):
        path = self.project.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save ChromaPress project", "", "ChromaPress Project (*.chromapress)")
        if not path: return
        if not path.lower().endswith(".chromapress"): path += ".chromapress"
        self.project.save(Path(path)); self.statusBar().showMessage(f"Saved {path}", 5000)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open ChromaPress project", "", "ChromaPress Project (*.chromapress)")
        if not path: return
        try:
            self.project = ProjectState.load(Path(path)); self.changes.set_changes(self.project.changes)
            source_data = self.project.source.__dict__ | {"path": self.project.source.path}
            self.overview.set_analysis(source_data)
            self.components.set_analysis(source_data)
            self.components.set_staged_changes(self.project.changes)
            self.system_page.set_analysis(source_data)
            self.boot_hardware.set_analysis(source_data)
            self.boot_hardware.set_staged_changes(self.project.changes)
            self.installer.set_analysis(source_data)
            self.files_page.set_analysis(source_data)
            self.desktop_page.set_analysis(source_data)
            self.apps.set_scenario(self.project.scenario, emit=False)
            self.apps.set_source(source_data)
            self.apps.set_staged_changes(self.project.changes)
            self._refresh_ai_target_context()
            self._refresh_review_pages()
            self.nav.setCurrentRow(NAV.index("Overview"))
        except Exception as exc:
            QMessageBox.critical(self, "Open project failed", str(exc))
