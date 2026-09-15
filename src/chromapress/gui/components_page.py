from __future__ import annotations
from chromapress.i18n import tr
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QHeaderView, QPushButton, QStyle
from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.paths import asset_path

class ComponentsPage(QWidget):
    """Installed target-image component browser.

    The page consumes only component evidence created from the selected image's
    package manifests. It never substitutes the Windows/WSL host inventory.
    """
    change_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source: dict = {}
        self._inventory: list[dict] = []
        self._staged_remove: set[str] = set()
        layout = QVBoxLayout(self)
        title = QLabel(tr('Components'))
        title.setObjectName('pageTitle')
        subtitle = QLabel(tr('Browse libraries, runtimes, kernel packages, drivers, language packs and other technical components detected in the selected Linux image. The inventory shown here comes from target-image package manifests, never from Windows or the WSL host.'))
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search installed components…'))
        self.search.setEnabled(False)
        self.category = QComboBox()
        self.category.addItem(tr('Useful components'), 'useful')
        self.category.addItem(tr('All installed components'), 'all')
        self.category.setEnabled(False)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.category)
        layout.addLayout(controls)
        self.status = QLabel(tr('Select and analyze a source ISO to view installed components.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels([tr('Component'), tr('Version'), tr('Category'), tr('State'), tr('Protection'), tr('Action')])
        header = self.tree.header()
        header.setMinimumSectionSize(80)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(1, 105)
        self.tree.setColumnWidth(2, 135)
        self.tree.setColumnWidth(3, 115)
        self.tree.setColumnWidth(4, 165)
        self.tree.setColumnWidth(5, 140)
        self.tree.setAlternatingRowColors(False)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet("QTreeWidget::item { padding-top: 12px; padding-bottom: 12px; border-bottom: 1px solid #d8dde3; }")
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setEnabled(False)
        layout.addWidget(self.tree, 1)
        asset = asset_path('chromapress-placeholder.png')
        if not asset.is_file():
            asset = asset_path('chromapress-placeholder.svg')
        self._component_icon = QIcon(str(asset)) if asset.is_file() else QIcon()
        if self._component_icon.isNull():
            self._component_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self.search.textChanged.connect(self._refresh)
        self.category.currentIndexChanged.connect(self._refresh)

    def set_analysis(self, data: dict) -> None:
        self._source = dict(data or {})
        self._inventory = list(self._source.get('component_inventory') or [])
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        ready = bool(self._source.get('path'))
        self.search.setEnabled(ready and bool(self._inventory))
        self.category.setEnabled(ready and bool(self._inventory))
        self.tree.setEnabled(ready and bool(self._inventory))
        if not ready:
            self.status.setText(tr('Select and analyze a source ISO to view installed components.'))
            self.tree.clear()
            return
        if not self._inventory:
            self.status.setText(tr('INSTALLED_INVENTORY=UNKNOWN — no authoritative package manifest inventory was available from this image. ChromaPress will not substitute host package data.'))
            self.tree.clear()
            return
        self.status.setText(tr(f'INSTALLED_INVENTORY=READY — {len(self._inventory)} target-image packages detected. Available repository metadata is not inferred by this view.'))
        self._refresh()

    def set_staged_changes(self, changes: list[ChangeItem]) -> None:
        staged = {str(change.payload.get('package') or '') for change in changes if change.kind == ChangeKind.PACKAGE_REMOVE and change.payload.get('package')}
        if staged == self._staged_remove:
            return
        self._staged_remove = staged
        if self._inventory:
            self._refresh()

    def _visible_inventory(self) -> list[dict]:
        query = self.search.text().strip().casefold()
        mode = str(self.category.currentData() or 'useful')
        result: list[dict] = []
        for item in self._inventory:
            category = str(item.get('category') or 'System component')
            if mode == 'useful' and category in {'Library', 'Dependency'}:
                continue
            haystack = ' '.join((str(item.get('display_name') or ''), str(item.get('package') or ''), str(item.get('version') or ''), category)).casefold()
            if query and query not in haystack:
                continue
            result.append(item)
        return result

    def _refresh(self, *_args) -> None:
        self.tree.clear()
        if not self._inventory:
            return
        grouped: dict[str, list[dict]] = {}
        for item in self._visible_inventory():
            grouped.setdefault(str(item.get('category') or 'System component'), []).append(item)
        order = ['Kernel', 'Driver / firmware', 'Runtime', 'Language / locale', 'Service', 'Desktop component', 'System component', 'Utility', 'Dependency', 'Library']
        for category in sorted(grouped, key=lambda value: (order.index(value) if value in order else 999, value.casefold())):
            rows = grouped[category]
            group = QTreeWidgetItem(self.tree)
            group.setText(0, tr(f'{category} ({len(rows)})'))
            group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            for data in sorted(rows, key=lambda x: str(x.get('package') or '').casefold()):
                self._add_component(group, data)
            group.setExpanded(True)
        if not grouped:
            self.status.setText(tr(f'INSTALLED_INVENTORY=READY — {len(self._inventory)} packages detected; no components match the current filter.'))
        else:
            self.status.setText(tr(f'INSTALLED_INVENTORY=READY — showing {sum((len(v) for v in grouped.values()))} of {len(self._inventory)} target-image packages. Available repository metadata is not inferred.'))

    def _add_component(self, parent: QTreeWidgetItem, data: dict) -> None:
        package = str(data.get('package') or '')
        protected = bool(data.get('protected'))
        reason = str(data.get('protection_reason') or '')
        item = QTreeWidgetItem(parent)
        item.setIcon(0, self._component_icon)
        item.setText(0, str(data.get('display_name') or package))
        item.setToolTip(0, tr(f'Technical package: {package}') if package else tr('Target-image component'))
        item.setText(1, str(data.get('version') or tr('')))
        item.setText(2, str(data.get('category') or tr('System component')))
        item.setText(3, tr('Remove staged') if package in self._staged_remove else tr('Installed'))
        item.setText(4, tr('Protected') if protected else tr('Review required'))
        item.setToolTip(4, reason or tr('Removal requires normal ChromaPress dependency/preflight review.'))
        button = QPushButton(tr('Remove staged') if package in self._staged_remove else tr('Stage remove'))
        button.setMinimumHeight(36)
        button.setStyleSheet(
            "QPushButton { "
            "background: transparent; "
            "color: #20242a; "
            "border: 0; "
            "border-radius: 0; "
            "padding: 0px 10px 7px 10px; "
            "}"
            "QPushButton:hover { "
            "background: rgba(220, 226, 232, 90); "
            "}"
            "QPushButton:disabled { "
            "background: transparent; "
            "color: #20242a; "
            "}"
        )
        if protected or not package or package in self._staged_remove:
            button.setEnabled(False)
        if protected:
            button.setToolTip(reason or tr('Protected target-image component'))
        elif package in self._staged_remove:
            button.setToolTip(tr('Removal is already staged in Changes.'))
        else:
            button.setToolTip(tr('Stage removal; ChromaPress will validate dependencies before apply.'))
            button.clicked.connect(lambda _checked=False, d=dict(data): self._stage_remove(d))
        action_cell = QWidget()
        action_cell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        action_cell.setStyleSheet("background: transparent; border: 0;")
        action_layout = QVBoxLayout(action_cell)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(0)
        action_layout.addStretch(1)
        action_layout.addWidget(button)
        action_layout.addStretch(1)
        self.tree.setItemWidget(item, 5, action_cell)

    def _stage_remove(self, data: dict) -> None:
        package = str(data.get('package') or '').strip()
        if not package or bool(data.get('protected')):
            return
        self.change_requested.emit(ChangeItem(f'Remove component {package}', ChangeKind.PACKAGE_REMOVE, f"Target-image component • {data.get('category', 'System component')} • dependency review required", {'package': package, 'target_ref': f'pkg:{package}', 'component': True, 'source_sha256': str(self._source.get('sha256') or '')}))
