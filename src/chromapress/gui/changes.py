from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QMessageBox

from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.preflight import test_change


class ChangesPanel(QWidget):
    changed = Signal()
    review_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        title = QLabel("Changes")
        title.setObjectName("panelTitle")
        self.summary = QLabel("No changes staged")
        self.list = QListWidget()
        buttons = QHBoxLayout()
        self.test_btn = QPushButton("Test")
        self.undo_btn = QPushButton("Undo")
        self.review_btn = QPushButton("Full overview")
        buttons.addWidget(self.test_btn)
        buttons.addWidget(self.undo_btn)
        buttons.addWidget(self.review_btn)
        layout.addWidget(title)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.test_btn.clicked.connect(self._test_selected)
        self.undo_btn.clicked.connect(self._undo_selected)
        self.review_btn.clicked.connect(lambda _checked=False: self.review_requested.emit())
        self.list.currentItemChanged.connect(lambda _current, _previous: self._update_button_state())
        self._changes: list[ChangeItem] = []
        self._update_button_state()

    @property
    def changes(self) -> list[ChangeItem]:
        return self._changes

    def set_changes(self, changes: list[ChangeItem]) -> None:
        current_id = self._current_id()
        self._changes = changes
        self.refresh(preferred_id=current_id, select_fallback=True)

    def add_change(self, change: ChangeItem) -> None:
        # Identical staged actions are one plan item, not repeated clicks.
        for existing in self._changes:
            if existing.kind == change.kind and existing.payload == change.payload:
                self.refresh(preferred_id=existing.id, select_fallback=True)
                return
        self._changes.append(change)
        self.refresh(preferred_id=change.id, select_fallback=True)
        self.changed.emit()

    @staticmethod
    def _target_ref(change: ChangeItem) -> str:
        explicit = str(change.payload.get("target_ref", "")).strip()
        if explicit:
            return explicit
        package = str(change.payload.get("package", "")).strip()
        if package:
            return f"pkg:{package}"
        desktop = str(change.payload.get("desktop_file", "")).strip()
        if desktop:
            return f"desktop:{desktop}"
        application = str(change.payload.get("application", "")).strip()
        return f"name:{application.casefold()}" if application else ""

    def undo_installed_change(self, target_ref: str) -> None:
        """Undo a staged Remove or Replace for one installed application.

        Alpha 16 intentionally keys this by a stable application locator rather
        than package name only.  That lets unresolved desktop launchers have real
        Keep/Remove/Replace choices while package ownership is resolved fail-closed
        later during apply.
        """
        target_ref = str(target_ref).strip()
        before = len(self._changes)
        self._changes[:] = [
            c for c in self._changes
            if not (
                c.kind in {ChangeKind.PACKAGE_REMOVE, ChangeKind.PACKAGE_REPLACE}
                and self._target_ref(c) == target_ref
            )
        ]
        if len(self._changes) != before:
            self.refresh(select_fallback=True)
            self.changed.emit()

    # Compatibility path used by older Alpha 14/15 row signals.
    def undo_package_remove(self, package: str) -> None:
        package = str(package).strip()
        if package:
            self.undo_installed_change(f"pkg:{package}")

    def undo_package_add(self, package: str) -> None:
        before = len(self._changes)
        self._changes[:] = [
            c for c in self._changes
            if not (c.kind == ChangeKind.PACKAGE_REPOSITORY and str(c.payload.get("package", "")) == package)
        ]
        if len(self._changes) != before:
            self.refresh(select_fallback=True)
            self.changed.emit()

    def _current_id(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def refresh(self, preferred_id: str = "", select_fallback: bool = False) -> None:
        if not preferred_id:
            preferred_id = self._current_id()
        self.list.clear()
        preferred_row = -1
        for row, change in enumerate(self._changes):
            item = QListWidgetItem(f"{change.status.value}  {change.title}\n{change.detail}")
            item.setData(Qt.ItemDataRole.UserRole, change.id)
            self.list.addItem(item)
            if change.id == preferred_id:
                preferred_row = row
        n = len(self._changes)
        self.summary.setText("No changes staged" if n == 0 else f"{n} change{'s' if n != 1 else ''} staged")
        if preferred_row >= 0:
            self.list.setCurrentRow(preferred_row)
        elif select_fallback and n:
            self.list.setCurrentRow(n - 1)
        self._update_button_state()

    def _update_button_state(self) -> None:
        has_selection = self.list.currentItem() is not None
        self.test_btn.setEnabled(has_selection)
        self.undo_btn.setEnabled(has_selection)

    def _selected(self) -> ChangeItem | None:
        item = self.list.currentItem()
        if not item:
            return None
        cid = item.data(Qt.ItemDataRole.UserRole)
        return next((c for c in self._changes if c.id == cid), None)

    def _test_selected(self) -> None:
        change = self._selected()
        if not change:
            return
        status, message = test_change(change)
        change.status = status
        self.refresh(preferred_id=change.id, select_fallback=True)
        QMessageBox.information(self, f"{status.value}: {change.title}", message)
        self.changed.emit()

    def _undo_selected(self) -> None:
        change = self._selected()
        if not change:
            return
        row = self.list.currentRow()
        self._changes[:] = [c for c in self._changes if c.id != change.id]
        self.refresh(select_fallback=False)
        if self._changes:
            self.list.setCurrentRow(min(row, len(self._changes) - 1))
        self._update_button_state()
        self.changed.emit()
