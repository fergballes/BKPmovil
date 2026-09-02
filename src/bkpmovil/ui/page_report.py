"""Paso 4: resumen final de la copia."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..backup import BackupResult
from ..localfs import human_duration, human_size, open_in_file_manager
from ..report import RESUMEN


class ReportPage(QWidget):
    """Números grandes, tabla por carpeta y accesos a la copia."""

    new_backup = Signal()

    COLUMNAS = ["Carpeta", "Ficheros copiados", "Tamaño", "Ya estaban", "Fallos", "Origen"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result: BackupResult | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.title = QLabel("Copia terminada")
        self.title.setObjectName("titulo")
        layout.addWidget(self.title)

        self.subtitle = QLabel("")
        self.subtitle.setObjectName("subtitulo")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        self.numbers = QGridLayout()
        self.numbers.setHorizontalSpacing(36)
        self.valores: dict[str, QLabel] = {}
        for columna, (clave, titulo) in enumerate(
            (
                ("carpetas", "carpetas copiadas"),
                ("ficheros", "ficheros copiados"),
                ("tamano", "tamaño total"),
                ("omitidos", "ya estaban"),
                ("duracion", "ha tardado"),
            )
        ):
            caja = QWidget()
            interior = QVBoxLayout(caja)
            interior.setContentsMargins(0, 0, 0, 0)
            interior.setSpacing(0)
            valor = QLabel("—")
            valor.setObjectName("numeroGrande")
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("etiquetaNumero")
            interior.addWidget(valor)
            interior.addWidget(etiqueta)
            self.valores[clave] = valor
            self.numbers.addWidget(caja, 0, columna)
        self.numbers.setColumnStretch(5, 1)
        layout.addLayout(self.numbers)

        self.table = QTableWidget(0, len(self.COLUMNAS))
        self.table.setHorizontalHeaderLabels(self.COLUMNAS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.warning = QLabel(
            "Recuerda: el historial de chats de WhatsApp no se puede copiar por WiFi; "
            "sí se han copiado sus fotos y vídeos."
        )
        self.warning.setObjectName("aviso")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        botones = QHBoxLayout()
        self.open_button = QPushButton("Abrir la carpeta de la copia")
        self.open_button.setObjectName("primario")
        self.open_button.clicked.connect(self._open_folder)
        botones.addWidget(self.open_button)
        self.report_button = QPushButton("Ver el informe")
        self.report_button.clicked.connect(self._open_report)
        botones.addWidget(self.report_button)
        botones.addStretch(1)
        self.again_button = QPushButton("Hacer otra copia")
        self.again_button.clicked.connect(self.new_backup.emit)
        botones.addWidget(self.again_button)
        layout.addLayout(botones)

    # -- API ---------------------------------------------------------------

    def show_result(self, result: BackupResult) -> None:
        self.result = result
        cancelada = result.cancelled
        self.title.setText("Copia cancelada" if cancelada else "Copia terminada")

        detalle = (
            f"Se ha guardado en:  {result.dest}\n"
            f"Móvil: {result.device or result.serial}"
        )
        if cancelada:
            detalle += "\nLa cancelaste a medias, pero todo lo que ya se había copiado es válido."
        if result.total_failed:
            detalle += (
                f"\n{result.total_failed} ficheros no se han podido copiar; "
                f"están listados al final de {RESUMEN}."
            )
        self.subtitle.setText(detalle)

        self.valores["carpetas"].setText(str(len(result.folders_with_content)))
        self.valores["ficheros"].setText(f"{result.total_copied:,}".replace(",", "."))
        self.valores["tamano"].setText(human_size(result.total_bytes))
        self.valores["omitidos"].setText(f"{result.total_skipped:,}".replace(",", "."))
        self.valores["duracion"].setText(human_duration(result.duration))

        self.table.setRowCount(len(result.folders))
        for row, folder in enumerate(result.folders):
            celdas = [
                folder.dest_name,
                f"{folder.copied:,}".replace(",", "."),
                human_size(folder.bytes_copied),
                f"{folder.skipped:,}".replace(",", "."),
                str(folder.failed),
                folder.root,
            ]
            for column, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if 1 <= column <= 4:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)

    # -- interno -----------------------------------------------------------

    def _open_folder(self) -> None:
        if self.result:
            open_in_file_manager(Path(self.result.dest))

    def _open_report(self) -> None:
        if self.result:
            open_in_file_manager(Path(self.result.dest) / RESUMEN)
