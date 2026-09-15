from __future__ import annotations
from chromapress.i18n import tr
from pathlib import Path
import json
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout, QLineEdit, QComboBox, QPushButton, QCheckBox, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QProgressBar
from chromapress.models import ProjectState
from chromapress.services.part7 import COMPRESSION_CHOICES, VERIFICATION_POLICIES, HOOK_PHASES, HOOK_INTERPRETERS, available_production_presets, create_profile, save_profile, load_profile, profile_change_items, profile_summary_against_project, make_expert_hook, create_build_plan_payload, production_change, validate_build_plan_payload
from chromapress.services.preflight import test_change
from chromapress.services.part8 import build_static_acceptance, acceptance_summary, save_diagnostics, validate_acceptance_record
from chromapress.services.wsl import WslBridge


class _BuildWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, distro: str, execution_plan: dict):
        super().__init__()
        self.distro = distro
        self.execution_plan = execution_plan

    @Slot()
    def run(self):
        try:
            result = WslBridge(self.distro).build_iso(
                self.execution_plan,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class _BuildProgressDialog(QDialog):
    _DROPS = (
        ("        0 11", "        0", "        0 "),
        ("         1 0", "        1", "        0 "),
        ("        0   ", "        11", "         1"),
        ("         1  ", "        0", "        10"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Building ISO"))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        title = QLabel("DESTILLATION\nbinary  →  Tux")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        self.ascii_view = QLabel()
        self.ascii_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ascii_view.setStyleSheet(
            'font-family: Consolas, "Courier New", monospace; '
            "font-size: 13px; background: #11161d; color: #e8edf5; "
            "border: 1px solid #303a46; border-radius: 7px; padding: 12px;"
        )
        layout.addWidget(self.ascii_view)

        self.phase_label = QLabel(tr("Preparing build…"))
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_label.setWordWrap(True)
        layout.addWidget(self.phase_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel(
            tr("Progress follows completed build phases; it is not an elapsed-time estimate.")
        )
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._animate)
        self._timer.start()
        self._animate()

    def _animate(self):
        drops = self._DROPS[self._frame % len(self._DROPS)]
        self._frame += 1
        picture = [
            "      /------\\",
            "     / 01001  \\",
            "     | 10110  |",
            "     | 01101  |",
            "     \\        /",
            "      \\------/",
            "        ||",
            "        ||",
            *drops,
            "        .--.",
            "       |o_o |",
            "       |:_/ |",
            "      //   \\\\",
            "     (|     |)",
            "    /'\\_   _/'\\",
            "    \\___)=(___/",
        ]
        self.ascii_view.setText("\n".join(picture))

    @Slot(object)
    def set_progress(self, payload):
        if not isinstance(payload, dict):
            return
        try:
            value = int(payload.get("percent", self.progress_bar.value()))
        except (TypeError, ValueError):
            value = self.progress_bar.value()
        value = max(self.progress_bar.value(), min(100, max(0, value)))
        self.progress_bar.setValue(value)

        phase = str(payload.get("phase") or "").strip()
        if phase:
            self.phase_label.setText(phase)

        detail = str(payload.get("detail") or "").strip()
        if detail:
            self.detail_label.setText(detail)

    def finish_success(self):
        self.set_progress({
            "percent": 100,
            "phase": "ISO BUILD COMPLETE!",
            "detail": tr("Output hash and static boot checks passed. Runtime boot verification is still required."),
        })
        self._timer.stop()

    def finish_failure(self):
        self._timer.stop()


class ProductionWorkflowPage(QWidget):
    stage_requested = Signal(object)
    import_requested = Signal(object)

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self._build_thread = None
        self._build_worker = None
        self.project = ProjectState()
        self.loaded_profile: dict | None = None
        self.expert_hooks: list[dict] = []
        self._preflight_payload: dict | None = None
        layout = QVBoxLayout(self)
        title = QLabel(tr('Build & Verify'))
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        intro = QLabel(tr('Part 7 production planning. Presets are inspectable JSON, Expert hooks are SHA-256 locked and human-reviewed, and the selected source ISO remains read-only.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        profile_box = QGroupBox(tr('Reusable customization profile'))
        pf = QFormLayout(profile_box)
        self.profile_name = QLineEdit('ChromaPress Production Profile')
        self.profile_status = QLabel(tr('No profile loaded.'))
        self.profile_status.setWordWrap(True)
        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        self.save_profile_btn = QPushButton(tr('Save / export profile…'))
        self.load_profile_btn = QPushButton(tr('Load / inspect profile…'))
        self.import_profile_btn = QPushButton(tr('Import verified plan'))
        self.import_profile_btn.setEnabled(False)
        rh.addWidget(self.save_profile_btn)
        rh.addWidget(self.load_profile_btn)
        rh.addWidget(self.import_profile_btn)
        pf.addRow(tr('Profile name:'), self.profile_name)
        pf.addRow(tr('Actions:'), row)
        pf.addRow(tr('Comparison:'), self.profile_status)
        layout.addWidget(profile_box)
        prod_box = QGroupBox(tr('Production build plan'))
        form = QFormLayout(prod_box)
        self.preset = QComboBox()
        self.preset.addItem(tr('Custom production plan'), '')
        self.output_dir = QLineEdit()
        self.output_dir.setPlaceholderText(tr('E:\\Builds or /srv/builds'))
        outrow = QWidget()
        oh = QHBoxLayout(outrow)
        oh.setContentsMargins(0, 0, 0, 0)
        oh.addWidget(self.output_dir, 1)
        self.browse_output_btn = QPushButton(tr('Browse…'))
        oh.addWidget(self.browse_output_btn)
        self.output_name = QLineEdit('chromapress-output.iso')
        self.compression = QComboBox()
        self.compression.addItems(list(COMPRESSION_CHOICES))
        self.verification = QComboBox()
        self.verification.addItem(tr('SHA-256'), 'sha256')
        self.verification.addItem(tr('SHA-256 + boot structure'), 'sha256_boot_structure')
        self.verification.addItem(tr('Strict runtime verification required'), 'strict_runtime_required')
        self.verification.setCurrentIndex(1)
        self.diagnostics = QCheckBox(tr('Create diagnostics bundle metadata after build'))
        self.diagnostics.setChecked(True)
        form.addRow(tr('Capability-backed preset:'), self.preset)
        form.addRow(tr('Output location:'), outrow)
        form.addRow(tr('Output filename:'), self.output_name)
        form.addRow(tr('Compression:'), self.compression)
        form.addRow(tr('Verification:'), self.verification)
        form.addRow(tr('Diagnostics:'), self.diagnostics)
        layout.addWidget(prod_box)
        hooks_box = QGroupBox(tr('Expert hooks — optional, reviewed and isolated'))
        hf = QFormLayout(hooks_box)
        self.hook_path = QLineEdit()
        self.hook_path.setPlaceholderText(tr('Select a local reviewed script'))
        hookrow = QWidget()
        hh = QHBoxLayout(hookrow)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.addWidget(self.hook_path, 1)
        self.hook_browse = QPushButton(tr('Browse…'))
        hh.addWidget(self.hook_browse)
        self.hook_phase = QComboBox()
        self.hook_phase.addItems(list(HOOK_PHASES))
        self.hook_interpreter = QComboBox()
        self.hook_interpreter.addItems(list(HOOK_INTERPRETERS))
        self.hook_reviewed = QCheckBox(tr('I reviewed this hook and understand it executes only in the isolated WSL build workspace'))
        self.add_hook_btn = QPushButton(tr('Add reviewed hook'))
        self.hook_summary = QPlainTextEdit()
        self.hook_summary.setReadOnly(True)
        self.hook_summary.setMaximumHeight(120)
        hf.addRow(tr('Script:'), hookrow)
        hf.addRow(tr('Phase:'), self.hook_phase)
        hf.addRow(tr('Interpreter:'), self.hook_interpreter)
        hf.addRow(tr('Review:'), self.hook_reviewed)
        hf.addRow(tr(''), self.add_hook_btn)
        hf.addRow(tr('Staged hooks:'), self.hook_summary)
        layout.addWidget(hooks_box)
        action_box = QGroupBox(tr('Preflight & stage'))
        av = QVBoxLayout(action_box)
        self.preflight_status = QLabel(tr('BLOCKED — analyse a source ISO before preparing a production plan.'))
        self.preflight_status.setWordWrap(True)
        buttons = QWidget()
        bh = QHBoxLayout(buttons)
        bh.setContentsMargins(0, 0, 0, 0)
        self.preflight_btn = QPushButton(tr('Preflight build plan'))
        self.stage_btn = QPushButton(tr('Stage production plan'))
        self.stage_btn.setEnabled(False)
        bh.addWidget(self.preflight_btn)
        bh.addWidget(self.stage_btn)
        av.addWidget(self.preflight_status)
        av.addWidget(buttons)
        layout.addWidget(action_box)
        build_box = QGroupBox(tr('Build ISO'))
        build_layout = QVBoxLayout(build_box)
        self.build_status = QLabel(tr('BLOCKED — stage a valid production plan before ISO generation.'))
        self.build_status.setWordWrap(True)
        self.build_btn = QPushButton(tr('Build ISO'))
        self.build_btn.setObjectName('buildIsoButton')
        self.build_btn.setMinimumHeight(48)
        self.build_btn.setEnabled(False)
        self.build_btn.clicked.connect(self.start_build)
        build_layout.addWidget(self.build_status)
        build_layout.addWidget(self.build_btn)
        layout.addWidget(build_box)

        acceptance_box = QGroupBox(tr('Cross-distribution acceptance — Part 8'))
        av8 = QVBoxLayout(acceptance_box)
        self.acceptance_status = QLabel(tr('BLOCKED — analyse a source ISO before generating acceptance evidence.'))
        self.acceptance_status.setWordWrap(True)
        self.acceptance_details = QPlainTextEdit()
        self.acceptance_details.setReadOnly(True)
        self.acceptance_details.setMaximumHeight(180)
        a8buttons = QWidget()
        a8h = QHBoxLayout(a8buttons)
        a8h.setContentsMargins(0, 0, 0, 0)
        self.acceptance_refresh_btn = QPushButton(tr('Refresh static acceptance'))
        self.acceptance_export_btn = QPushButton(tr('Export diagnostics…'))
        self.acceptance_export_btn.setEnabled(False)
        a8h.addWidget(self.acceptance_refresh_btn)
        a8h.addWidget(self.acceptance_export_btn)
        av8.addWidget(self.acceptance_status)
        av8.addWidget(self.acceptance_details)
        av8.addWidget(a8buttons)
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
        for widget in (self.output_dir, self.output_name):
            widget.textChanged.connect(self._invalidate_preflight)
        self.compression.currentIndexChanged.connect(self._invalidate_preflight)
        self.verification.currentIndexChanged.connect(self._invalidate_preflight)
        self.preset.currentIndexChanged.connect(self._invalidate_preflight)
        self.diagnostics.toggled.connect(self._invalidate_preflight)

    def set_project(self, project: ProjectState) -> None:
        self.project = project
        current = self.preset.currentData()
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem(tr('Custom production plan'), '')
        for preset in available_production_presets(project):
            self.preset.addItem(preset['label'], preset['id'])
        idx = self.preset.findData(current)
        self.preset.setCurrentIndex(max(0, idx))
        self.preset.blockSignals(False)
        self._invalidate_preflight()
        self.refresh_acceptance()
        self._refresh_build_gate()
        if self.loaded_profile:
            self._refresh_profile_comparison()

    def _production_settings(self) -> dict:
        return {'output_dir': self.output_dir.text().strip(), 'output_name': self.output_name.text().strip(), 'compression': self.compression.currentText(), 'verification_policy': self.verification.currentData() or 'sha256_boot_structure', 'diagnostics_bundle': self.diagnostics.isChecked(), 'preset_id': self.preset.currentData() or ''}

    def save_current_profile(self):
        try:
            profile = create_profile(self.project, self.profile_name.text(), self._production_settings())
        except Exception as exc:
            QMessageBox.warning(self, tr('Profile blocked'), tr(str(exc)))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Save ChromaPress profile'), '', tr('ChromaPress profile (*.chromapress-profile);;JSON (*.json)'))
        if not path:
            return
        if not Path(path).suffix:
            path += '.chromapress-profile'
        try:
            save_profile(profile, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, tr('Profile blocked'), tr(str(exc)))
            return
        self.loaded_profile = profile
        self._refresh_profile_comparison()
        QMessageBox.information(self, tr('ChromaPress'), tr('Profile saved without generation credentials or other secret material.'))

    def load_profile_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Load ChromaPress profile'), '', tr('ChromaPress profile (*.chromapress-profile *.json)'))
        if not path:
            return
        try:
            self.loaded_profile = load_profile(Path(path))
        except Exception as exc:
            self.loaded_profile = None
            self.import_profile_btn.setEnabled(False)
            self.profile_status.setText(tr('BLOCKED — ') + str(exc))
            return
        prod = dict(self.loaded_profile.get('production') or {})
        if prod.get('output_dir'):
            self.output_dir.setText(str(prod['output_dir']))
        if prod.get('output_name'):
            self.output_name.setText(str(prod['output_name']))
        if prod.get('compression') in COMPRESSION_CHOICES:
            self.compression.setCurrentText(str(prod['compression']))
        v = self.verification.findData(prod.get('verification_policy'))
        if v >= 0:
            self.verification.setCurrentIndex(v)
        self.diagnostics.setChecked(bool(prod.get('diagnostics_bundle', True)))
        self._refresh_profile_comparison()

    def _refresh_profile_comparison(self):
        if not self.loaded_profile:
            self.profile_status.setText(tr('No profile loaded.'))
            self.import_profile_btn.setEnabled(False)
            return
        try:
            summary = profile_summary_against_project(self.loaded_profile, self.project)
        except Exception as exc:
            self.profile_status.setText(tr('BLOCKED — ') + str(exc))
            self.import_profile_btn.setEnabled(False)
            return
        src_same = bool(summary['source']['same'])
        ch = summary['changes']
        self.profile_status.setText(tr(f"Source {('MATCH' if src_same else 'DIFF')} • saved changes {ch['left_count']} / current {ch['right_count']} • added {len(ch['added'])} • removed {len(ch['removed'])} • scenario {('MATCH' if summary['same_scenario'] else 'DIFF')}"))
        self.import_profile_btn.setEnabled(src_same)

    def import_loaded_profile(self):
        if not self.loaded_profile:
            return
        try:
            items = profile_change_items(self.loaded_profile, self.project.source.sha256)
            failures = []
            for item in items:
                status, message = test_change(item)
                if status.value in {'FAIL', 'BLOCKED'}:
                    failures.append(f'{item.title}: {message}')
            if failures:
                raise ValueError('Imported plan failed preflight: ' + '; '.join(failures[:5]))
        except Exception as exc:
            QMessageBox.warning(self, tr('Import blocked'), tr(str(exc)))
            return
        answer = QMessageBox.question(self, tr('Import verified plan'), tr('Replace the current staged plan with the verified profile plan? The selected source ISO remains unchanged.'))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.import_requested.emit({'changes': items, 'scenario': str(self.loaded_profile.get('scenario') or '')})

    def refresh_acceptance(self):
        try:
            record = build_static_acceptance(self.project.source)
            ok, message = validate_acceptance_record(record)
            if not ok:
                raise ValueError(message)
        except Exception as exc:
            self._part8_record = None
            self.acceptance_export_btn.setEnabled(False)
            self.acceptance_status.setText(tr('BLOCKED — ') + str(exc))
            self.acceptance_details.clear()
            return
        self._part8_record = record
        self.acceptance_export_btn.setEnabled(bool(record.get('source_sha256')))
        state = str(record.get('verification_state') or '')
        if state == 'VERIFIED':
            self.acceptance_status.setText(tr('VERIFIED — explicit runtime evidence completed every required Part 8 gate.'))
        elif state == 'STATIC_READY_RUNTIME_REQUIRED':
            self.acceptance_status.setText(tr('STATIC READY — runtime acceptance is still required; analysis alone is never VERIFIED.'))
        else:
            self.acceptance_status.setText(tr('STATIC INCOMPLETE — review unknown/static gates before runtime acceptance.'))
        lines = [acceptance_summary(record), '']
        for row in record.get('checks') or []:
            lines.append(f"{row['status']:>16}  {row['label']} — {row['evidence']}")
        self.acceptance_details.setPlainText('\n'.join(lines))

    def export_acceptance_diagnostics(self):
        record = getattr(self, '_part8_record', None)
        if not record:
            self.refresh_acceptance()
            record = getattr(self, '_part8_record', None)
        if not record:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Export Part 8 acceptance diagnostics'), '', tr('JSON (*.json)'))
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            save_diagnostics(record, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, tr('Acceptance export blocked'), tr(str(exc)))
            return
        QMessageBox.information(self, tr('ChromaPress'), tr('Part 8 diagnostics exported. Runtime/boot checks remain manual until explicit evidence is recorded.'))

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, tr('Select output folder'))
        if path:
            self.output_dir.setText(path)

    def browse_hook(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Select reviewed Expert hook'))
        if path:
            self.hook_path.setText(path)

    def add_hook(self):
        try:
            hook = make_expert_hook(Path(self.hook_path.text()), self.hook_phase.currentText(), self.hook_interpreter.currentText(), self.hook_reviewed.isChecked())
            if not hook['human_reviewed']:
                raise ValueError('Explicit human review is required before an Expert hook can be added.')
        except Exception as exc:
            QMessageBox.warning(self, tr('Expert hook blocked'), tr(str(exc)))
            return
        self.expert_hooks.append(hook)
        self.hook_summary.setPlainText('\n'.join((f"{h['phase']} • {h['interpreter']} • {h['sha256'][:12]}… • {h['source_path']}" for h in self.expert_hooks)))
        self.hook_reviewed.setChecked(False)
        self._invalidate_preflight()

    def _invalidate_preflight(self, *_args):
        self._preflight_payload = None
        if hasattr(self, 'stage_btn'):
            self.stage_btn.setEnabled(False)
        if hasattr(self, 'preflight_status'):
            if self.project.source.sha256:
                self.preflight_status.setText(tr('REVIEW REQUIRED — run preflight after checking output, verification policy, preset and Expert hooks.'))
            else:
                self.preflight_status.setText(tr('BLOCKED — analyse a source ISO before preparing a production plan.'))


    @staticmethod
    def _is_production_change(change) -> bool:
        payload = getattr(change, 'payload', None)
        return isinstance(payload, dict) and payload.get('config_type') == 'part7_production_build_plan'

    def _production_change(self):
        for change in reversed(self.project.changes):
            if self._is_production_change(change):
                return change
        return None

    def _build_readiness(self) -> tuple[bool, str, object | None, list]:
        if getattr(self, '_build_thread', None) is not None:
            return False, tr('BUILDING — ISO generation is already running.'), None, []

        production_change_item = self._production_change()
        if production_change_item is None:
            return False, tr('BLOCKED — stage a valid production plan before ISO generation.'), None, []

        payload = dict(production_change_item.payload or {})
        ok, message = validate_build_plan_payload(payload)
        if not ok:
            return False, tr('BLOCKED — ') + str(message), production_change_item, []

        if str(payload.get('source_sha256') or '').lower() != str(self.project.source.sha256 or '').lower():
            return False, tr('BLOCKED — the staged production plan does not match the current source ISO.'), production_change_item, []

        current = self._production_settings()
        compare_keys = ('output_dir', 'output_name', 'compression', 'verification_policy', 'diagnostics_bundle', 'preset_id')
        if any(current.get(key) != payload.get(key) for key in compare_keys):
            return False, tr('BLOCKED — production settings changed after staging. Run preflight and stage the production plan again.'), production_change_item, []

        if payload.get('expert_hooks'):
            return False, tr('BLOCKED — Expert hooks are not enabled in the first verified ISO mutation gate.'), production_change_item, []

        changes = [change for change in self.project.changes if not self._is_production_change(change)]
        if len(changes) != int(payload.get('change_count', -1)):
            return False, tr('BLOCKED — staged changes changed after production preflight. Run preflight and stage again.'), production_change_item, changes

        supported = {'package_repository', 'package_remove', 'package_replace'}
        unsupported = sorted({change.kind.value for change in changes if change.kind.value not in supported})
        if unsupported:
            return False, tr('BLOCKED — first ISO mutation gate supports only APT add/remove/replace. Unsupported: ') + ', '.join(unsupported), production_change_item, changes

        workspace = str(getattr(self.settings, 'workspace_dir', '') or '').strip()
        if not workspace:
            return False, tr('BLOCKED — configure an explicit build workspace in Settings before ISO generation.'), production_change_item, changes

        return True, tr('READY — reviewed production plan can be built. Source ISO remains read-only.'), production_change_item, changes

    def _refresh_build_gate(self):
        if not hasattr(self, 'build_btn'):
            return
        ready, reason, _production, _changes = self._build_readiness()
        self.build_btn.setEnabled(ready)
        self.build_status.setText(reason)
        if ready:
            self.build_btn.setStyleSheet(
                'QPushButton {'
                'background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #16b8d4, stop:0.45 #1186b8, stop:1 #0d6c98);'
                'color: white; border: 1px solid #075f82; border-radius: 7px;'
                'padding: 10px 24px; font-size: 15px; font-weight: 700;'
                '}'
                'QPushButton:hover { border: 1px solid #063f59; }'
                'QPushButton:pressed { padding-top: 11px; padding-bottom: 9px; }'
            )
        else:
            self.build_btn.setStyleSheet(
                'QPushButton { background: #e3e7eb; color: #8a929a; border: 1px solid #c7cdd3; '
                'border-radius: 7px; padding: 10px 24px; font-size: 15px; font-weight: 700; }'
            )

    def start_build(self):
        ready, reason, production_change_item, changes = self._build_readiness()
        if not ready or production_change_item is None:
            self._refresh_build_gate()
            QMessageBox.warning(self, tr('Build blocked'), reason)
            return

        payload = dict(production_change_item.payload or {})
        output_path = str(Path(str(payload.get('output_dir') or '')) / str(payload.get('output_name') or ''))
        answer = QMessageBox.question(
            self,
            tr('Start ISO build?'),
            tr('The reviewed plan will now be applied in the isolated Linux build workspace.\n\n')
            + tr('Source: ') + str(payload.get('source_path') or '') + '\n'
            + tr('Output: ') + output_path + '\n'
            + tr('Changes: ') + str(len(changes)) + '\n\n'
            + tr('The source ISO remains read-only. Runtime/boot verification is still required after generation.'),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        execution_plan = {
            'schema': 'chromapress-build-execution-v1',
            'production': payload,
            'changes': [change.to_dict() for change in changes],
            'workspace_dir': str(getattr(self.settings, 'workspace_dir', '') or ''),
            'reserve_gb': int(getattr(self.settings, 'reserve_gb', 0) or 0),
        }

        self.build_status.setText(tr('BUILDING — applying the reviewed plan and generating a new ISO. The source ISO remains read-only.'))
        self.build_btn.setEnabled(False)
        self.preflight_btn.setEnabled(False)
        self.stage_btn.setEnabled(False)

        self._progress_dialog = _BuildProgressDialog(self)
        self._progress_dialog.show()

        self._build_thread = QThread(self)
        self._build_worker = _BuildWorker(
            str(getattr(self.settings, 'wsl_distro', 'Ubuntu') or 'Ubuntu'),
            execution_plan,
        )
        self._build_worker.moveToThread(self._build_thread)
        self._build_thread.started.connect(self._build_worker.run)
        self._build_worker.progress.connect(self._build_progress)
        self._build_worker.finished.connect(self._build_succeeded)
        self._build_worker.failed.connect(self._build_failed)
        self._build_worker.finished.connect(self._build_thread.quit)
        self._build_worker.failed.connect(self._build_thread.quit)
        self._build_worker.finished.connect(self._build_worker.deleteLater)
        self._build_worker.failed.connect(self._build_worker.deleteLater)
        self._build_thread.finished.connect(self._build_thread_finished)
        self._build_thread.start()

    @Slot(object)
    def _build_progress(self, payload):
        dialog = getattr(self, "_progress_dialog", None)
        if dialog is not None:
            dialog.set_progress(payload)

    @Slot(object)
    def _build_succeeded(self, result: dict):
        dialog = getattr(self, "_progress_dialog", None)
        if dialog is not None:
            dialog.finish_success()
            dialog.accept()
            self._progress_dialog = None
        output = str(result.get('output_path') or '')
        sha256 = str(result.get('output_sha256') or '')
        self.build_status.setText(
            tr('BUILD COMPLETE — new ISO generated and SHA-256 verified.\n')
            + tr('Output: ') + output + '\n'
            + 'SHA-256: ' + sha256 + '\n'
            + tr('Runtime/boot verification is still required before release.')
        )
        QMessageBox.information(
            self,
            tr('Build complete'),
            tr('New ISO generated successfully.\n\n')
            + tr('Output: ') + output + '\nSHA-256: ' + sha256 + '\n\n'
            + tr('The original source ISO was not modified. Runtime/boot verification is still required.')
        )

    @Slot(str)
    def _build_failed(self, message: str):
        dialog = getattr(self, "_progress_dialog", None)
        if dialog is not None:
            dialog.finish_failure()
            dialog.reject()
            self._progress_dialog = None
        self.build_status.setText(tr('BUILD FAILED — no failed output is kept as a release artifact.\n') + message)
        QMessageBox.critical(self, tr('Build failed'), message)

    @Slot()
    def _build_thread_finished(self):
        thread = getattr(self, '_build_thread', None)
        if thread is not None:
            thread.deleteLater()
        self._build_thread = None
        self._build_worker = None
        self.preflight_btn.setEnabled(bool(self.project.source.sha256))
        self._refresh_build_gate()

    def preflight(self):
        try:
            payload = create_build_plan_payload(self.project, output_dir=self.output_dir.text(), output_name=self.output_name.text(), compression=self.compression.currentText(), verification_policy=self.verification.currentData(), diagnostics_bundle=self.diagnostics.isChecked(), preset_id=self.preset.currentData() or '', expert_hooks=self.expert_hooks)
            change = production_change(payload)
            status, message = test_change(change)
            if status.value != 'PASS':
                raise ValueError(message)
        except Exception as exc:
            self._preflight_payload = None
            self.stage_btn.setEnabled(False)
            self.preflight_status.setText(tr('BLOCKED — ') + str(exc))
            return
        self._preflight_payload = payload
        self.stage_btn.setEnabled(True)
        self.preflight_status.setText(tr(f"PASS — source SHA locked • {payload['change_count']} staged changes • output {payload['output_name']} • {len(payload['expert_hooks'])} reviewed hook(s) • verification {payload['verification_policy']}."))

    def stage(self):
        if not self._preflight_payload:
            self.preflight()
            if not self._preflight_payload:
                return
        ok, message = validate_build_plan_payload(self._preflight_payload)
        if not ok:
            self._invalidate_preflight()
            QMessageBox.warning(self, tr('Production plan blocked'), tr(message))
            return
        self.stage_requested.emit(production_change(self._preflight_payload))
        self.stage_btn.setEnabled(False)
        self.preflight_status.setText(tr('STAGED — production build plan added to Changes. Apply/build still requires final human review and target-specific runtime verification.'))
