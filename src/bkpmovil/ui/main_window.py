"""Ventana principal: los cuatro pasos, en orden."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..adb import Adb, AdbNotFound
from ..backup import BackupResult
from ..config import Config
from .page_connect import ConnectPage
from .page_folders import FoldersPage
from .page_progress import ProgressPage
from .page_report import ReportPage
from .style import paso_html
from .workers import BackupWorker

PASO_CONECTAR, PASO_CARPETAS, PASO_COPIANDO, PASO_RESUMEN = range(4)


def _scrolled(page: QWidget) -> QScrollArea:
    """Envuelve una página para que siga siendo usable en pantallas pequeñas."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(page)
    return area


class MainWindow(QMainWindow):
    def __init__(self, adb: Adb, config: Config) -> None:
        super().__init__()
        self.adb = adb
        self.config = config
        self.serial = ""
        self.model = ""
        self.device_name = ""
        self.worker: BackupWorker | None = None

        self.setWindowTitle("BKPmovil — copia de seguridad del móvil")
        self.resize(1180, 780)
        self.setMinimumSize(880, 560)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        layout.addLayout(self._build_header())
        separador = QFrame()
        separador.setObjectName("separador")
        separador.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separador)

        self.stack = QStackedWidget()
        self.connect_page = ConnectPage(adb, config)
        self.folders_page = FoldersPage(adb, config)
        self.progress_page = ProgressPage()
        self.report_page = ReportPage()
        for page in (self.connect_page, self.folders_page, self.progress_page, self.report_page):
            self.stack.addWidget(_scrolled(page))
        layout.addWidget(self.stack, 1)

        layout.addLayout(self._build_footer())
        self.setCentralWidget(central)

        self.connect_page.connected.connect(self._on_connected)
        self.folders_page.start_backup.connect(self._start_backup)
        self.progress_page.pause_toggled.connect(self._on_pause)
        self.progress_page.cancelled.connect(self._on_cancel)
        self.report_page.new_backup.connect(lambda: self._go(PASO_CARPETAS))

        self._go(PASO_CONECTAR)

    # -- construcción ------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        titulo = QLabel("BKPmovil")
        titulo.setObjectName("titulo")
        row.addWidget(titulo)
        row.addSpacing(18)
        self.steps = QLabel()
        self.steps.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self.steps)
        row.addStretch(1)
        self.device_label = QLabel("Sin conectar")
        self.device_label.setObjectName("subtitulo")
        row.addWidget(self.device_label)
        return row

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.back_button = QPushButton("‹ Atrás")
        self.back_button.clicked.connect(self._back)
        row.addWidget(self.back_button)
        row.addStretch(1)
        self.help_label = QLabel("")
        self.help_label.setObjectName("subtitulo")
        row.addWidget(self.help_label)
        return row

    # -- navegación --------------------------------------------------------

    def _go(self, step: int) -> None:
        self.stack.setCurrentIndex(step)
        self.steps.setText(paso_html(step))
        self.back_button.setVisible(step in (PASO_CARPETAS,))
        ayudas = {
            PASO_CONECTAR: "¿Primera vez? Sigue la guía de la izquierda; se hace una sola vez.",
            PASO_CARPETAS: "Marca lo que quieras copiar y elige dónde guardarlo.",
            PASO_COPIANDO: "Puedes pausar o cancelar: lo ya copiado no se pierde.",
            PASO_RESUMEN: "La próxima copia solo traerá lo nuevo, así que será mucho más rápida.",
        }
        self.help_label.setText(ayudas.get(step, ""))

    def _back(self) -> None:
        if self.stack.currentIndex() == PASO_CARPETAS:
            self._go(PASO_CONECTAR)

    # -- flujo -------------------------------------------------------------

    def _on_connected(self, serial: str, info) -> None:
        self.serial = serial
        self.model = info.model
        self.device_name = info.display_name
        self.device_label.setText(f"● {info.display_name}")
        self.folders_page.set_device(serial, info.model)
        self._go(PASO_CARPETAS)
        self.folders_page.analyze()

    def _start_backup(self, sources: list, dest: Path, full: bool) -> None:
        if not sources:
            return
        self.progress_page.reset()
        self._go(PASO_COPIANDO)
        worker = BackupWorker(
            self.adb,
            self.serial,
            dest,
            sources,
            self.device_name,
            self.model,
            self.config,
            full=full,
            parent=self,
        )
        worker.progress.connect(self.progress_page.update_progress)
        worker.log.connect(self.progress_page.append_log)
        worker.ok.connect(self._backup_done)
        worker.failed.connect(self._backup_failed)
        self.worker = worker
        worker.start()

    def _on_pause(self, paused: bool) -> None:
        if not self.worker:
            return
        self.worker.pause() if paused else self.worker.resume()

    def _on_cancel(self) -> None:
        if not self.worker:
            return
        answer = QMessageBox.question(
            self,
            "Cancelar la copia",
            "¿Seguro que quieres parar?\n\nTodo lo copiado hasta ahora se conserva y "
            "la próxima vez se seguirá desde donde lo dejaste.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.progress_page.finishing()
            self.worker.cancel()

    def _backup_done(self, result: BackupResult) -> None:
        self.worker = None
        self.report_page.show_result(result)
        self._go(PASO_RESUMEN)

    def _backup_failed(self, message: str) -> None:
        self.worker = None
        QMessageBox.critical(self, "La copia ha fallado", message)
        self._go(PASO_CARPETAS)

    # -- cierre ------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Copia en marcha",
                "Hay una copia en curso. ¿Salir de todas formas?\n"
                "Lo copiado hasta ahora se conserva.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(8000)
        self.config.save()
        event.accept()


def show_adb_missing(error: AdbNotFound) -> None:
    QMessageBox.critical(None, "Falta adb", str(error))
