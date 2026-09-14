from __future__ import annotations

from pathlib import Path
import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QCheckBox, QPlainTextEdit,
    QFileDialog, QMessageBox
)

from chromapress.models import ProjectState
from chromapress.services.part7 import (
    COMPRESSION_CHOICES, VERIFICATION_POLICIES, HOOK_PHASES, HOOK_INTERPRETERS,
    available_production_presets, create_profile, save_profile, load_profile,
    profile_change_items, profile_summary_against_project, make_expert_hook,
    create_build_plan_payload, production_change, validate_build_plan_payload,
)
from chromapress.services.preflight import test_change
from chromapress.services.part8 import (
    build_static_acceptance, acceptance_summary, save_diagnostics, validate_acceptance_record,
)


class ProductionWorkflowPage(QWidget):
    stage_requested = Signal(object)
    import_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = ProjectState()
        self.loaded_profile: dict | None = None
        self.expert_hooks: list[dict] = []
        self._preflight_payload: dict | None = None

        layout = QVBoxLayout(self)
        title = QLabel("Build & Verify"); title.setObjectName("pageTitle"); layout.addWidget(title)
        intro = QLabel(
            "Part 7 production planning. Presets are inspectable JSON, Expert hooks are SHA-256 locked and human-reviewed, and the selected source ISO remains read-only."
        )
        intro.setWordWrap(True); layout.addWidget(intro)

        profile_box = QGroupBox("Reusable customization profile")
        pf = QFormLayout(profile_box)
        self.profile_name = QLineEdit("ChromaPress Production Profile")
        self.profile_status = QLabel("No profile loaded."); self.profile_status.setWordWrap(True)
        row = QWidget(); rh = QHBoxLayout(row); rh.setContentsMargins(0,0,0,0)
        self.save_profile_btn = QPushButton("Save / export profile…")
        self.load_profile_btn = QPushButton("Load / inspect profile…")
        self.import_profile_btn = QPushButton("Import verified plan")
        self.import_profile_btn.setEnabled(False)
        rh.addWidget(self.save_profile_btn); rh.addWidget(self.load_profile_btn); rh.addWidget(self.import_profile_btn)
        pf.addRow("Profile name:", self.profile_name); pf.addRow("Actions:", row); pf.addRow("Comparison:", self.profile_status)
        layout.addWidget(profile_box)

        prod_box = QGroupBox("Production build plan")
        form = QFormLayout(prod_box)
        self.preset = QComboBox(); self.preset.addItem("Custom production plan", "")
        self.output_dir = QLineEdit(); self.output_dir.setPlaceholderText(r"E:\Builds or /srv/builds")
        outrow = QWidget(); oh = QHBoxLayout(outrow); oh.setContentsMargins(0,0,0,0); oh.addWidget(self.output_dir,1)
        self.browse_output_btn = QPushButton("Browse…"); oh.addWidget(self.browse_output_btn)
        self.output_name = QLineEdit("chromapress-output.iso")
        self.compression = QComboBox(); self.compression.addItems(list(COMPRESSION_CHOICES))
        self.verification = QComboBox()
        self.verification.addItem("SHA-256", "sha256")
        self.verification.addItem("SHA-256 + boot structure", "sha256_boot_structure")
        self.verification.addItem("Strict runtime verification required", "strict_runtime_required")
        self.verification.setCurrentIndex(1)
        self.diagnostics = QCheckBox("Create diagnostics bundle metadata after build"); self.diagnostics.setChecked(True)
        form.addRow("Capability-backed preset:", self.preset)
        form.addRow("Output location:", outrow)
        form.addRow("Output filename:", self.output_name)
        form.addRow("Compression:", self.compression)
        form.addRow("Verification:", self.verification)
        form.addRow("Diagnostics:", self.diagnostics)
        layout.addWidget(prod_box)

        hooks_box = QGroupBox("Expert hooks — optional, reviewed and isolated")
        hf = QFormLayout(hooks_box)
        self.hook_path = QLineEdit(); self.hook_path.setPlaceholderText("Select a local reviewed script")
        hookrow = QWidget(); hh = QHBoxLayout(hookrow); hh.setContentsMargins(0,0,0,0); hh.addWidget(self.hook_path,1)
        self.hook_browse = QPushButton("Browse…"); hh.addWidget(self.hook_browse)
        self.hook_phase = QComboBox(); self.hook_phase.addItems(list(HOOK_PHASES))
        self.hook_interpreter = QComboBox(); self.hook_interpreter.addItems(list(HOOK_INTERPRETERS))
        self.hook_reviewed = QCheckBox("I reviewed this hook and understand it executes only in the isolated WSL build workspace")
        self.add_hook_btn = QPushButton("Add reviewed hook")
        self.hook_summary = QPlainTextEdit(); self.hook_summary.setReadOnly(True); self.hook_summary.setMaximumHeight(120)
        hf.addRow("Script:", hookrow); hf.addRow("Phase:", self.hook_phase); hf.addRow("Interpreter:", self.hook_interpreter)
        hf.addRow("Review:", self.hook_reviewed); hf.addRow("", self.add_hook_btn); hf.addRow("Staged hooks:", self.hook_summary)
        layout.addWidget(hooks_box)

        action_box = QGroupBox("Preflight & stage")
        av = QVBoxLayout(action_box)
        self.preflight_status = QLabel("BLOCKED — analyse a source ISO before preparing a production plan."); self.preflight_status.setWordWrap(True)
        buttons = QWidget(); bh = QHBoxLayout(buttons); bh.setContentsMargins(0,0,0,0)
        self.preflight_btn = QPushButton("Preflight build plan")
        self.stage_btn = QPushButton("Stage production plan"); self.stage_btn.setEnabled(False)
        bh.addWidget(self.preflight_btn); bh.addWidget(self.stage_btn)
        av.addWidget(self.preflight_status); av.addWidget(buttons)
        layout.addWidget(action_box)

        acceptance_box = QGroupBox("Cross-distribution acceptance — Part 8")
        av8 = QVBoxLayout(acceptance_box)
        self.acceptance_status = QLabel("BLOCKED — analyse a source ISO before generating acceptance evidence.")
        self.acceptance_status.setWordWrap(True)
        self.acceptance_details = QPlainTextEdit(); self.acceptance_details.setReadOnly(True); self.acceptance_details.setMaximumHeight(180)
        a8buttons = QWidget(); a8h = QHBoxLayout(a8buttons); a8h.setContentsMargins(0,0,0,0)
        self.acceptance_refresh_btn = QPushButton("Refresh static acceptance")
        self.acceptance_export_btn = QPushButton("Export diagnostics…"); self.acceptance_export_btn.setEnabled(False)
        a8h.addWidget(self.acceptance_refresh_btn); a8h.addWidget(self.acceptance_export_btn)
        av8.addWidget(self.acceptance_status); av8.addWidget(self.acceptance_details); av8.addWidget(a8buttons)
        layout.addWidget(acceptance_box)
        layout.addStretch(1)

        self.save_profile_btn.clicked.connect(self.save_current_profile)
        self.load_profile_btn.clicked.connect(self.load_profile_file)
        self.import_profile_btn.clicked.connect(self.import_loaded_profile)
        self.browse_output_btn.clicked.connect(self.browse_output)
        self.hook_browse.clicked.connect(self.browse_hook)
        self.add_hook_btn.clicked.connect(self.add_hook)
        self.preflight_btn.clicked.connect(self.preflight)
        self.stage_btn.clicked.connect(self.stage)
        self.acceptance_refresh_btn.clicked.connect(self.refresh_acceptance)
        self.acceptance_export_btn.clicked.connect(self.export_acceptance_diagnostics)
        for widget in (self.output_dir, self.output_name): widget.textChanged.connect(self._invalidate_preflight)
        self.compression.currentIndexChanged.connect(self._invalidate_preflight)
        self.verification.currentIndexChanged.connect(self._invalidate_preflight)
        self.preset.currentIndexChanged.connect(self._invalidate_preflight)
        self.diagnostics.toggled.connect(self._invalidate_preflight)

    def set_project(self, project: ProjectState) -> None:
        self.project = project
        current = self.preset.currentData()
        self.preset.blockSignals(True); self.preset.clear(); self.preset.addItem("Custom production plan", "")
        for preset in available_production_presets(project):
            self.preset.addItem(preset["label"], preset["id"])
        idx = self.preset.findData(current)
        self.preset.setCurrentIndex(max(0, idx)); self.preset.blockSignals(False)
        self._invalidate_preflight()
        self.refresh_acceptance()
        if self.loaded_profile:
            self._refresh_profile_comparison()

    def _production_settings(self) -> dict:
        return {
            "output_dir": self.output_dir.text().strip(),
            "output_name": self.output_name.text().strip(),
            "compression": self.compression.currentText(),
            "verification_policy": self.verification.currentData() or "sha256_boot_structure",
            "diagnostics_bundle": self.diagnostics.isChecked(),
            "preset_id": self.preset.currentData() or "",
        }

    def save_current_profile(self):
        try:
            profile = create_profile(self.project, self.profile_name.text(), self._production_settings())
        except Exception as exc:
            QMessageBox.warning(self, "Profile blocked", str(exc)); return
        path, _ = QFileDialog.getSaveFileName(self, "Save ChromaPress profile", "", "ChromaPress profile (*.chromapress-profile);;JSON (*.json)")
        if not path: return
        if not Path(path).suffix: path += ".chromapress-profile"
        try:
            save_profile(profile, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Profile blocked", str(exc)); return
        self.loaded_profile = profile; self._refresh_profile_comparison()
        QMessageBox.information(self, "ChromaPress", "Profile saved without generation credentials or other secret material.")

    def load_profile_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load ChromaPress profile", "", "ChromaPress profile (*.chromapress-profile *.json)")
        if not path: return
        try:
            self.loaded_profile = load_profile(Path(path))
        except Exception as exc:
            self.loaded_profile = None; self.import_profile_btn.setEnabled(False); self.profile_status.setText("BLOCKED — " + str(exc)); return
        prod = dict(self.loaded_profile.get("production") or {})
        if prod.get("output_dir"): self.output_dir.setText(str(prod["output_dir"]))
        if prod.get("output_name"): self.output_name.setText(str(prod["output_name"]))
        if prod.get("compression") in COMPRESSION_CHOICES: self.compression.setCurrentText(str(prod["compression"]))
        v = self.verification.findData(prod.get("verification_policy"));
        if v >= 0: self.verification.setCurrentIndex(v)
        self.diagnostics.setChecked(bool(prod.get("diagnostics_bundle", True)))
        self._refresh_profile_comparison()

    def _refresh_profile_comparison(self):
        if not self.loaded_profile:
            self.profile_status.setText("No profile loaded."); self.import_profile_btn.setEnabled(False); return
        try:
            summary = profile_summary_against_project(self.loaded_profile, self.project)
        except Exception as exc:
            self.profile_status.setText("BLOCKED — " + str(exc)); self.import_profile_btn.setEnabled(False); return
        src_same = bool(summary["source"]["same"])
        ch = summary["changes"]
        self.profile_status.setText(
            f"Source {'MATCH' if src_same else 'DIFF'} • saved changes {ch['left_count']} / current {ch['right_count']} • "
            f"added {len(ch['added'])} • removed {len(ch['removed'])} • scenario {'MATCH' if summary['same_scenario'] else 'DIFF'}"
        )
        self.import_profile_btn.setEnabled(src_same)

    def import_loaded_profile(self):
        if not self.loaded_profile: return
        try:
            items = profile_change_items(self.loaded_profile, self.project.source.sha256)
            failures = []
            for item in items:
                status, message = test_change(item)
                if status.value in {"FAIL", "BLOCKED"}: failures.append(f"{item.title}: {message}")
            if failures: raise ValueError("Imported plan failed preflight: " + "; ".join(failures[:5]))
        except Exception as exc:
            QMessageBox.warning(self, "Import blocked", str(exc)); return
        answer = QMessageBox.question(self, "Import verified plan", "Replace the current staged plan with the verified profile plan? The selected source ISO remains unchanged.")
        if answer != QMessageBox.StandardButton.Yes: return
        self.import_requested.emit({"changes": items, "scenario": str(self.loaded_profile.get("scenario") or "")})

    def refresh_acceptance(self):
        try:
            record = build_static_acceptance(self.project.source)
            ok, message = validate_acceptance_record(record)
            if not ok:
                raise ValueError(message)
        except Exception as exc:
            self._part8_record = None
            self.acceptance_export_btn.setEnabled(False)
            self.acceptance_status.setText("BLOCKED — " + str(exc))
            self.acceptance_details.clear()
            return
        self._part8_record = record
        self.acceptance_export_btn.setEnabled(bool(record.get("source_sha256")))
        state = str(record.get("verification_state") or "")
        if state == "VERIFIED":
            self.acceptance_status.setText("VERIFIED — explicit runtime evidence completed every required Part 8 gate.")
        elif state == "STATIC_READY_RUNTIME_REQUIRED":
            self.acceptance_status.setText("STATIC READY — runtime acceptance is still required; analysis alone is never VERIFIED.")
        else:
            self.acceptance_status.setText("STATIC INCOMPLETE — review unknown/static gates before runtime acceptance.")
        lines = [acceptance_summary(record), ""]
        for row in record.get("checks") or []:
            lines.append(f"{row['status']:>16}  {row['label']} — {row['evidence']}")
        self.acceptance_details.setPlainText("\n".join(lines))

    def export_acceptance_diagnostics(self):
        record = getattr(self, "_part8_record", None)
        if not record:
            self.refresh_acceptance(); record = getattr(self, "_part8_record", None)
        if not record:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Part 8 acceptance diagnostics", "", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_diagnostics(record, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Acceptance export blocked", str(exc)); return
        QMessageBox.information(self, "ChromaPress", "Part 8 diagnostics exported. Runtime/boot checks remain manual until explicit evidence is recorded.")

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path: self.output_dir.setText(path)

    def browse_hook(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select reviewed Expert hook")
        if path: self.hook_path.setText(path)

    def add_hook(self):
        try:
            hook = make_expert_hook(Path(self.hook_path.text()), self.hook_phase.currentText(), self.hook_interpreter.currentText(), self.hook_reviewed.isChecked())
            if not hook["human_reviewed"]: raise ValueError("Explicit human review is required before an Expert hook can be added.")
        except Exception as exc:
            QMessageBox.warning(self, "Expert hook blocked", str(exc)); return
        self.expert_hooks.append(hook)
        self.hook_summary.setPlainText("\n".join(f"{h['phase']} • {h['interpreter']} • {h['sha256'][:12]}… • {h['source_path']}" for h in self.expert_hooks))
        self.hook_reviewed.setChecked(False); self._invalidate_preflight()

    def _invalidate_preflight(self, *_args):
        self._preflight_payload = None
        if hasattr(self, "stage_btn"): self.stage_btn.setEnabled(False)
        if hasattr(self, "preflight_status"):
            if self.project.source.sha256:
                self.preflight_status.setText("REVIEW REQUIRED — run preflight after checking output, verification policy, preset and Expert hooks.")
            else:
                self.preflight_status.setText("BLOCKED — analyse a source ISO before preparing a production plan.")

    def preflight(self):
        try:
            payload = create_build_plan_payload(
                self.project, output_dir=self.output_dir.text(), output_name=self.output_name.text(),
                compression=self.compression.currentText(), verification_policy=self.verification.currentData(),
                diagnostics_bundle=self.diagnostics.isChecked(), preset_id=self.preset.currentData() or "",
                expert_hooks=self.expert_hooks,
            )
            change = production_change(payload)
            status, message = test_change(change)
            if status.value != "PASS": raise ValueError(message)
        except Exception as exc:
            self._preflight_payload = None; self.stage_btn.setEnabled(False); self.preflight_status.setText("BLOCKED — " + str(exc)); return
        self._preflight_payload = payload
        self.stage_btn.setEnabled(True)
        self.preflight_status.setText(
            f"PASS — source SHA locked • {payload['change_count']} staged changes • output {payload['output_name']} • "
            f"{len(payload['expert_hooks'])} reviewed hook(s) • verification {payload['verification_policy']}."
        )

    def stage(self):
        if not self._preflight_payload:
            self.preflight();
            if not self._preflight_payload: return
        ok, message = validate_build_plan_payload(self._preflight_payload)
        if not ok:
            self._invalidate_preflight(); QMessageBox.warning(self, "Production plan blocked", message); return
        self.stage_requested.emit(production_change(self._preflight_payload))
        self.stage_btn.setEnabled(False)
        self.preflight_status.setText("STAGED — production build plan added to Changes. Apply/build still requires final human review and target-specific runtime verification.")
