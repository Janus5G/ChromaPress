from __future__ import annotations

from pathlib import Path
from threading import Event
from uuid import uuid4

from PySide6.QtCore import QThread, Signal, QObject, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QComboBox, QGroupBox, QProgressBar, QMessageBox
)

from chromapress.services.downloads import (
    OFFICIAL_SOURCES,
    DownloadCancelled,
    download_official,
)
from chromapress.services.wsl import WslBridge


class Worker(QObject):
    """Run one non-GUI task in a QThread and marshal results back to Qt."""

    finished = Signal(str, object)
    failed = Signal(str, str)
    cancelled = Signal(str)
    progress = Signal(str, int)
    status = Signal(str, str)

    def __init__(self, task_id: str, fn, cancel_event: Event):
        super().__init__()
        self.task_id = task_id
        self.fn = fn
        self.cancel_event = cancel_event

    @Slot()
    def run(self):
        try:
            def report_progress(value: int):
                self.progress.emit(self.task_id, int(value))

            def report_status(text: str):
                self.status.emit(self.task_id, text)

            result = self.fn(report_progress, report_status, self.cancel_event)
            self.finished.emit(self.task_id, result)
        except DownloadCancelled:
            self.cancelled.emit(self.task_id)
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc))


class SourcePage(QWidget):
    source_analyzed = Signal(dict)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._tasks: dict[str, tuple[QThread, Worker, object, Event, bool]] = {}
        self._active_download_task: str | None = None

        layout = QVBoxLayout(self)
        title = QLabel("Source")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Start from an official Linux release or open an existing/custom ISO directly. "
            "Existing ISO files are never uploaded or copied just to analyze them."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        official = QGroupBox("Create from official distribution (new source)")
        o = QVBoxLayout(official)
        row = QHBoxLayout()
        self.official_combo = QComboBox()
        for source in OFFICIAL_SOURCES:
            self.official_combo.addItem(source.label, source.id)

        self.download_btn = QPushButton("Download, verify & analyze")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)

        row.addWidget(self.official_combo, 1)
        row.addWidget(self.download_btn)
        row.addWidget(self.cancel_btn)
        o.addLayout(row)

        self.status_label = QLabel("Ready")
        o.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        o.addWidget(self.progress)
        layout.addWidget(official)

        existing = QGroupBox("Open existing ISO")
        e = QHBoxLayout(existing)
        self.path_label = QLabel("No ISO selected")
        self.path_label.setWordWrap(True)
        self.open_btn = QPushButton("Open ISO…")
        e.addWidget(self.path_label, 1)
        e.addWidget(self.open_btn)
        layout.addWidget(existing)

        self.current_source_label = QLabel("Current source: none")
        self.current_source_label.setWordWrap(True)
        layout.addWidget(self.current_source_label)
        layout.addStretch(1)

        self.open_btn.clicked.connect(self.open_existing)
        self.download_btn.clicked.connect(self.download_official)
        self.cancel_btn.clicked.connect(self.cancel_download)

    def _set_busy(self, busy: bool) -> None:
        self.open_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.official_combo.setEnabled(not busy)

    def _run(self, fn, finished, *, cancellable: bool = False) -> str:
        task_id = uuid4().hex
        thread = QThread(self)
        cancel_event = Event()
        worker = Worker(task_id, fn, cancel_event)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.progress.connect(self._on_worker_progress)
        worker.status.connect(self._on_worker_status)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._tasks[task_id] = (thread, worker, finished, cancel_event, cancellable)
        if cancellable:
            self._active_download_task = task_id
            self.cancel_btn.setEnabled(True)
        self._set_busy(True)
        thread.start()
        return task_id

    @Slot(str, int)
    def _on_worker_progress(self, task_id: str, value: int) -> None:
        if task_id in self._tasks:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, value)))

    @Slot(str, str)
    def _on_worker_status(self, task_id: str, text: str) -> None:
        if task_id not in self._tasks:
            return
        self.status_label.setText(text)
        if text.startswith("Verifying"):
            self.progress.setRange(0, 0)

    @Slot(str, object)
    def _on_worker_finished(self, task_id: str, result) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        callback = task[2]
        callback(result)

    @Slot(str, str)
    def _on_worker_failed(self, task_id: str, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("FAILED")
        QMessageBox.critical(self, "ChromaPress", message)

    @Slot(str)
    def _on_worker_cancelled(self, task_id: str) -> None:
        self.progress.setRange(0, 100)
        self.status_label.setText("Cancelled — partial download kept for resume")
        self.cancel_btn.setEnabled(False)

    @Slot()
    def _on_thread_finished(self) -> None:
        finished_thread = self.sender()
        remove_id = None
        for task_id, (thread, _worker, _callback, _cancel_event, _cancellable) in self._tasks.items():
            if thread is finished_thread:
                remove_id = task_id
                break

        if remove_id is not None:
            self._tasks.pop(remove_id, None)
            if self._active_download_task == remove_id:
                self._active_download_task = None
                self.cancel_btn.setEnabled(False)

        if not self._tasks:
            self._set_busy(False)

    def cancel_download(self) -> None:
        task_id = self._active_download_task
        if not task_id:
            return
        task = self._tasks.get(task_id)
        if task is None:
            return
        task[3].set()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling…")

    def open_existing(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Linux ISO", "", "Linux ISO (*.iso);;All files (*)"
        )
        if not path:
            return
        self.path_label.setText(path)
        self._analyze(path, kind="existing")

    def _analyze(self, path: str, kind: str):
        self.status_label.setText("Analyzing ISO…")
        self.progress.setRange(0, 0)
        bridge = WslBridge(self.settings.wsl_distro)

        def work(_progress, _status, _cancel_event):
            data = bridge.analyze_iso(path)
            data["source_kind"] = kind
            return data

        def done(data):
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.status_label.setText("READY")
            distro = data.get("distribution") or "Unknown Linux"
            version = data.get("version") or ""
            arch = data.get("architecture") or ""
            summary = " ".join(x for x in (distro, version, arch) if x)
            self.current_source_label.setText(f"Current source: {summary}")
            self.source_analyzed.emit(data)

        self._run(work, done)

    def download_official(self):
        if not self.settings.cache_dir.strip():
            QMessageBox.warning(
                self,
                "Storage location required",
                "Choose an explicit ISO/download cache in Settings before downloading a multi-GB distribution image.",
            )
            return

        source_id = self.official_combo.currentData()
        source = next(x for x in OFFICIAL_SOURCES if x.id == source_id)
        cache = Path(self.settings.cache_dir)

        # Give immediate feedback before any DNS/TLS/network work begins.
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText(f"Starting direct download: {source.label}")

        def work(progress_signal, status_signal, cancel_event):
            def progress(done, total):
                progress_signal(int(done * 100 / total) if total else 0)

            path = download_official(
                source,
                cache,
                progress=progress,
                status=status_signal,
                cancelled=cancel_event.is_set,
                reserve_gb=self.settings.reserve_gb,
            )
            return str(path)

        def downloaded(path):
            self.path_label.setText(path)
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Verified — analyzing ISO…")
            self._analyze(path, kind="official")

        self._run(work, downloaded, cancellable=True)
