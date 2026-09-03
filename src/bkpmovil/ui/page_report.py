"""Paso 4: resumen final de la copia."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..backup import BackupResult
from ..localfs import human_duration, human_size, miles, open_in_file_manager
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
        self.valores["ficheros"].setText(miles(result.total_copied))
        self.valores["tamano"].setText(human_size(result.total_bytes))
        self.valores["omitidos"].setText(miles(result.total_skipped))
        self.valores["duracion"].setText(human_duration(result.duration))

        self.table.setRowCount(len(result.folders))
        for row, folder in enumerate(result.folders):
            celdas = [
                folder.dest_name,
                miles(folder.copied),
                human_size(folder.bytes_copied),
                miles(folder.skipped),
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
        if not self.result:
            return
        destino = Path(self.result.dest)
        if not open_in_file_manager(destino):
            QMessageBox.information(
                self,
                "No se ha podido abrir la carpeta",
                "No se ha podido abrir el explorador de archivos. La copia está en:\n\n"
                f"{destino}",
            )

    def _open_report(self) -> None:
        """Enseña el informe en una ventana propia.

        No se delega en el sistema: el programa asociado a los .txt puede ser
        un editor de terminal, que desde una aplicación de ventanas arranca sin
        terminal a la que engancharse y no se ve nada. Además el informe lleva
        columnas alineadas y necesita fuente monoespaciada.
        """
        if not self.result:
            return
        informe = Path(self.result.dest) / RESUMEN
        try:
            texto = informe.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "No se ha podido leer el informe",
                f"No se ha podido leer {informe}.\n\n{exc}",
            )
            return

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"{RESUMEN} — {informe.parent.name}")
        dialogo.resize(720, 560)
        caja = QVBoxLayout(dialogo)

        ruta = QLabel(str(informe))
        ruta.setObjectName("subtitulo")
        ruta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        caja.addWidget(ruta)

        visor = QPlainTextEdit(texto)
        visor.setObjectName("informe")
        visor.setReadOnly(True)
        visor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        caja.addWidget(visor, 1)

        botones = QDialogButtonBox()
        copiar = botones.addButton("Copiar el texto", QDialogButtonBox.ButtonRole.ActionRole)
        copiar.clicked.connect(lambda: self._copy_to_clipboard(texto, copiar))
        cerrar = botones.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        cerrar.setObjectName("primario")
        botones.rejected.connect(dialogo.reject)
        caja.addWidget(botones)

        dialogo.exec()

    @staticmethod
    def _copy_to_clipboard(texto: str, boton: QPushButton) -> None:
        aplicacion = QApplication.instance()
        if aplicacion is None:
            return
        aplicacion.clipboard().setText(texto)
        boton.setText("Copiado")
        QTimer.singleShot(1500, lambda: boton.setText("Copiar el texto"))
