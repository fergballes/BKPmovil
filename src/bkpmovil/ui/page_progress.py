"""Paso 3: qué se está copiando ahora mismo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..backup import Progress
from ..localfs import human_duration, human_size, miles


def _dato(titulo: str) -> tuple[QWidget, QLabel]:
    """Bloque «número grande + etiqueta»."""
    caja = QWidget()
    layout = QVBoxLayout(caja)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    valor = QLabel("—")
    valor.setObjectName("numeroGrande")
    etiqueta = QLabel(titulo)
    etiqueta.setObjectName("etiquetaNumero")
    layout.addWidget(valor)
    layout.addWidget(etiqueta)
    return caja, valor


class ProgressPage(QWidget):
    """Barra global, carpeta en curso, velocidad y registro."""

    pause_toggled = Signal(bool)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.title = QLabel("Preparando la copia…")
        self.title.setObjectName("titulo")
        layout.addWidget(self.title)

        self.folder_label = QLabel("")
        self.folder_label.setObjectName("subtitulo")
        layout.addWidget(self.folder_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setFormat("%p %")
        layout.addWidget(self.bar)

        self.file_label = QLabel("")
        self.file_label.setObjectName("subtitulo")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.file_label)

        self.folder_bar = QProgressBar()
        self.folder_bar.setObjectName("secundaria")
        self.folder_bar.setRange(0, 100)
        self.folder_bar.setTextVisible(False)
        self.folder_bar.setFixedHeight(8)
        layout.addWidget(self.folder_bar)

        datos = QGridLayout()
        datos.setHorizontalSpacing(30)
        self.valores: dict[str, QLabel] = {}
        for columna, (clave, titulo) in enumerate(
            (
                ("ficheros", "ficheros copiados"),
                ("tamano", "copiado"),
                ("velocidad", "velocidad"),
                ("restante", "tiempo restante"),
            )
        ):
            caja, valor = _dato(titulo)
            self.valores[clave] = valor
            datos.addWidget(caja, 0, columna)
        datos.setColumnStretch(4, 1)
        layout.addLayout(datos)

        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, 1)

        botones = QHBoxLayout()
        self.hint = QLabel("Mantén el móvil desbloqueado y cerca del router.")
        self.hint.setObjectName("subtitulo")
        botones.addWidget(self.hint)
        botones.addStretch(1)
        self.pause_button = QPushButton("Pausar")
        self.pause_button.clicked.connect(self._toggle_pause)
        botones.addWidget(self.pause_button)
        self.cancel_button = QPushButton("Cancelar copia")
        self.cancel_button.setObjectName("peligro")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        botones.addWidget(self.cancel_button)
        layout.addLayout(botones)

        self._paused = False

    # -- API ---------------------------------------------------------------

    def reset(self) -> None:
        self._paused = False
        self.pause_button.setText("Pausar")
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.bar.setValue(0)
        self.folder_bar.setValue(0)
        self.log.clear()
        self.title.setText("Preparando la copia…")
        self.folder_label.setText("")
        self.file_label.setText("")
        for valor in self.valores.values():
            valor.setText("—")

    def append_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def update_progress(self, progress: Progress) -> None:
        self.bar.setValue(progress.percent)
        if progress.folder:
            self.title.setText(f"Copiando  ·  {progress.folder}")
            self.folder_label.setText(
                f"Carpeta {progress.folder}: "
                f"{progress.folder_files_done} de {progress.folder_files_total} ficheros"
            )
        if progress.folder_files_total:
            self.folder_bar.setValue(
                int(progress.folder_files_done * 100 / progress.folder_files_total)
            )
        if progress.file_name:
            self.file_label.setText(progress.file_name)

        self.valores["ficheros"].setText(miles(progress.files_done))
        self.valores["tamano"].setText(human_size(progress.bytes_done))
        self.valores["velocidad"].setText(
            f"{human_size(progress.speed)}/s" if progress.speed > 1000 else "—"
        )
        self.valores["restante"].setText(
            human_duration(progress.eta) if progress.eta > 0 else "—"
        )

    def finishing(self) -> None:
        self.title.setText("Terminando y escribiendo el informe…")
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

    # -- interno -----------------------------------------------------------

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText("Reanudar" if self._paused else "Pausar")
        self.title.setText("Copia en pausa" if self._paused else "Copiando…")
        self.pause_toggled.emit(self._paused)
