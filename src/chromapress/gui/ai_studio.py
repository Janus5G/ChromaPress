from __future__ import annotations

import json

from PySide6.QtCore import QObject, QThread, Signal, QRegularExpression, Qt
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QPlainTextEdit, QSplitter, QMessageBox, QFormLayout, QGroupBox,
    QToolButton, QCheckBox
)

from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.ai import AiRequest, generate_code
from chromapress.services.ai_catalog import AI_PROVIDERS, provider_by_id, normalized_model_id
from chromapress.services.part6 import (
    review_generated_project, ai_app_payload, dependency_change_items, validate_target_context,
)


class CplHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        keyword = QTextCharFormat(); keyword.setForeground(QColor("#6d28d9")); keyword.setFontWeight(700)
        comment = QTextCharFormat(); comment.setForeground(QColor("#64748b"))
        string = QTextCharFormat(); string.setForeground(QColor("#9a3412"))
        self.rules = [
            (QRegularExpression(r"\b(potens|tal|streng|konstant|pixel|skriv_voxel|kanal|rød|grøn|blå|violet|uv|var|store|load|print|HALT)\b", QRegularExpression.PatternOption.CaseInsensitiveOption), keyword),
            (QRegularExpression(r"//[^\n]*"), comment),
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"'), string),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next(); self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class AiWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, req):
        super().__init__(); self.req = req

    def run(self):
        try:
            self.finished.emit(generate_code(self.req))
        except Exception as exc:
            self.failed.emit(str(exc))


class AiStudioPage(QWidget):
    change_requested = Signal(object)
    settings_requested = Signal()
    configuration_changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._threads = []
        self.target_context: dict = {}
        self._review: dict | None = None

        layout = QVBoxLayout(self)
        title = QLabel("AI App Studio"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Optional coding workspace. Generated applications remain normal inspectable source projects and are never blindly injected into the ISO."
        )
        intro.setWordWrap(True); layout.addWidget(intro)

        config = QGroupBox("Generation")
        form = QFormLayout(config)
        self.provider = QComboBox()
        for provider in AI_PROVIDERS:
            self.provider.addItem(provider.label, provider.id)
        self.model = QComboBox()
        self.model_help = QLabel(); self.model_help.setWordWrap(True)
        self.settings_btn = QPushButton("AI settings…")
        settings_row = QWidget(); sh = QHBoxLayout(settings_row); sh.setContentsMargins(0,0,0,0)
        sh.addWidget(self.model, 1); sh.addWidget(self.settings_btn)
        self.credential_note = QLabel("Generation credential: session-only. Runtime application credentials are separate and are never copied from the generation credential.")
        self.credential_note.setWordWrap(True)
        form.addRow("AI provider:", self.provider)
        form.addRow("Model/version:", settings_row)
        form.addRow("Best for:", self.model_help)
        form.addRow("Credential policy:", self.credential_note)
        layout.addWidget(config)

        target_box = QGroupBox("Detected target Linux context")
        target_layout = QVBoxLayout(target_box)
        self.target_status = QLabel("Analyze a source ISO first."); self.target_status.setWordWrap(True)
        target_layout.addWidget(self.target_status)
        layout.addWidget(target_box)

        self.advanced_toggle = QToolButton(); self.advanced_toggle.setText("Advanced"); self.advanced_toggle.setCheckable(True); self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.advanced_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.advanced_box = QGroupBox("Advanced coding options")
        advanced_form = QFormLayout(self.advanced_box)
        self.toolchain = QComboBox(); self.toolchain.addItems(["Auto", "Python / PySide6", "Qt / C++", "C / C++", "Rust", "CPL / CPA"])
        advanced_form.addRow("Toolchain:", self.toolchain)
        note = QLabel("Endpoint, WSL and storage details are configured centrally in Settings → Advanced. Build/test commands are reviewed plans; untrusted generated code is not auto-executed on the host.")
        note.setWordWrap(True); advanced_form.addRow("", note)
        self.advanced_box.setVisible(False); layout.addWidget(self.advanced_box)

        split = QSplitter()
        prompt_wrap = QWidget(); pv = QVBoxLayout(prompt_wrap)
        pv.addWidget(QLabel("Describe the application"))
        self.prompt = QPlainTextEdit(); self.prompt.setPlaceholderText("Example: Build a small Qt application for managing network profiles with Danish and English UI.")
        pv.addWidget(self.prompt)
        self.generate_btn = QPushButton("Generate / revise"); pv.addWidget(self.generate_btn)

        code_wrap = QWidget(); cv = QVBoxLayout(code_wrap)
        cv.addWidget(QLabel("Generated project/source — inspect and edit before staging"))
        self.code = QPlainTextEdit(); cv.addWidget(self.code)
        action_row = QWidget(); ah = QHBoxLayout(action_row); ah.setContentsMargins(0,0,0,0)
        self.inspect_btn = QPushButton("Inspect & validate")
        self.stage_btn = QPushButton("Stage reviewed app"); self.stage_btn.setEnabled(False)
        ah.addWidget(self.inspect_btn); ah.addWidget(self.stage_btn); cv.addWidget(action_row)
        split.addWidget(prompt_wrap); split.addWidget(code_wrap); split.setSizes([450, 650]); layout.addWidget(split, 1)

        review_box = QGroupBox("Part 6 review")
        rv = QVBoxLayout(review_box)
        self.review_status = QLabel("No generated project reviewed yet."); self.review_status.setWordWrap(True)
        self.review_details = QPlainTextEdit(); self.review_details.setReadOnly(True); self.review_details.setMaximumHeight(220)
        self.human_review_check = QCheckBox("I have actively reviewed the generated code, security implications and dependencies.")
        self.human_review_check.setChecked(False)
        self.human_review_check.setEnabled(False)
        rv.addWidget(self.review_status); rv.addWidget(self.review_details); rv.addWidget(self.human_review_check)
        layout.addWidget(review_box)

        self.highlighter = CplHighlighter(self.code.document())
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.model.editTextChanged.connect(lambda _text: self._model_changed())
        self.settings_btn.clicked.connect(self.settings_requested)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.generate_btn.clicked.connect(self.generate)
        self.inspect_btn.clicked.connect(self.inspect_project)
        self.stage_btn.clicked.connect(self.stage)
        self.human_review_check.toggled.connect(self._update_stage_enabled)
        self.code.textChanged.connect(self._invalidate_review)
        self.refresh_from_settings()
        self.stage_btn.setEnabled(False)

    def _current_model(self) -> str:
        return str(self.model.currentData() or self.model.currentText() or "").strip()

    def refresh_from_settings(self):
        provider_id = self.settings.ai_provider or "openai"
        idx = self.provider.findData(provider_id)
        self.provider.blockSignals(True); self.provider.setCurrentIndex(max(0, idx)); self.provider.blockSignals(False)
        self._populate_models(self.settings.ai_model)

    def _populate_models(self, preferred: str = ""):
        provider = provider_by_id(self.provider.currentData())
        preferred = normalized_model_id(provider.id, preferred)
        self.model.blockSignals(True); self.model.clear(); self.model.setEditable(provider.editable_model)
        for option in provider.models:
            self.model.addItem(option.label, option.id)
            self.model.setItemData(self.model.count()-1, option.description, Qt.ItemDataRole.ToolTipRole)
        idx = self.model.findData(preferred)
        if idx >= 0:
            self.model.setCurrentIndex(idx)
        elif provider.editable_model:
            self.model.setEditText(preferred)
        else:
            self.model.setCurrentIndex(0)
        self.model.blockSignals(False); self._update_model_help()

    def _provider_changed(self):
        self.settings.ai_provider = self.provider.currentData() or "openai"
        self._populate_models("")
        self.settings.ai_model = self._current_model()
        self.configuration_changed.emit(); self._invalidate_review()

    def _model_changed(self):
        if self.model.count() == 0: return
        self.settings.ai_model = self._current_model(); self._update_model_help(); self.configuration_changed.emit(); self._invalidate_review()

    def _update_model_help(self):
        provider = provider_by_id(self.provider.currentData()); current = self._current_model()
        option = next((m for m in provider.models if m.id == current), None)
        text = option.description if option else f"Custom model ID for {provider.label}."
        self.model.setToolTip(text); self.model_help.setText(text)

    def _toggle_advanced(self, checked: bool):
        self.advanced_box.setVisible(checked); self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def set_target_context(self, context):
        self.target_context = dict(context or {}) if isinstance(context, dict) else {}
        ok, message = validate_target_context(self.target_context)
        if ok:
            c = self.target_context
            self.target_status.setText(
                f"READY — {c.get('distribution')} {c.get('version')} • {c.get('architecture')} • desktop {c.get('desktop')} • "
                f"{c.get('package_manager')} • installer {c.get('installer_type')} • {len(c.get('available_libraries') or [])} detected library/package hints"
            )
        else:
            self.target_status.setText("BLOCKED — " + message)
        self._invalidate_review()

    def _update_stage_enabled(self, *_args):
        review_ok = bool(self._review and self._review.get("status") == "PASS")
        target_ok, _message = validate_target_context(self.target_context)
        human_review_ok = bool(hasattr(self, "human_review_check") and self.human_review_check.isChecked())
        if hasattr(self, "stage_btn"):
            self.stage_btn.setEnabled(review_ok and target_ok and human_review_ok)

    def _invalidate_review(self):
        self._review = None
        if hasattr(self, "human_review_check"):
            self.human_review_check.blockSignals(True)
            self.human_review_check.setChecked(False)
            self.human_review_check.setEnabled(False)
            self.human_review_check.blockSignals(False)
        self._update_stage_enabled()
        if hasattr(self, "review_status"):
            self.review_status.setText("Project changed — run Inspect & validate before staging.")

    def generate(self):
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "ChromaPress", "Describe the application first."); return
        ok, target_message = validate_target_context(self.target_context)
        if not ok:
            QMessageBox.warning(self, "Target context required", target_message); return
        provider = provider_by_id(self.provider.currentData())
        if provider.requires_api_key and not self.settings.ai_api_key.strip():
            QMessageBox.information(self, "AI API key required", "Set the generation API key in Settings → General → AI & Coding. It is kept only for this ChromaPress session.")
            self.settings_requested.emit(); return
        req = AiRequest(
            provider=provider.id,
            endpoint=self.settings.ai_endpoint,
            api_key=self.settings.ai_api_key,
            model=self._current_model(),
            prompt=prompt,
            toolchain=self.toolchain.currentText(),
            target_context=self.target_context,
        )
        worker = AiWorker(req); thread = QThread(self); worker.moveToThread(thread); thread.started.connect(worker.run)
        self.generate_btn.setEnabled(False)
        worker.finished.connect(self._generation_finished)
        worker.failed.connect(lambda msg: (QMessageBox.critical(self, "AI generation failed", msg), self.generate_btn.setEnabled(True)))
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(lambda: self._threads.remove((thread, worker)) if (thread, worker) in self._threads else None)
        self._threads.append((thread, worker)); thread.start()

    def _generation_finished(self, text: str):
        self.code.setPlainText(text); self.generate_btn.setEnabled(True); self.inspect_project()

    def inspect_project(self):
        text = self.code.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "ChromaPress", "Generate or paste an inspectable project first."); return
        try:
            review = review_generated_project(text, generation_credential=self.settings.ai_api_key)
        except Exception as exc:
            self._review = None; self.stage_btn.setEnabled(False)
            self.review_status.setText(f"BLOCKED — {exc}"); self.review_details.setPlainText(str(exc)); return
        self._review = review
        manifest = review["manifest"]
        lines = [
            f"Application: {manifest['name']} {manifest['version']}",
            f"Files: {review['file_count']}",
            "Files being added: " + ", ".join(row["path"] for row in review["files"]),
            "Packages required: " + (", ".join(x["name"] for x in manifest["packages"]) or "none"),
            "Services required: " + (", ".join(manifest["services"]) or "none"),
            "Permissions: " + (", ".join(manifest["permissions"]) or "none"),
            "Autostart: " + (", ".join(manifest["autostart"]) or "none"),
            "Desktop integration: " + (", ".join(manifest["desktop_integration"]) or "none"),
            "Security implications: " + (", ".join(manifest["security_implications"]) or "none declared"),
            "Build plan: " + manifest["build"]["command"],
            "Test plan: " + manifest["test"]["command"],
            "Apply remains blocked until build/test/security/dependency review gates are explicitly completed.",
        ]
        if review["errors"]:
            lines.extend("ERROR: " + x for x in review["errors"])
        lines.extend("NOTE: " + x for x in review["warnings"])
        self.review_details.setPlainText("\n".join(lines))
        if review["status"] == "PASS":
            self.human_review_check.setEnabled(True)
            target_ok, target_message = validate_target_context(self.target_context)
            if target_ok:
                self.review_status.setText("PASS — project envelope, paths, manifest, credential leak scan and target Linux context passed. Confirm the human-review checkbox before staging.")
            else:
                self.review_status.setText("PASS — project inspection passed. STAGING BLOCKED — " + target_message)
            self._update_stage_enabled()
        else:
            self.human_review_check.blockSignals(True)
            self.human_review_check.setChecked(False)
            self.human_review_check.setEnabled(False)
            self.human_review_check.blockSignals(False)
            self.review_status.setText("BLOCKED — generated project failed security/credential inspection.")
            self._update_stage_enabled()

    def stage(self):
        self.inspect_project()
        if not self._review or self._review.get("status") != "PASS":
            return
        target_ok, target_message = validate_target_context(self.target_context)
        if not target_ok:
            self._update_stage_enabled()
            QMessageBox.warning(self, "Target context required", target_message)
            return
        if not self.human_review_check.isChecked():
            self._update_stage_enabled()
            QMessageBox.warning(self, "Human review required", "Actively confirm the human-review checkbox before staging an AI-generated application.")
            return
        try:
            payload = ai_app_payload(
                self._review, self.target_context,
                provider=self.provider.currentData() or "openai",
                model=self._current_model(), toolchain=self.toolchain.currentText(), prompt=self.prompt.toPlainText(),
                human_review_acknowledged=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "ChromaPress", str(exc)); return
        project_id = payload["project_id"]
        for dep in dependency_change_items(self._review, self.target_context, project_id):
            self.change_requested.emit(dep)
        manifest = self._review["manifest"]
        self.change_requested.emit(ChangeItem(
            manifest["name"], ChangeKind.AI_APP,
            f"{self.provider.currentText()} • {self._current_model()} • {self._review['file_count']} files • {len(manifest['packages'])} package dependencies",
            payload,
        ))
