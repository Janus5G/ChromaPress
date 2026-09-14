from __future__ import annotations

from pathlib import Path
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout,
    QFileDialog, QPushButton, QHBoxLayout, QWidget, QComboBox, QLabel,
    QTabWidget, QGroupBox
)

from chromapress.services.ai_catalog import AI_PROVIDERS, provider_by_id, normalized_model_id


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("ChromaPress Settings")
        self.resize(780, 560)
        self.setMinimumSize(720, 500)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        # ---- Simple/default settings ----
        general = QWidget()
        gv = QVBoxLayout(general)

        storage_box = QGroupBox("Storage")
        sf = QFormLayout(storage_box)
        root = settings.storage_root or self._derive_storage_root()
        self._initial_effective_root = root
        self.storage_root = QLineEdit(root)
        self.storage_status = QLabel()
        self.storage_status.setWordWrap(True)
        sf.addRow("Storage location:", self._browse_row(self.storage_root, self._storage_changed))
        sf.addRow("Status:", self.storage_status)
        gv.addWidget(storage_box)

        ai_box = QGroupBox("AI & Coding")
        af = QFormLayout(ai_box)
        self.provider = QComboBox()
        for provider in AI_PROVIDERS:
            self.provider.addItem(provider.label, provider.id)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.ai_provider)))

        self.model = QComboBox()
        self.api_key = QLineEdit(settings.ai_api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API key — kept only for this ChromaPress session")

        self.cpl_status = QLabel(
            "Configured" if settings.cpl_toolchain_path.strip() else "Auto-detect when CPL/CPA bridge is enabled"
        )
        self.cpl_status.setWordWrap(True)

        af.addRow("AI provider:", self.provider)
        af.addRow("Model/version:", self.model)
        af.addRow("API key:", self.api_key)
        af.addRow("CPL/CPA:", self.cpl_status)
        gv.addWidget(ai_box)
        gv.addStretch(1)
        tabs.addTab(general, "General")

        # ---- Technical overrides ----
        advanced = QWidget()
        adv = QFormLayout(advanced)
        self.wsl = QLineEdit(settings.wsl_distro if os.name == "nt" else "Native Linux")
        self.wsl.setEnabled(os.name == "nt")
        self.workspace = QLineEdit(settings.workspace_dir)
        self.cache = QLineEdit(settings.cache_dir)
        self.reserve = QSpinBox(); self.reserve.setRange(5, 500); self.reserve.setValue(settings.reserve_gb); self.reserve.setSuffix(" GB")
        self.ai_endpoint = QLineEdit(settings.ai_endpoint)
        self.ai_endpoint.setPlaceholderText("Only needed for preview/custom compatible providers")
        self.cpl = QLineEdit(settings.cpl_toolchain_path)
        adv.addRow("WSL distribution:" if os.name == "nt" else "Execution engine:", self.wsl)
        adv.addRow("Build workspace:", self._browse_row(self.workspace))
        adv.addRow("ISO/download cache:", self._browse_row(self.cache))
        adv.addRow("Minimum free-space reserve:", self.reserve)
        adv.addRow("Provider endpoint override:", self.ai_endpoint)
        adv.addRow("CPL/CPA toolchain path:", self._browse_row(self.cpl))
        tabs.addTab(advanced, "Advanced")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.provider.currentIndexChanged.connect(self._populate_models)
        self.model.currentIndexChanged.connect(self._update_model_tooltip)
        self.model.editTextChanged.connect(lambda _text: self._update_model_tooltip())
        self.storage_root.textChanged.connect(self._storage_changed)
        self._populate_models()
        desired = normalized_model_id(self.provider.currentData(), settings.ai_model)
        idx = self.model.findData(desired)
        self.model.setCurrentIndex(max(0, idx))
        self._storage_changed()

    def _derive_storage_root(self) -> str:
        paths = [p for p in (self.settings.workspace_dir, self.settings.cache_dir) if p]
        if len(paths) == 2:
            try:
                return str(Path(paths[0]).parent) if Path(paths[0]).parent == Path(paths[1]).parent else ""
            except Exception:
                return ""
        return ""

    def _browse_row(self, edit, callback=None):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton("Browse…"); h.addWidget(b)
        b.clicked.connect(lambda: self._browse(edit, callback))
        return w

    def _browse(self, edit, callback=None):
        path = QFileDialog.getExistingDirectory(self, "Select directory", edit.text())
        if path:
            edit.setText(path)
            if callback:
                callback()

    def _storage_changed(self):
        text = self.storage_root.text().strip()
        if not text:
            self.storage_status.setText("Choose a location before downloading or building large images.")
            return
        path = Path(text)
        existing = path if path.exists() else path.parent
        try:
            usage = shutil.disk_usage(existing)
            free_gb = usage.free / (1024 ** 3)
            reserve = self.reserve.value() if hasattr(self, "reserve") else self.settings.reserve_gb
            ready = free_gb >= reserve
            state = "READY" if ready else "BLOCKED — below safety reserve"
            self.storage_status.setText(f"{free_gb:.1f} GB free • safety reserve {reserve} GB • {state}")
        except Exception:
            self.storage_status.setText("Location selected. Free-space status will be verified before large operations.")

    def _populate_models(self):
        provider = provider_by_id(self.provider.currentData())
        previous = str(self.model.currentData() or self.model.currentText() or "").strip()
        self.model.clear()
        self.model.setEditable(provider.editable_model)
        for option in provider.models:
            self.model.addItem(option.label, option.id)
            index = self.model.count() - 1
            self.model.setItemData(index, option.description, Qt.ItemDataRole.ToolTipRole)
        desired = normalized_model_id(provider.id, previous)
        idx = self.model.findData(desired)
        if idx >= 0:
            self.model.setCurrentIndex(idx)
        elif provider.editable_model:
            self.model.setEditText(desired)
        self.api_key.setPlaceholderText(
            "Optional for local endpoint — session only" if not provider.requires_api_key else "API key — kept only for this ChromaPress session"
        )
        self._update_model_tooltip()

    def _update_model_tooltip(self):
        provider = provider_by_id(self.provider.currentData())
        current = str(self.model.currentData() or self.model.currentText() or "").strip()
        option = next((m for m in provider.models if m.id == current), None)
        self.model.setToolTip(option.description if option else f"Custom model ID for {provider.label}.")

    def apply(self):
        root = self.storage_root.text().strip()
        old_root = self._initial_effective_root.strip()
        self.settings.storage_root = root
        if os.name == "nt":
            self.settings.wsl_distro = self.wsl.text().strip() or "Ubuntu"

        # In normal use, one root is enough. If Advanced already contains paths
        # outside the old/default root, keep those explicit overrides.
        default_old_workspace = str(Path(old_root) / "build") if old_root else ""
        default_old_cache = str(Path(old_root) / "cache") if old_root else ""
        workspace_text = self.workspace.text().strip()
        cache_text = self.cache.text().strip()
        if root and (not workspace_text or workspace_text == default_old_workspace):
            workspace_text = str(Path(root) / "build")
        if root and (not cache_text or cache_text == default_old_cache):
            cache_text = str(Path(root) / "cache")
        self.settings.workspace_dir = workspace_text
        self.settings.cache_dir = cache_text
        self.settings.reserve_gb = self.reserve.value()

        self.settings.ai_provider = self.provider.currentData() or "openai"
        self.settings.ai_model = str(self.model.currentData() or self.model.currentText() or "gpt-5.6-sol").strip()
        self.settings.ai_api_key = self.api_key.text().strip()  # runtime only
        self.settings.ai_endpoint = self.ai_endpoint.text().strip()
        self.settings.cpl_toolchain_path = self.cpl.text().strip()
