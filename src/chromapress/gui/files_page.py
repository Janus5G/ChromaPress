from __future__ import annotations

from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QComboBox, QLineEdit,
    QPushButton, QListWidget, QFileDialog, QHBoxLayout, QMessageBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
)

from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.part5 import inspect_custom_content, validate_custom_content_payload


class FilesPage(QWidget):
    """Part 5 safe custom-content staging page."""

    stage_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.analysis: dict = {}
        self.capability: dict = {}
        self.sources: list[str] = []
        layout = QVBoxLayout(self)
        title = QLabel("Files / Custom Content"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Stage user-provided files, folders or .tar.gz archives for /etc/skel/ or a controlled system overlay. "
            "Archives are inspected before staging; traversal, unsafe absolute paths, special nodes and escaping symlinks are rejected."
        ); intro.setWordWrap(True); layout.addWidget(intro)

        capbox = QGroupBox("Target capability")
        cf = QFormLayout(capbox)
        self.cap_value = QLabel("UNKNOWN"); self.cap_value.setWordWrap(True)
        self.target_value = QLabel("/etc/skel/ + controlled system overlay")
        cf.addRow("Capability:", self.cap_value); cf.addRow("Supported targets:", self.target_value)
        layout.addWidget(capbox)

        select = QGroupBox("Sources")
        sv = QVBoxLayout(select)
        self.source_list = QListWidget(); sv.addWidget(self.source_list)
        btnrow = QHBoxLayout()
        self.add_files_btn = QPushButton("Add files")
        self.add_folder_btn = QPushButton("Add folder")
        self.add_archive_btn = QPushButton("Add .tar.gz")
        self.clear_btn = QPushButton("Clear")
        for b in (self.add_files_btn, self.add_folder_btn, self.add_archive_btn, self.clear_btn): btnrow.addWidget(b)
        btnrow.addStretch(1); sv.addLayout(btnrow); layout.addWidget(select)

        options = QGroupBox("Placement and conflict policy")
        of = QFormLayout(options)
        self.target_kind = QComboBox(); self.target_kind.addItem("Default user content (/etc/skel/)", "default_user_content"); self.target_kind.addItem("System file / overlay", "system_overlay")
        self.target_subpath = QLineEdit(); self.target_subpath.setPlaceholderText("Desktop or /opt/myapp")
        self.conflict = QComboBox(); self.conflict.addItems(["PRESERVE", "SKIP", "REPLACE"])
        self.replace_confirm = QCheckBox("I reviewed the target and explicitly allow REPLACE where a conflict is verified")
        of.addRow("Target type:", self.target_kind); of.addRow("Target subpath:", self.target_subpath); of.addRow("Conflict policy:", self.conflict); of.addRow("Replace confirmation:", self.replace_confirm)
        layout.addWidget(options)

        self.inspect_btn = QPushButton("Inspect selected content")
        self.stage_btn = QPushButton("Stage custom content")
        row = QHBoxLayout(); row.addWidget(self.inspect_btn); row.addWidget(self.stage_btn); row.addStretch(1); layout.addLayout(row)

        review = QGroupBox("Inspection / review")
        rv = QVBoxLayout(review)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Source / target", "Type", "Ownership", "Permissions / conflict"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1,2,3): self.tree.header().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        rv.addWidget(self.tree); layout.addWidget(review, 1)
        self.status = QLabel("No source analyzed."); self.status.setWordWrap(True); layout.addWidget(self.status)

        self.add_files_btn.clicked.connect(self._add_files)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.add_archive_btn.clicked.connect(self._add_archive)
        self.clear_btn.clicked.connect(self._clear)
        self.inspect_btn.clicked.connect(self._inspect)
        self.stage_btn.clicked.connect(self._stage)
        self.target_kind.currentIndexChanged.connect(self._refresh_review)
        self.target_subpath.textChanged.connect(self._refresh_review)
        self.conflict.currentTextChanged.connect(self._refresh_review)
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        for w in (self.add_files_btn, self.add_folder_btn, self.add_archive_btn, self.clear_btn, self.target_kind, self.target_subpath, self.conflict, self.replace_confirm, self.inspect_btn, self.stage_btn):
            w.setEnabled(enabled)

    def _append_sources(self, paths: list[str]) -> None:
        for raw in paths:
            p = str(Path(raw).resolve())
            if p not in self.sources:
                self.sources.append(p); self.source_list.addItem(p)
        self._refresh_review()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select custom-content files")
        if paths: self._append_sources(paths)

    def _add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select custom-content folder")
        if path: self._append_sources([path])

    def _add_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select .tar.gz archive", "", "Tar GZip (*.tar.gz *.tgz)")
        if path: self._append_sources([path])

    def _clear(self) -> None:
        self.sources.clear(); self.source_list.clear(); self.tree.clear(); self.status.setText("Selection cleared.")

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls and all(u.isLocalFile() for u in urls): event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths: self._append_sources(paths); event.acceptProposedAction()

    def _target_root(self) -> str:
        kind = str(self.target_kind.currentData())
        text = self.target_subpath.text().strip()
        if kind == "default_user_content":
            if not text:
                return "/etc/skel/"
            p = PurePosixPath(text)
            if p.is_absolute():
                text = str(p).lstrip("/")
            return "/etc/skel/" + text.strip("/") + "/"
        return text or "/opt/chromapress-content"

    def _inspect_data(self) -> dict:
        return inspect_custom_content(self.sources)

    def _refresh_review(self) -> None:
        if not self.sources:
            return
        try:
            data = self._inspect_data()
        except Exception as exc:
            self.tree.clear(); self.status.setText(f"BLOCKED — {exc}"); return
        self._show_review(data)

    def _show_review(self, data: dict) -> None:
        self.tree.clear(); target_root = self._target_root(); policy = self.conflict.currentText()
        owner = "new user inherits" if self.target_kind.currentData() == "default_user_content" else "root:root at apply (review required)"
        for source in data.get("entries") or []:
            top = QTreeWidgetItem([str(source.get("source") or ""), str(source.get("kind") or ""), owner, f"{policy}; target conflict checked again before apply"])
            self.tree.addTopLevelItem(top)
            members = list(source.get("members") or [])
            for member in members[:250]:
                rel = str(member.get("path") or "").lstrip("/")
                target = target_root.rstrip("/") + "/" + rel if rel else target_root
                perm = str(member.get("mode") or "default")
                if member.get("type") == "symlink": perm += " -> " + str(member.get("link_target") or "")
                top.addChild(QTreeWidgetItem([target, str(member.get("type") or ""), owner, perm]))
            if len(members) > 250:
                top.addChild(QTreeWidgetItem([f"… {len(members)-250} more entries", "summary", owner, "full list retained in staged metadata"]));
            top.setExpanded(True)
        self.status.setText(f"INSPECTED — {data.get('entry_count',0)} entries; unsafe traversal/absolute paths/symlinks/special archive nodes rejected.")

    def _inspect(self) -> None:
        try:
            data = self._inspect_data(); self._show_review(data)
        except Exception as exc:
            self.status.setText(f"BLOCKED — {exc}"); QMessageBox.warning(self, "Custom content blocked", str(exc))

    def _stage(self) -> None:
        try:
            inspected = self._inspect_data()
        except Exception as exc:
            self.status.setText(f"BLOCKED — {exc}"); QMessageBox.warning(self, "Custom content blocked", str(exc)); return
        cap = self.capability
        target_root = self._target_root()
        payload = {
            "config_type": "part5_custom_content", "part": 5, "gate_version": "part5-complete",
            "source_sha256": str(self.analysis.get("sha256") or "").strip().casefold(), "analysis_scope": str(cap.get("analysis_scope") or ""),
            "capability_status": str(cap.get("capability_status") or "UNKNOWN"), "target_kind": str(self.target_kind.currentData()), "target_root": target_root,
            "conflict_policy": self.conflict.currentText(), "replace_unknown_content_confirmed": self.replace_confirm.isChecked(),
            "entries": list(inspected.get("entries") or []), "entry_count": int(inspected.get("entry_count") or 0),
            "archive_inspected": inspected.get("archive_inspected") is True, "safe_paths_verified": inspected.get("safe_paths_verified") is True,
            "symlinks_validated": inspected.get("symlinks_validated") is True, "show_target_paths": True, "show_conflicts": True,
            "show_ownership": True, "show_permissions": True, "require_review_before_apply": True,
            "require_target_conflict_review_before_apply": True, "never_silently_overwrite_unknown_source_content": True,
            "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }
        ok, msg = validate_custom_content_payload(payload)
        if not ok:
            self.status.setText(f"BLOCKED — {msg}"); QMessageBox.warning(self, "Custom content blocked", msg); return
        self.stage_requested.emit(ChangeItem("Part 5 custom content", ChangeKind.CONFIG, f"{payload['entry_count']} inspected entries → {target_root}; conflict policy {payload['conflict_policy']}.", payload))
        self.status.setText("STAGED — review target paths, ownership, permissions and conflicts in Changes before apply.")

    def set_analysis(self, data: dict) -> None:
        self.analysis = dict(data or {}); self.capability = dict(data.get("part5_custom_content_evidence") or {})
        status = str(self.capability.get("capability_status") or "UNKNOWN")
        self.cap_value.setText(f"{status} — {self.capability.get('reason','')}")
        enabled = status in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and bool(data.get("sha256"))
        self._set_enabled(enabled)
        self.status.setText(str(self.capability.get("reason") or "Analyze a source ISO first."))
