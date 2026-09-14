"""PyInstaller entry point for the Windows ChromaPress executable.

Keep the executable bootstrap outside the chromapress package so PyInstaller
imports chromapress.app with normal package context. This preserves relative
imports inside the package (for example .gui.main_window).
"""
from chromapress.app import main


if __name__ == "__main__":
    raise SystemExit(main())
