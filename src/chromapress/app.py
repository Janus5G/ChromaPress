from __future__ import annotations

import sys
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from .gui.main_window import MainWindow
from .gui.about_dialog import chromapress_icon


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JanusRokkjaer.ChromaPress")
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()
    QCoreApplication.setOrganizationName("ChromaPress")
    QCoreApplication.setApplicationName("ChromaPress")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(chromapress_icon())
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
