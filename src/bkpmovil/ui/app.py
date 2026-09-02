"""Arranque de la aplicación gráfica."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ..adb import Adb, AdbNotFound
from ..config import Config
from .main_window import MainWindow, show_adb_missing
from .style import STYLESHEET


def _assets_dir() -> Path:
    """Carpeta de recursos, tanto en desarrollo como empaquetada."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "assets"
    return Path(__file__).resolve().parent.parent.parent.parent / "assets"


def app_icon() -> QIcon:
    """Icono de la app; si falta el fichero, se dibuja uno sencillo."""
    for name in ("icono.png", "icono.svg", "icono.ico"):
        candidate = _assets_dir() / name
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon

    pixmap = QPixmap(QSize(256, 256))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.GlobalColor.darkBlue)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(58, 24, 140, 208, 22, 22)
    painter.setBrush(Qt.GlobalColor.white)
    painter.drawRoundedRect(74, 48, 108, 150, 8, 8)
    painter.end()
    return QIcon(pixmap)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BKPmovil")
    app.setApplicationDisplayName("BKPmovil")
    app.setOrganizationName("BKPmovil")
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    try:
        adb = Adb()
    except AdbNotFound as exc:
        show_adb_missing(exc)
        return 2

    window = MainWindow(adb, Config.load())
    window.show()
    return app.exec()
