from __future__ import annotations

from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QPushButton, QStyle,
)

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
        title = QLabel("Components")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Browse libraries, runtimes, kernel packages, drivers, language packs and other "
            "technical components detected in the selected Linux image. The inventory shown "
            "here comes from target-image package manifests, never from Windows or the WSL host."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search installed components…")
        self.search.setEnabled(False)
        self.category = QComboBox()
        self.category.addItem("Useful components", "useful")
        self.category.addItem("All installed components", "all")
        self.category.setEnabled(False)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.category)
        layout.addLayout(controls)

        self.status = QLabel("Select and analyze a source ISO to view installed components.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Component", "Version", "Category", "State", "Protection", "Action"])
        header = self.tree.header()
        header.setMinimumSectionSize(80)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 170)
        self.tree.setColumnWidth(3, 110)
        self.tree.setColumnWidth(4, 240)
        self.tree.setColumnWidth(5, 120)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setEnabled(False)
        layout.addWidget(self.tree, 1)

        asset = asset_path("chromapress-placeholder.png")
        if not asset.is_file():
            asset = asset_path("chromapress-placeholder.svg")
        self._component_icon = QIcon(str(asset)) if asset.is_file() else QIcon()
        if self._component_icon.isNull():
            self._component_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        self.search.textChanged.connect(self._refresh)
        self.category.currentIndexChanged.connect(self._refresh)

    def set_analysis(self, data: dict) -> None:
        self._source = dict(data or {})
        self._inventory = list(self._source.get("component_inventory") or [])
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        ready = bool(self._source.get("path"))
        self.search.setEnabled(ready and bool(self._inventory))
        self.category.setEnabled(ready and bool(self._inventory))
        self.tree.setEnabled(ready and bool(self._inventory))

        if not ready:
            self.status.setText("Select and analyze a source ISO to view installed components.")
            self.tree.clear()
            return
        if not self._inventory:
            self.status.setText(
                "INSTALLED_INVENTORY=UNKNOWN — no authoritative package manifest inventory was "
                "available from this image. ChromaPress will not substitute host package data."
            )
            self.tree.clear()
            return
        self.status.setText(
            f"INSTALLED_INVENTORY=READY — {len(self._inventory)} target-image packages detected. "
            "Available repository metadata is not inferred by this view."
        )
        self._refresh()

    def set_staged_changes(self, changes: list[ChangeItem]) -> None:
        staged = {
            str(change.payload.get("package") or "")
            for change in changes
            if change.kind == ChangeKind.PACKAGE_REMOVE and change.payload.get("package")
        }
        if staged == self._staged_remove:
            return
        self._staged_remove = staged
        if self._inventory:
            self._refresh()

    def _visible_inventory(self) -> list[dict]:
        query = self.search.text().strip().casefold()
        mode = str(self.category.currentData() or "useful")
        result: list[dict] = []
        for item in self._inventory:
            category = str(item.get("category") or "System component")
            if mode == "useful" and category in {"Library", "Dependency"}:
                continue
            haystack = " ".join((
                str(item.get("display_name") or ""),
                str(item.get("package") or ""),
                str(item.get("version") or ""),
                category,
            )).casefold()
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
            grouped.setdefault(str(item.get("category") or "System component"), []).append(item)

        order = [
            "Kernel", "Driver / firmware", "Runtime", "Language / locale", "Service",
            "Desktop component", "System component", "Utility", "Dependency", "Library",
        ]
        for category in sorted(grouped, key=lambda value: (order.index(value) if value in order else 999, value.casefold())):
            rows = grouped[category]
            group = QTreeWidgetItem(self.tree)
            group.setText(0, f"{category} ({len(rows)})")
            group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            for data in sorted(rows, key=lambda x: str(x.get("package") or "").casefold()):
                self._add_component(group, data)
            group.setExpanded(True)

        if not grouped:
            self.status.setText(
                f"INSTALLED_INVENTORY=READY — {len(self._inventory)} packages detected; "
                "no components match the current filter."
            )
        else:
            self.status.setText(
                f"INSTALLED_INVENTORY=READY — showing {sum(len(v) for v in grouped.values())} of "
                f"{len(self._inventory)} target-image packages. Available repository metadata is not inferred."
            )

    def _add_component(self, parent: QTreeWidgetItem, data: dict) -> None:
        package = str(data.get("package") or "")
        protected = bool(data.get("protected"))
        reason = str(data.get("protection_reason") or "")
        item = QTreeWidgetItem(parent)
        item.setIcon(0, self._component_icon)
        item.setText(0, str(data.get("display_name") or package))
        item.setToolTip(0, f"Technical package: {package}" if package else "Target-image component")
        item.setText(1, str(data.get("version") or ""))
        item.setText(2, str(data.get("category") or "System component"))
        item.setText(3, "Remove staged" if package in self._staged_remove else "Installed")
        item.setText(4, "Protected" if protected else "Review required")
        item.setToolTip(4, reason or "Removal requires normal ChromaPress dependency/preflight review.")

        button = QPushButton("Remove staged" if package in self._staged_remove else "Stage remove")
        if protected or not package or package in self._staged_remove:
            button.setEnabled(False)
        if protected:
            button.setToolTip(reason or "Protected target-image component")
        elif package in self._staged_remove:
            button.setToolTip("Removal is already staged in Changes.")
        else:
            button.setToolTip("Stage removal; ChromaPress will validate dependencies before apply.")
            button.clicked.connect(lambda _checked=False, d=dict(data): self._stage_remove(d))
        self.tree.setItemWidget(item, 5, button)

    def _stage_remove(self, data: dict) -> None:
        package = str(data.get("package") or "").strip()
        if not package or bool(data.get("protected")):
            return
        self.change_requested.emit(ChangeItem(
            f"Remove component {package}",
            ChangeKind.PACKAGE_REMOVE,
            f"Target-image component • {data.get('category', 'System component')} • dependency review required",
            {
                "package": package,
                "target_ref": f"pkg:{package}",
                "component": True,
                "source_sha256": str(self._source.get("sha256") or ""),
            },
        ))
