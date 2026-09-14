from __future__ import annotations

from pathlib import Path
import json
import re

from PySide6.QtCore import QObject, QThread, Signal, Slot, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QHeaderView, QFileDialog, QDialog, QDialogButtonBox, QLineEdit,
    QFormLayout, QGroupBox, QProgressBar, QTableWidgetItem, QMessageBox,
    QButtonGroup, QCheckBox, QTreeWidget, QTreeWidgetItem, QStyle
)

from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.wsl import WslBridge
from chromapress.services.paths import asset_path
from chromapress.scenarios import (
    SCENARIOS, relevance_score, application_section, suite_group, section_order_for_scenario,
    personal_home_group, HOME_GROUP_DESCRIPTIONS, missing_home_recommendations,
    HOME_EVERYDAY_SUBGROUPS, HOME_SPECIALIST_SUBGROUPS, HomeRecommendation,
    HOME_RECOMMENDATIONS, SCENARIO_RECOMMENDATIONS, home_recommendations_supported,
    scenario_recommendations_supported, missing_scenario_recommendations,
    SCENARIO_RECOMMENDATION_DESCRIPTIONS, scenario_by_id
)


class TextEntryDialog(QDialog):
    def __init__(self, title: str, field_label: str, help_text: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 420)
        self.setMinimumSize(680, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(title); heading.setObjectName("dialogTitle"); layout.addWidget(heading)
        help_label = QLabel(help_text); help_label.setWordWrap(True); layout.addWidget(help_label)
        box = QGroupBox("Application source"); form = QFormLayout(box)
        self.value = QLineEdit(); self.value.setPlaceholderText(placeholder); self.value.setMinimumHeight(34)
        form.addRow(field_label, self.value); layout.addWidget(box); layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.value.returnPressed.connect(self.accept)

    def text(self) -> str:
        return self.value.text().strip()


class GitEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install/build from Git")
        self.resize(760, 420); self.setMinimumSize(680, 360)
        layout = QVBoxLayout(self)
        heading = QLabel("Install/build from Git"); heading.setObjectName("dialogTitle"); layout.addWidget(heading)
        help_label = QLabel("Enter the repository address. ChromaPress will inspect the source and build system in an isolated workspace before anything is staged for the image.")
        help_label.setWordWrap(True); layout.addWidget(help_label)
        box = QGroupBox("Git source"); form = QFormLayout(box)
        self.url = QLineEdit(); self.url.setPlaceholderText("https://github.com/owner/project.git")
        self.ref = QLineEdit(); self.ref.setPlaceholderText("Optional branch, tag or commit")
        self.url.setMinimumHeight(34); self.ref.setMinimumHeight(34)
        form.addRow("Repository URL:", self.url); form.addRow("Version/ref:", self.ref)
        layout.addWidget(box); layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)


class CatalogWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, settings, source: dict):
        super().__init__()
        self.settings = settings
        self.source = source

    @Slot()
    def run(self):
        try:
            bridge = WslBridge(self.settings.wsl_distro)
            result = bridge.application_catalog(
                str(self.source.get("path", "")),
                self.settings.workspace_dir,
                self.settings.reserve_gb,
                self.settings.cache_dir,
                str(self.source.get("sha256", "")),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ApplicationsPage(QWidget):
    change_requested = Signal(object)
    open_ai_requested = Signal()
    scenario_changed = Signal(str)
    catalog_changed = Signal(object)
    undo_remove_requested = Signal(str)
    undo_installed_change_requested = Signal(str)
    undo_add_requested = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._source: dict = {}
        self._catalog: list[dict] = []
        self._thread: QThread | None = None
        self._worker: CatalogWorker | None = None
        self._scenario_id = ""
        self._staged_remove_packages: set[str] = set()
        self._staged_remove_refs: set[str] = set()
        self._staged_replace_refs: set[str] = set()
        self._staged_add_packages: set[str] = set()
        self._catalog_read_method = ""
        self._catalog_loaded = False

        layout = QVBoxLayout(self)
        title = QLabel("Applications"); title.setObjectName("pageTitle")
        subtitle = QLabel("Choose what programs you want in the Linux image. Start by selecting the intended use of the finished system; this only prioritises the application view and gives AI better context.")
        subtitle.setWordWrap(True); layout.addWidget(title); layout.addWidget(subtitle)

        scenario_box = QGroupBox("1. Intended system use")
        scenario_layout = QHBoxLayout(scenario_box)
        self.scenario_group = QButtonGroup(self)
        self.scenario_group.setExclusive(True)
        self.scenario_buttons = {}
        for scenario in SCENARIOS:
            button = QPushButton(scenario.label)
            button.setCheckable(True)
            # Keep the active system-use profile visibly selected.  This is a
            # presentation cue only; it does not change the source image.
            button.setStyleSheet(
                "QPushButton:checked { background-color: #d8dde4; "
                "border: 1px solid #87929f; font-weight: 600; }"
            )
            button.setToolTip(scenario.ai_context)
            self.scenario_group.addButton(button)
            self.scenario_buttons[scenario.id] = button
            scenario_layout.addWidget(button)
        layout.addWidget(scenario_box)

        self.show_all = QCheckBox("Show all applications")
        self.show_all.setChecked(False)
        self.show_all.setEnabled(False)
        layout.addWidget(self.show_all)

        tools = QHBoxLayout()
        self.repo = QPushButton("Add from repository")
        self.url = QPushButton("Direct link")
        self.local = QPushButton("Local package/file")
        self.git = QPushButton("Git repository")
        self.ai = QPushButton("Create with AI")
        for b in (self.repo, self.url, self.local, self.git, self.ai): tools.addWidget(b)
        tools.addStretch(1); layout.addLayout(tools)

        status_row = QHBoxLayout()
        self.catalog_status = QLabel("Open or download a Linux image to load its applications.")
        self.catalog_status.setWordWrap(True)
        self.reload = QPushButton("Reload applications"); self.reload.setEnabled(False)
        status_row.addWidget(self.catalog_status, 1); status_row.addWidget(self.reload)
        layout.addLayout(status_row)
        self.catalog_progress = QProgressBar(); self.catalog_progress.setVisible(False); layout.addWidget(self.catalog_progress)

        self.search = QLineEdit(); self.search.setPlaceholderText("Search applications…"); self.search.setEnabled(False)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Application", "Version", "Description", "State", "Action"])
        header = self.tree.header()
        # Keep the action/state area stable and let Description absorb the
        # available width.  This avoids the ragged/clipped look when the Changes
        # panel is opened while still allowing the important columns to be resized.
        header.setMinimumSectionSize(80)
        for column in (0, 1, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        self.tree.setColumnWidth(0, 340)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(3, 110)
        self.tree.setColumnWidth(4, 260)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(20)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setAnimated(False)
        self.tree.setIconSize(QSize(26, 26))
        self._app_placeholder_icon = self._load_placeholder_icon()
        layout.addWidget(self.tree, 1)

        self.repo.clicked.connect(self.add_repo); self.url.clicked.connect(self.add_url)
        self.local.clicked.connect(self.add_local); self.git.clicked.connect(self.add_git)
        self.ai.clicked.connect(self.open_ai_requested); self.reload.clicked.connect(self.reload_catalog)
        self.search.textChanged.connect(self._apply_filter)
        self.show_all.toggled.connect(lambda _checked: self._apply_filter(self.search.text()))
        for scenario_id, button in self.scenario_buttons.items():
            button.clicked.connect(lambda _checked=False, sid=scenario_id: self.set_scenario(sid, emit=True))

    def set_settings(self, settings) -> None:
        self.settings = settings

    def set_scenario(self, scenario_id: str, emit: bool = False) -> None:
        if scenario_id not in self.scenario_buttons:
            scenario_id = ""

        # A typed search is intentionally global, but selecting another system-use
        # profile is an explicit navigation action. Clear the previous search so
        # the application list immediately reflects the newly selected profile.
        # This keeps both behaviours intuitive: Search ignores profile boundaries;
        # profile selection exits Search and returns to that profile's normal view.
        scenario_switched = scenario_id != self._scenario_id
        if scenario_switched and self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)

        self._scenario_id = scenario_id
        for sid, button in self.scenario_buttons.items():
            button.blockSignals(True)
            button.setChecked(sid == scenario_id)
            button.blockSignals(False)
        selected = bool(scenario_id)
        self.show_all.setEnabled(selected)
        self.search.setEnabled(selected and bool(self._catalog))
        if selected:
            if emit:
                self.scenario_changed.emit(scenario_id)
            if self._source.get("path") and not self._catalog and self._thread is None:
                self.reload_catalog()
            else:
                self._apply_filter(self.search.text())
            self.catalog_changed.emit(self.catalog_summary())
        elif self._source.get("path"):
            self.catalog_status.setText("Choose the intended system use above to load and prioritise applications.")

    def _cache_file(self) -> Path | None:
        cache_root = str(getattr(self.settings, "cache_dir", "") or "").strip()
        key = str(self._source.get("sha256", "") or "").strip()
        if not cache_root or not key:
            return None
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", key).strip("-") or "unknown"
        return Path(cache_root) / "catalog" / f"{safe}.json"

    def _try_load_windows_cache(self) -> bool:
        """Load the small catalogue JSON directly on Windows.

        This avoids starting WSL at all when the selected ISO has already been
        indexed. The cache contains metadata only and is keyed by the ISO hash.
        """
        cache_file = self._cache_file()
        if cache_file is None or not cache_file.is_file():
            return False
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("schema") != 3:
            return False
        if str(payload.get("source_sha256", "")) != str(self._source.get("sha256", "")):
            return False
        payload["cache_hit"] = True
        payload["read_method"] = "windows-cache"
        self._catalog_ready(payload)
        return True

    def set_source(self, data: dict) -> None:
        self._source = dict(data)
        self._catalog = []
        self._catalog_loaded = False
        self._catalog_read_method = ""
        self.tree.clear()
        self.search.clear(); self.search.setEnabled(False)
        self.reload.setEnabled(bool(data.get("path")))
        if not data.get("path"):
            self.catalog_status.setText("Open or download a Linux image to load its applications.")
            return
        # Reuse the explicit small metadata cache directly from Windows first.
        # A previously indexed ISO should therefore open its Applications view
        # without waiting for WSL to start.
        if self._try_load_windows_cache():
            return
        self.catalog_status.setText("Preparing application list in the background — choose the intended system use above.")
        self.reload_catalog()

    def reload_catalog(self) -> None:
        if self._thread is not None or not self._source.get("path"):
            return
        if not self.settings.workspace_dir.strip():
            self.catalog_status.setText("BLOCKED — choose a Storage location in Settings first.")
            return
        self.catalog_status.setText("Reading user-facing applications from the selected image…")
        self.catalog_progress.setVisible(True); self.catalog_progress.setRange(0, 0)
        self.reload.setEnabled(False)
        self._thread = QThread(self)
        self._worker = CatalogWorker(self.settings, self._source)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._catalog_ready)
        self._worker.failed.connect(self._catalog_failed)
        self._worker.finished.connect(self._thread.quit); self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater); self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._catalog_thread_finished); self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(object)
    def _catalog_ready(self, result) -> None:
        self._catalog = list(result.get("applications") or [])
        self._catalog_loaded = True
        self._catalog_read_method = "cached" if result.get("cache_hit") else str(result.get("read_method", "metadata"))
        self.catalog_progress.setRange(0, 100); self.catalog_progress.setValue(100); self.catalog_progress.setVisible(False)
        cache_note = "cached" if result.get("cache_hit") else str(result.get("read_method", "metadata"))
        if self._scenario_id:
            self.catalog_status.setText(f"READY — {len(self._catalog)} installed applications loaded ({cache_note}).")
            self.search.setEnabled(True)
            self._apply_filter(self.search.text())
        else:
            self.catalog_status.setText(f"READY — {len(self._catalog)} applications loaded ({cache_note}). Choose the intended system use above.")
            self.search.setEnabled(False)
            self.tree.clear()
        self.catalog_changed.emit(self.catalog_summary())

    @Slot(str)
    def _catalog_failed(self, message: str) -> None:
        self.catalog_progress.setVisible(False)
        self.catalog_status.setText("FAILED — application catalogue could not be read.")
        QMessageBox.critical(self, "ChromaPress Applications", message)

    @Slot()
    def _catalog_thread_finished(self) -> None:
        self._thread = None; self._worker = None
        self.reload.setEnabled(bool(self._source.get("path")))

    def _load_placeholder_icon(self) -> QIcon:
        asset = asset_path("chromapress-placeholder.png")
        if not asset.is_file():
            asset = asset_path("chromapress-placeholder.svg")
        icon = QIcon(str(asset)) if asset.is_file() else QIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        return icon

    def _application_icon(self, app: dict) -> QIcon:
        # On Windows the Linux icon theme is normally unavailable. Try the named
        # icon first; otherwise every application gets the ChromaPress placeholder.
        name = str(app.get("icon", "")).strip()
        icon = QIcon.fromTheme(name) if name else QIcon()
        return icon if not icon.isNull() else self._app_placeholder_icon

    @staticmethod
    def _display_description(app: dict) -> str:
        description = str(app.get("description", "")).strip()
        if description:
            return description
        categories = {str(x).casefold() for x in app.get("categories", [])}
        if "webbrowser" in categories:
            return "Browse websites and use web services."
        if "office" in categories:
            return "Create or work with documents and office files."
        if "game" in categories:
            return "Installed game or entertainment application."
        if categories & {"audio", "video", "player"}:
            return "Play or work with audio/video media."
        if "graphics" in categories:
            return "View or work with images and graphics."
        if categories & {"development", "ide"}:
            return "Software development or programming tool."
        if "filemanager" in categories:
            return "Browse and manage files and folders."
        return "Installed application."

    @staticmethod
    def _app_ref(app: dict) -> str:
        package = str(app.get("package", "")).strip()
        if package:
            return f"pkg:{package}"
        desktop = str(app.get("desktop_file", "")).strip()
        if desktop:
            return f"desktop:{desktop}"
        name = str(app.get("application", "")).strip().casefold()
        return f"name:{name}" if name else ""

    @staticmethod
    def _change_target_ref(change: ChangeItem) -> str:
        explicit = str(change.payload.get("target_ref", "")).strip()
        if explicit:
            return explicit
        package = str(change.payload.get("package", "")).strip()
        if package:
            return f"pkg:{package}"
        desktop = str(change.payload.get("desktop_file", "")).strip()
        if desktop:
            return f"desktop:{desktop}"
        name = str(change.payload.get("application", "")).strip().casefold()
        return f"name:{name}" if name else ""

    def set_staged_changes(self, changes: list[ChangeItem]) -> None:
        remove_packages = {
            str(change.payload.get("package", ""))
            for change in changes
            if change.kind == ChangeKind.PACKAGE_REMOVE and change.payload.get("package")
        }
        remove_refs = {
            self._change_target_ref(change)
            for change in changes
            if change.kind == ChangeKind.PACKAGE_REMOVE and self._change_target_ref(change)
        }
        replace_refs = {
            self._change_target_ref(change)
            for change in changes
            if change.kind == ChangeKind.PACKAGE_REPLACE and self._change_target_ref(change)
        }
        add_packages = {
            str(change.payload.get("package", ""))
            for change in changes
            if change.kind == ChangeKind.PACKAGE_REPOSITORY and change.payload.get("package")
        }
        if (
            remove_packages == self._staged_remove_packages
            and remove_refs == self._staged_remove_refs
            and replace_refs == self._staged_replace_refs
            and add_packages == self._staged_add_packages
        ):
            return
        self._staged_remove_packages = remove_packages
        self._staged_remove_refs = remove_refs
        self._staged_replace_refs = replace_refs
        self._staged_add_packages = add_packages
        if self._catalog_loaded and self._scenario_id:
            self._apply_filter(self.search.text())

    def catalog_summary(self) -> dict:
        sections: dict[str, int] = {}
        for app in self._catalog:
            section = application_section(app)
            sections[section] = sections.get(section, 0) + 1
        return {
            "total": len(self._catalog) if self._catalog_loaded else None,
            "read_method": self._catalog_read_method,
            "scenario": self._scenario_id,
            "sections": sections,
        }

    def _leaf_item(self, parent: QTreeWidgetItem, app: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setIcon(0, self._application_icon(app))
        item.setSizeHint(0, QSize(0, 42))
        item.setText(0, str(app.get("application", "")))
        name_font = item.font(0); name_font.setBold(True); item.setFont(0, name_font)
        item.setText(1, str(app.get("version", "")))
        item.setText(2, self._display_description(app))
        item.setText(3, str(app.get("state", "Installed")))
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Alpha 16: every installed launcher gets a real user choice.  Exact
        # package ownership is used when available.  When Quick catalogue
        # ownership is unresolved we still have an exact desktop-file locator,
        # so Remove/Replace can be staged and later resolved fail-closed before
        # the image is modified.  No more passive "Preserved" action rows.
        target_ref = self._app_ref(app)
        action_box = QWidget()
        row = QHBoxLayout(action_box)
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(4)
        action_box.setMinimumHeight(34)
        keep = QPushButton("Keep")
        remove = QPushButton("Remove")
        replace = QPushButton("Replace")
        for button, width in ((keep, 66), (remove, 72), (replace, 78)):
            button.setCheckable(True)
            button.setMinimumWidth(width)
        choice = QButtonGroup(action_box)
        choice.setExclusive(True)
        choice.addButton(keep); choice.addButton(remove); choice.addButton(replace)
        action_box.setStyleSheet(
            "QPushButton:checked { background: #dfe9f5; border: 1px solid #7f9fbe; font-weight: 600; }"
        )

        if target_ref in self._staged_replace_refs:
            replace.setChecked(True)
            item.setText(3, "Replace staged")
            keep.setToolTip("Keep the installed application and undo the staged replacement.")
            remove.setToolTip("Change this staged replacement to a removal.")
            replace.setToolTip("Replacement is currently staged.")
            keep.clicked.connect(lambda _checked=False, ref=target_ref: self.undo_installed_change_requested.emit(ref))
            remove.clicked.connect(lambda _checked=False, data=dict(app): self._switch_to_remove(data))
        elif target_ref in self._staged_remove_refs:
            remove.setChecked(True)
            item.setText(3, "Remove staged")
            keep.setToolTip("Keep the installed application and undo the staged removal.")
            remove.setToolTip("Removal is currently staged.")
            replace.setToolTip("Change this staged removal to a replacement.")
            keep.clicked.connect(lambda _checked=False, ref=target_ref: self.undo_installed_change_requested.emit(ref))
            replace.clicked.connect(lambda _checked=False, data=dict(app): self._switch_to_replace(data))
        else:
            keep.setChecked(True)
            package = str(app.get("package", "")).strip()
            ownership = str(app.get("ownership", "unresolved")).strip()
            if package:
                keep.setToolTip(f"Keep {app.get('application', package)} in the finished ISO.")
                remove.setToolTip(f"Stage removal of package: {package}")
            else:
                keep.setToolTip("Keep this installed application unchanged.")
                remove.setToolTip(
                    "Stage removal using the installed launcher as an exact locator. "
                    "Package ownership will be resolved fail-closed before apply."
                )
            replace.setToolTip("Choose a replacement package/application for this installed application.")
            remove.clicked.connect(lambda _checked=False, data=dict(app): self._stage_remove(data))
            replace.clicked.connect(lambda _checked=False, data=dict(app): self._stage_replace(data))
            if not package and ownership == "unresolved":
                item.setToolTip(3, "Installed launcher detected; package ownership will be resolved before Remove/Replace is applied.")

        row.addWidget(keep)
        row.addWidget(remove)
        row.addWidget(replace)
        self.tree.setItemWidget(item, 4, action_box)
        return item

    def _recommendation_item(
        self, parent: QTreeWidgetItem, recommendation: HomeRecommendation,
        *, context_scenario: str | None = None, label_prefix: str = "Recommended"
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setIcon(0, self._app_placeholder_icon)
        item.setSizeHint(0, QSize(0, 42))
        item.setText(0, f"{label_prefix}: {recommendation.application}")
        name_font = item.font(0); name_font.setBold(True); item.setFont(0, name_font)
        item.setText(1, "")
        item.setText(2, recommendation.description)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        package = recommendation.package

        action_box = QWidget()
        row = QHBoxLayout(action_box)
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(4)
        action_box.setMinimumHeight(34)
        skip = QPushButton("Skip")
        add = QPushButton("Add")
        skip.setCheckable(True)
        add.setCheckable(True)
        skip.setMinimumWidth(72)
        add.setMinimumWidth(72)
        choice = QButtonGroup(action_box)
        choice.setExclusive(True)
        choice.addButton(skip)
        choice.addButton(add)
        action_box.setStyleSheet(
            "QPushButton:checked { background: #dfe9f5; border: 1px solid #7f9fbe; font-weight: 600; }"
        )

        manager = getattr(recommendation, "manager", "apt") or "apt"
        source_label = {"apt": "Repository", "snap": "Snap", "bundled": "Bundled"}.get(manager, manager.title())
        repository_component = str(getattr(recommendation, "repository_component", "") or "").strip()
        if manager == "apt" and repository_component:
            source_label = f"Ubuntu {repository_component.title()}"
        if package in self._staged_add_packages:
            add.setChecked(True)
            item.setText(3, f"Add staged • {source_label}")
            add.setToolTip(f"{source_label} addition is currently staged.")
            skip.setToolTip(f"Skip {recommendation.application} and undo the staged addition.")
            skip.clicked.connect(lambda _checked=False, pkg=package: self.undo_add_requested.emit(pkg))
        else:
            skip.setChecked(True)
            item.setText(3, f"Available • {source_label}")
            skip.setToolTip("Leave the selected image unchanged for this recommendation.")
            if manager == "snap":
                add.setToolTip(f"Stage Snap Store package: {package}")
            elif manager == "bundled":
                add.setToolTip(f"Stage bundled application: {recommendation.application}")
            else:
                add.setToolTip(f"Stage repository package: {package}")
            add.clicked.connect(
                lambda _checked=False, rec=recommendation, sid=context_scenario: self._stage_recommendation(rec, sid)
            )

        # Alpha 14 correction: the buttons were created but never inserted into
        # the row layout, leaving an empty Action cell next to Available.
        row.addWidget(skip)
        row.addWidget(add)
        self.tree.setItemWidget(item, 4, action_box)

        documentation_label = str(getattr(recommendation, "documentation_label", "") or "").strip()
        documentation_relpath = str(getattr(recommendation, "documentation_relpath", "") or "").strip()
        if documentation_label and documentation_relpath:
            documentation = QTreeWidgetItem(item)
            documentation.setIcon(0, item.icon(0))
            documentation.setSizeHint(0, QSize(0, 34))
            documentation.setText(0, documentation_label)
            documentation.setText(2, "School evaluation material supplied with ChromaLearn; not a compliance certificate.")
            documentation.setText(4, "Included automatically")
            documentation.setToolTip(0, documentation_relpath)
            item.setExpanded(True)
        return item

    def _stage_recommendation(self, recommendation: HomeRecommendation, context_scenario: str | None = None) -> None:
        manager = getattr(recommendation, "manager", "apt") or "apt"
        recommendation_scenario = context_scenario or self._scenario_id
        scenario_label = scenario_by_id(recommendation_scenario).label if recommendation_scenario else "Global search"
        payload = {
            "package": recommendation.package,
            "application": recommendation.application,
            "recommendation_role": recommendation.role,
            "recommended": True,
            "manager": manager,
            "scenario": recommendation_scenario,
        }
        repository_component = str(getattr(recommendation, "repository_component", "") or "").strip()
        if repository_component:
            payload["repository_component"] = repository_component
        if manager == "bundled":
            relpath = getattr(recommendation, "bundle_relpath", "")
            root = Path(__file__).resolve().parents[3]
            bundle_path = root / relpath
            payload["path"] = str(bundle_path)
            payload["bundle_relpath"] = relpath
            payload["sha256"] = getattr(recommendation, "bundle_sha256", "")
            documentation_relpath = str(getattr(recommendation, "documentation_relpath", "") or "").strip()
            if documentation_relpath:
                documentation_path = root / documentation_relpath
                payload["documentation_label"] = str(getattr(recommendation, "documentation_label", "") or "")
                payload["documentation_path"] = str(documentation_path)
                payload["documentation_relpath"] = documentation_relpath
                payload["documentation_sha256"] = str(getattr(recommendation, "documentation_sha256", "") or "")
                detail = f"{scenario_label} recommendation • bundled application + evaluation documentation"
            else:
                detail = f"{scenario_label} recommendation • bundled application source"
        elif manager == "snap":
            detail = f"{scenario_label} recommendation • Snap Store package {recommendation.package}"
        else:
            detail = f"{scenario_label} recommendation • repository package {recommendation.package}"
        self.change_requested.emit(ChangeItem(
            f"Add {recommendation.application}", ChangeKind.PACKAGE_REPOSITORY, detail, payload
        ))

    @staticmethod
    def _recommendation_matches_query(recommendation: HomeRecommendation, query: str) -> bool:
        haystack = " ".join((
            recommendation.application, recommendation.package, recommendation.description,
            recommendation.subgroup, " ".join(recommendation.aliases),
        )).casefold()
        return query in haystack

    def _global_search_recommendations(self, query: str) -> list[tuple[str, HomeRecommendation]]:
        """Return matching available/recommended apps independent of active profile.

        The profile buttons only shape the normal Quick view.  Search is global
        across installed applications and every supported recommendation source.
        """
        if not query:
            return []

        candidates: list[tuple[str, HomeRecommendation]] = []
        if home_recommendations_supported(self._source):
            candidates.extend(("personal", rec) for rec in HOME_RECOMMENDATIONS)
        for scenario in SCENARIOS:
            if scenario.id in {"personal", "custom"}:
                continue
            if scenario_recommendations_supported(self._source, scenario.id):
                candidates.extend((scenario.id, rec) for rec in SCENARIO_RECOMMENDATIONS.get(scenario.id, ()))

        # Prefer the currently selected profile when the same package is present
        # in several role presets, then de-duplicate by source manager + package.
        candidates.sort(key=lambda pair: (pair[0] != self._scenario_id, pair[0], pair[1].application.casefold()))
        installed_packages = {
            str(app.get("package", "")).strip()
            for app in self._catalog if str(app.get("package", "")).strip()
        }
        result: list[tuple[str, HomeRecommendation]] = []
        seen: set[tuple[str, str]] = set()
        for scenario_id, recommendation in candidates:
            manager = str(getattr(recommendation, "manager", "apt") or "apt")
            key = (manager, recommendation.package)
            if key in seen:
                continue
            if not self._recommendation_matches_query(recommendation, query):
                continue
            # If the exact package is already installed, the installed row is the
            # authoritative search result.  Avoid presenting a duplicate Add row.
            if recommendation.package in installed_packages and recommendation.package not in self._staged_remove_packages:
                continue
            seen.add(key)
            result.append((scenario_id, recommendation))
        return result

    def _populate_global_search_recommendations(self, query: str) -> None:
        matches = self._global_search_recommendations(query)
        if not matches:
            return
        top = QTreeWidgetItem(self.tree)
        top.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        top.setSizeHint(0, QSize(0, 40))
        top.setText(0, f"Available / recommended matches ({len(matches)})")
        top.setText(2, "Global search results from supported application sources; independent of the selected system-use profile.")
        font = top.font(0); font.setBold(True); top.setFont(0, font)
        for scenario_id, recommendation in matches:
            item = self._recommendation_item(
                top, recommendation, context_scenario=scenario_id, label_prefix="Available"
            )
            scenario_label = scenario_by_id(scenario_id).label
            item.setToolTip(0, f"Available recommendation from {scenario_label}.")

    def _add_suite_or_leafs(self, parent: QTreeWidgetItem, apps: list[dict]) -> None:
        suites: dict[str, list[dict]] = {}
        standalone: list[dict] = []
        for app in apps:
            suite = suite_group(app)
            if suite:
                suites.setdefault(suite, []).append(app)
            else:
                standalone.append(app)

        for suite_name, suite_apps in sorted(suites.items()):
            suite_item = QTreeWidgetItem(parent)
            suite_item.setIcon(0, self._app_placeholder_icon)
            suite_item.setSizeHint(0, QSize(0, 40))
            suite_item.setText(0, f"{suite_name} ({len(suite_apps)})")
            suite_font = suite_item.font(0); suite_font.setBold(True); suite_item.setFont(0, suite_font)
            if suite_name == "LibreOffice":
                suite_item.setText(2, "Office suite — writing, spreadsheets, presentations, drawing and formulas. Expand to choose individual components.")
            else:
                suite_item.setText(2, "Application suite — expand to view components.")
            suite_item.setText(3, "Installed")
            for app in sorted(suite_apps, key=lambda a: str(a.get("application", "")).casefold()):
                self._leaf_item(suite_item, app)

        for app in sorted(standalone, key=lambda a: str(a.get("application", "")).casefold()):
            self._leaf_item(parent, app)

    def _populate_personal(self, apps: list[dict]) -> None:
        grouped: dict[str, dict[str, list[dict]]] = {}
        for app in apps:
            top, subgroup = personal_home_group(app)
            if not top:
                continue
            grouped.setdefault(top, {}).setdefault(subgroup, []).append(app)

        recommendations_by_subgroup: dict[str, list[HomeRecommendation]] = {}
        if self._catalog_loaded:
            for recommendation in missing_home_recommendations(
                self._catalog, self._source, self._staged_remove_packages
            ):
                recommendations_by_subgroup.setdefault(recommendation.subgroup, []).append(recommendation)

        top_order = ("Everyday essentials", "Specialised / Advanced")
        subgroup_orders = {
            "Everyday essentials": HOME_EVERYDAY_SUBGROUPS,
            "Specialised / Advanced": HOME_SPECIALIST_SUBGROUPS,
        }
        for top in top_order:
            subgroups = grouped.get(top, {})
            subgroup_order = subgroup_orders[top]
            recommendation_count = (
                sum(len(recommendations_by_subgroup.get(name, [])) for name in subgroup_order)
                if top == "Everyday essentials" else 0
            )
            if not subgroups and not recommendation_count:
                continue
            total = sum(len(v) for v in subgroups.values())
            top_item = QTreeWidgetItem(self.tree)
            top_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            top_item.setSizeHint(0, QSize(0, 40))
            if recommendation_count:
                top_item.setText(0, f"{top} ({total} installed, {recommendation_count} recommended)")
            else:
                top_item.setText(0, f"{top} ({total})")
            top_item.setText(2, HOME_GROUP_DESCRIPTIONS.get(top, ""))
            top_font = top_item.font(0); top_font.setBold(True); top_item.setFont(0, top_font)

            for subgroup in subgroup_order:
                subgroup_apps = subgroups.get(subgroup, [])
                subgroup_recommendations = (
                    recommendations_by_subgroup.get(subgroup, []) if top == "Everyday essentials" else []
                )
                # Everyday categories stay visible if a recommended replacement
                # exists; specialised groups are shown only when they really contain
                # installed software.  This prevents duplicate empty specialist rows
                # appearing under Everyday essentials.
                if not subgroup_apps and not subgroup_recommendations:
                    continue
                subgroup_item = QTreeWidgetItem(top_item)
                subgroup_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
                subgroup_item.setSizeHint(0, QSize(0, 38))
                if subgroup_recommendations:
                    subgroup_item.setText(
                        0, f"{subgroup} ({len(subgroup_apps)} installed, {len(subgroup_recommendations)} recommended)"
                    )
                else:
                    subgroup_item.setText(0, f"{subgroup} ({len(subgroup_apps)})")
                subgroup_item.setText(2, HOME_GROUP_DESCRIPTIONS.get(subgroup, "Expand to view applications."))
                subgroup_font = subgroup_item.font(0); subgroup_font.setBold(True); subgroup_item.setFont(0, subgroup_font)
                for recommendation in subgroup_recommendations:
                    self._recommendation_item(subgroup_item, recommendation)
                self._add_suite_or_leafs(subgroup_item, subgroup_apps)

    def _populate_scenario_recommendations(self) -> None:
        if (
            not self._catalog_loaded
            or self._scenario_id in {"", "personal", "custom"}
            or self.show_all.isChecked()
            or self.search.text().strip()
        ):
            return
        recommendations = missing_scenario_recommendations(
            self._catalog, self._source, self._scenario_id, self._staged_remove_packages
        )
        if not recommendations:
            return

        scenario = scenario_by_id(self._scenario_id)
        top = QTreeWidgetItem(self.tree)
        top.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        top.setSizeHint(0, QSize(0, 40))
        top.setText(0, f"Recommended for {scenario.label} ({len(recommendations)})")
        top.setText(2, SCENARIO_RECOMMENDATION_DESCRIPTIONS.get(self._scenario_id, scenario.ai_context))
        font = top.font(0); font.setBold(True); top.setFont(0, font)
        # Recommendations are guidance for the selected system role, so they
        # should be visible immediately when the profile is selected instead
        # of requiring the user to discover and expand a collapsed folder.
        top.setExpanded(True)

        groups: dict[str, list[HomeRecommendation]] = {}
        for recommendation in recommendations:
            groups.setdefault(recommendation.subgroup, []).append(recommendation)
        for subgroup, items in groups.items():
            subgroup_item = QTreeWidgetItem(top)
            subgroup_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
            subgroup_item.setSizeHint(0, QSize(0, 38))
            subgroup_item.setText(0, f"{subgroup} ({len(items)} recommended)")
            subgroup_item.setText(2, "Recommended tools for this system role. Nothing is installed until Add is staged.")
            subgroup_font = subgroup_item.font(0); subgroup_font.setBold(True); subgroup_item.setFont(0, subgroup_font)
            subgroup_item.setExpanded(True)
            for recommendation in items:
                self._recommendation_item(subgroup_item, recommendation)

    @staticmethod
    def _tree_label_key(text: str) -> str:
        # Counts and staged states may change after a click; strip the trailing
        # count summary so the same logical group can be reopened afterwards.
        return re.sub(r"\s+\([^()]*\)$", "", str(text)).strip()

    def _expanded_tree_paths(self) -> set[tuple[str, ...]]:
        paths: set[tuple[str, ...]] = set()

        def walk(item: QTreeWidgetItem, prefix: tuple[str, ...]) -> None:
            path = prefix + (self._tree_label_key(item.text(0)),)
            if item.isExpanded():
                paths.add(path)
            for i in range(item.childCount()):
                walk(item.child(i), path)

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i), ())
        return paths

    def _restore_expanded_tree_paths(self, paths: set[tuple[str, ...]]) -> None:
        if not paths:
            return

        def walk(item: QTreeWidgetItem, prefix: tuple[str, ...]) -> None:
            path = prefix + (self._tree_label_key(item.text(0)),)
            if path in paths:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i), path)

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i), ())

    def _populate(self, apps: list[dict]) -> None:
        expanded_paths = self._expanded_tree_paths()
        self.tree.clear()

        if self._scenario_id == "personal" and not self.show_all.isChecked() and not self.search.text().strip():
            self._populate_personal(apps)
            self._restore_expanded_tree_paths(expanded_paths)
            return

        query = self.search.text().strip().casefold()
        if query:
            self._populate_global_search_recommendations(query)
        else:
            self._populate_scenario_recommendations()
        if not apps:
            self._restore_expanded_tree_paths(expanded_paths)
            if query:
                self.tree.expandAll()
            return

        grouped: dict[str, list[dict]] = {}
        for app in apps:
            grouped.setdefault(application_section(app), []).append(app)

        order = section_order_for_scenario(self._scenario_id)
        order_index = {name: i for i, name in enumerate(order)}
        sections = sorted(grouped, key=lambda name: (order_index.get(name, 999), name.casefold()))

        for section in sections:
            section_apps = sorted(grouped[section], key=lambda a: str(a.get("application", "")).casefold())
            section_item = QTreeWidgetItem(self.tree)
            section_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            section_item.setSizeHint(0, QSize(0, 38))
            section_item.setText(0, f"{section} ({len(section_apps)})")
            section_descriptions = {
                "Internet & Communication": "Browsers, communication and internet applications.",
                "Office & Documents": "Writing, documents, spreadsheets, presentations and readers.",
                "Games": "Games and entertainment applications.",
                "Media & Graphics": "Photos, graphics, audio, video and media applications.",
                "Development": "Programming, editors and software-development tools.",
                "System & Utilities": "System, file, settings and utility applications.",
                "Other": "Other installed user-facing applications.",
            }
            section_item.setText(2, section_descriptions.get(section, "Expand to view applications."))
            font = section_item.font(0); font.setBold(True); section_item.setFont(0, font)
            section_item.setFirstColumnSpanned(False)

            self._add_suite_or_leafs(section_item, section_apps)

        # Categories remain collapsed for instant visual overview. Search expands
        # only the matching groups, while ordinary staged changes preserve the
        # user's current expansion state instead of collapsing the tree.
        if self.search.text().strip():
            self.tree.expandAll()
        else:
            self._restore_expanded_tree_paths(expanded_paths)

    def _apply_filter(self, text: str) -> None:
        if not self._scenario_id:
            self.tree.clear()
            return
        query = text.strip().casefold()
        ranked = []
        for app in self._catalog:
            if query and not (
                query in str(app.get("application", "")).casefold()
                or query in str(app.get("description", "")).casefold()
                or query in str(app.get("package", "")).casefold()
            ):
                continue

            # Search is intentionally global: typing a name must find it even when
            # the current quick scenario would normally hide specialist software.
            if query:
                ranked.append((100, app))
                continue

            if self._scenario_id == "personal" and not self.show_all.isChecked():
                top, _sub = personal_home_group(app)
                if top:
                    ranked.append((10 if top == "Everyday essentials" else 5, app))
                continue

            score = relevance_score(app, self._scenario_id)
            if self.show_all.isChecked() or score > 0:
                ranked.append((score, app))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("application", "")).casefold()))
        self._populate([app for _score, app in ranked])

    @Slot(QTreeWidgetItem, int)
    def _tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 4:
            return
        app = item.data(4, 0x0100)
        if isinstance(app, dict):
            self._stage_remove(app)

    def _installed_payload(self, app: dict) -> dict:
        package = str(app.get("package", "")).strip()
        name = str(app.get("application", package or "Installed application")).strip()
        desktop_file = str(app.get("desktop_file", "")).strip()
        return {
            "package": package,
            "application": name,
            "desktop_file": desktop_file,
            "ownership": str(app.get("ownership", "unresolved")),
            "target_ref": self._app_ref(app),
        }

    def _stage_remove(self, app: dict) -> None:
        payload = self._installed_payload(app)
        target_ref = str(payload.get("target_ref", ""))
        if not target_ref:
            return
        name = str(payload.get("application", "Installed application"))
        package = str(payload.get("package", ""))
        detail = (
            f"Installed application • package {package}"
            if package else
            f"Installed application • resolve owner of {payload.get('desktop_file') or name} before apply"
        )
        self.change_requested.emit(ChangeItem(
            f"Remove {name}", ChangeKind.PACKAGE_REMOVE, detail, payload
        ))

    def _stage_replace(self, app: dict, undo_existing: bool = False) -> None:
        payload = self._installed_payload(app)
        target_ref = str(payload.get("target_ref", ""))
        if not target_ref:
            return
        name = str(payload.get("application", "Installed application"))
        dialog = TextEntryDialog(
            f"Replace {name}",
            "Replacement application/package:",
            "Enter the repository package that should replace this installed application. "
            "ChromaPress stages one atomic replacement plan: the current application is resolved and removed only if the replacement can be resolved safely.",
            "Example: abiword",
            self,
        )
        if not dialog.exec() or not dialog.text():
            # Restore the current visual choice if the user cancels the dialog.
            self._apply_filter(self.search.text())
            return
        replacement = dialog.text()
        if undo_existing:
            self.undo_installed_change_requested.emit(target_ref)
        payload["replacement_package"] = replacement
        payload["manager"] = "apt"
        self.change_requested.emit(ChangeItem(
            f"Replace {name} with {replacement}",
            ChangeKind.PACKAGE_REPLACE,
            f"Installed application → repository package {replacement}",
            payload,
        ))

    def _switch_to_remove(self, app: dict) -> None:
        target_ref = self._app_ref(app)
        if target_ref:
            self.undo_installed_change_requested.emit(target_ref)
        self._stage_remove(app)

    def _switch_to_replace(self, app: dict) -> None:
        # Keep the existing staged removal if the replacement dialog is cancelled.
        self._stage_replace(app, undo_existing=True)

    def add_repo(self):
        dialog = TextEntryDialog("Add from repository", "Application/package:", "Search for an application or package in the repositories belonging to the selected Linux image.", "Example: vlc", self)
        if dialog.exec() and dialog.text():
            package = dialog.text()
            self.change_requested.emit(ChangeItem(f"Add {package}", ChangeKind.PACKAGE_REPOSITORY, "Resolve from selected image repositories", {"package": package}))

    def add_url(self):
        dialog = TextEntryDialog("Install from direct link", "Download URL:", "Paste a direct HTTPS/HTTP link to a Linux package or application file. ChromaPress will inspect it before installation is allowed.", "https://example.org/application.deb", self)
        if dialog.exec() and dialog.text():
            url = dialog.text(); self.change_requested.emit(ChangeItem("Install from direct link", ChangeKind.DIRECT_URL, url, {"url": url}))

    def add_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Linux package or application", "", "Linux packages/applications (*.deb *.rpm *.AppImage *.flatpak *.snap *.tar *.gz *.xz *.zst *.zip);;All files (*)")
        if path:
            name = Path(path).name; self.change_requested.emit(ChangeItem(f"Add {name}", ChangeKind.LOCAL_PACKAGE, path, {"path": path}))

    def add_git(self):
        dialog = GitEntryDialog(self)
        if dialog.exec() and dialog.url.text().strip():
            url = dialog.url.text().strip(); ref = dialog.ref.text().strip(); detail = url if not ref else f"{url} @ {ref}"
            self.change_requested.emit(ChangeItem("Build application from Git", ChangeKind.GIT, detail, {"url": url, "ref": ref}))
