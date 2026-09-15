from __future__ import annotations
from chromapress.i18n import tr
from collections import Counter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTreeWidget, QTreeWidgetItem, QPushButton
from chromapress.models import ChangeKind, ProjectState
from chromapress.scenarios import scenario_by_id
_ADD_KINDS = {ChangeKind.PACKAGE_REPOSITORY, ChangeKind.DIRECT_URL, ChangeKind.LOCAL_PACKAGE, ChangeKind.GIT, ChangeKind.AI_APP}

class ProjectPlanPage(QWidget):
    """Human-facing live/final view of what the image is becoming.

    This is deliberately driven by the declarative project plan. It never mutates
    the source image and is designed to accept Components/System/Desktop/etc.
    sections later without changing the user-facing review model.
    """

    def __init__(self, final_review: bool=False, parent=None):
        super().__init__(parent)
        self.final_review = final_review
        layout = QVBoxLayout(self)
        title = QLabel(tr('Final build review' if final_review else 'Current image plan'))
        title.setObjectName('pageTitle')
        subtitle = QLabel(tr('Review the complete image plan before generation starts. Nothing is applied until the final build step.') if final_review else tr('A live overview of the selected source and every staged change. This is the current intended state of the finished ISO.'))
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        summary_box = QGroupBox(tr('Image summary'))
        form = QFormLayout(summary_box)
        self.source_value = QLabel(tr('No source selected'))
        self.scenario_value = QLabel(tr('Not selected'))
        self.apps_value = QLabel(tr('Application catalogue not loaded'))
        self.change_value = QLabel(tr('No staged changes'))
        for label in (self.source_value, self.scenario_value, self.apps_value, self.change_value):
            label.setWordWrap(True)
        form.addRow(tr('Source:'), self.source_value)
        form.addRow(tr('System use:'), self.scenario_value)
        form.addRow(tr('Applications:'), self.apps_value)
        form.addRow(tr('Plan:'), self.change_value)
        layout.addWidget(summary_box)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr('Area / item'), tr('Planned state'), tr('Validation')])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 380)
        self.tree.setColumnWidth(1, 620)
        self.tree.setColumnWidth(2, 140)
        layout.addWidget(self.tree, 1)
        if final_review:
            self.final_status = QLabel(tr('Generation remains disabled in this alpha. When the builder gate is connected, this page will be the mandatory final review before any ISO mutation starts.'))
            self.final_status.setWordWrap(True)
            self.start_btn = QPushButton(tr('Start generation'))
            self.start_btn.setEnabled(False)
            self.start_btn.setToolTip(tr('Enabled only after the Build & Verify engine and its final safety gates are connected.'))
            layout.addWidget(self.final_status)
            layout.addWidget(self.start_btn)

    @staticmethod
    def _bold(item: QTreeWidgetItem, column: int=0) -> None:
        font = item.font(column)
        font.setBold(True)
        item.setFont(column, font)

    def update_plan(self, project: ProjectState, app_summary: dict | None=None) -> None:
        app_summary = app_summary or {}
        source = project.source
        if source.path:
            identity = ' '.join((x for x in (source.distribution, source.version, source.architecture) if x)).strip()
            self.source_value.setText(tr(f"{identity or 'Linux image'} — {source.path}"))
        else:
            self.source_value.setText(tr('No source selected'))
        if project.scenario:
            self.scenario_value.setText(tr(scenario_by_id(project.scenario).label))
        else:
            self.scenario_value.setText(tr('Not selected'))
        total_apps = app_summary.get('total')
        if isinstance(total_apps, int):
            mode = str(app_summary.get('read_method', '')).strip()
            suffix = f' • {mode}' if mode else ''
            self.apps_value.setText(tr(f'{total_apps} user-facing applications detected in the base image{suffix}'))
        else:
            self.apps_value.setText(tr('Application catalogue not loaded'))
        additions = [c for c in project.changes if c.kind in _ADD_KINDS]
        removals = [c for c in project.changes if c.kind == ChangeKind.PACKAGE_REMOVE]
        others = [c for c in project.changes if c not in additions and c not in removals]
        if project.changes:
            self.change_value.setText(tr(f'{len(project.changes)} staged change(s): +{len(additions)} additions, -{len(removals)} removals, {len(others)} other'))
        else:
            self.change_value.setText(tr('No staged changes — the selected source is preserved as-is'))
        self.tree.clear()
        source_item = QTreeWidgetItem(self.tree, [tr('Source image'), self.source_value.text(), 'READ-ONLY' if source.path else 'BLOCKED'])
        self._bold(source_item)
        scenario_item = QTreeWidgetItem(self.tree, [tr('System scenario'), self.scenario_value.text(), 'SET' if project.scenario else 'NOT SET'])
        self._bold(scenario_item)
        apps_root = QTreeWidgetItem(self.tree, [tr('Applications'), self.apps_value.text(), 'DETECTED' if isinstance(total_apps, int) else 'PENDING'])
        self._bold(apps_root)
        section_counts = app_summary.get('sections') or {}
        if isinstance(section_counts, dict):
            for name, count in section_counts.items():
                QTreeWidgetItem(apps_root, [str(name), tr(f'{count} detected'), tr('BASE IMAGE')])
        if removals:
            remove_root = QTreeWidgetItem(apps_root, [tr(f'Remove ({len(removals)})'), tr('Applications/packages staged for removal'), tr('STAGED')])
            self._bold(remove_root)
            for change in removals:
                QTreeWidgetItem(remove_root, [change.title, change.detail, change.status.value])
        if additions:
            add_root = QTreeWidgetItem(apps_root, [tr(f'Add ({len(additions)})'), tr('New applications/sources staged for inclusion'), tr('STAGED')])
            self._bold(add_root)
            for change in additions:
                QTreeWidgetItem(add_root, [change.title, change.detail, change.status.value])
        if others:
            other_root = QTreeWidgetItem(self.tree, [tr(f'Other changes ({len(others)})'), tr('Configuration/content changes'), tr('STAGED')])
            self._bold(other_root)
            by_kind = Counter((c.kind.value for c in others))
            for kind, count in sorted(by_kind.items()):
                kind_item = QTreeWidgetItem(other_root, [kind.replace('_', ' ').title(), tr(f'{count} change(s)'), tr('STAGED')])
                for change in [c for c in others if c.kind.value == kind]:
                    QTreeWidgetItem(kind_item, [change.title, change.detail, change.status.value])
        self.tree.expandItem(source_item)
        self.tree.expandItem(scenario_item)
        self.tree.expandItem(apps_root)
        if self.final_review:
            if not source.path:
                self.final_status.setText(tr('BLOCKED — choose and analyse a source image before generation can ever be enabled.'))
            elif not project.scenario:
                self.final_status.setText(tr('REVIEW REQUIRED — select the intended system use before final generation.'))
            else:
                self.final_status.setText(tr('Final review available. Generation remains disabled in this alpha until the real Build & Verify engine is connected.'))
