"""Paso 2: elegir carpetas del móvil y destino en el ordenador."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..adb import Adb
from ..config import Config
from ..discovery import dir_exists, list_files
from ..index import BackupIndex
from ..localfs import free_space, human_size
from ..paths import FILTER_SETS, ResolvedSource
from .workers import DiscoverWorker

FILTROS = [
    ("Todo lo que haya", "todo"),
    ("Solo fotos y vídeos", "media"),
    ("Fotos, vídeos, audios y documentos", "media_audio_docs"),
]


class AddFolderDialog(QDialog):
    """Añadir a mano una carpeta del móvil que no se haya detectado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Añadir una carpeta del móvil")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Escribe la ruta tal y como está en el móvil. Casi siempre empieza\n"
                "por /sdcard/  ·  por ejemplo:  /sdcard/Notas de voz"
            )
        )
        form = QFormLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/sdcard/MiCarpeta")
        form.addRow("Ruta en el móvil:", self.path_edit)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("(se usa el nombre de la carpeta)")
        form.addRow("Nombre en la copia:", self.name_edit)
        self.filter_combo = QComboBox()
        for label, key in FILTROS:
            self.filter_combo.addItem(label, key)
        form.addRow("Qué copiar:", self.filter_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        path = self.path_edit.text().strip().rstrip("/")
        return {
            "root": path,
            "label": self.name_edit.text().strip() or path,
            "dest_name": self.name_edit.text().strip() or Path(path).name,
            "filter_key": self.filter_combo.currentData(),
            "enabled": True,
        }


class FoldersPage(QWidget):
    """Tabla de carpetas detectadas, con su tamaño y lo que falta por copiar."""

    start_backup = Signal(list, Path, bool)  # fuentes, destino, copia completa

    COLUMNAS = ["Carpeta", "Nuevos", "Tamaño nuevo", "Total en el móvil", "Ruta en el móvil"]

    def __init__(self, adb: Adb, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.adb = adb
        self.config = config
        self.serial = ""
        self.model = ""
        self.sources: list[ResolvedSource] = []
        self.pending: dict[str, tuple[int, int]] = {}
        self._worker: DiscoverWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addLayout(self._build_dest_row())
        layout.addLayout(self._build_toolbar())
        self.status = QLabel("Pulsa «Analizar el móvil» para ver qué hay dentro.")
        self.status.setObjectName("subtitulo")
        layout.addWidget(self.status)
        self.table = self._build_table()
        layout.addWidget(self.table, 1)
        layout.addWidget(self._build_footer())

    # -- construcción ------------------------------------------------------

    def _build_dest_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Guardar la copia en:"))
        self.dest_edit = QLineEdit(self.config.dest)
        self.dest_edit.setReadOnly(True)
        row.addWidget(self.dest_edit, 1)
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._choose_dest)
        row.addWidget(browse)
        return row

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.analyze_button = QPushButton("Analizar el móvil")
        self.analyze_button.setObjectName("primario")
        self.analyze_button.clicked.connect(self.analyze)
        row.addWidget(self.analyze_button)

        for text, slot in (
            ("Marcar todas", lambda: self._set_all(True)),
            ("Desmarcar todas", lambda: self._set_all(False)),
            ("Añadir carpeta…", self._add_custom),
            ("Quitar carpeta", self._remove_custom),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)

        row.addStretch(1)
        return row

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(self.COLUMNAS))
        table.setHorizontalHeaderLabels(self.COLUMNAS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.itemChanged.connect(self._on_item_changed)
        return table

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        izquierda = QVBoxLayout()
        izquierda.setSpacing(4)
        opciones = QHBoxLayout()
        opciones.setSpacing(18)
        self.full_check = QCheckBox("Copia completa")
        self.full_check.setToolTip(
            "Copia también los ficheros que ya se copiaron en veces anteriores.\n"
            "Normalmente no hace falta: sin marcarla, solo se trae lo nuevo."
        )
        self.full_check.stateChanged.connect(lambda: self._refresh_summary())
        opciones.addWidget(self.full_check)
        self.verify_check = QCheckBox("Comprobar fichero a fichero")
        self.verify_check.setToolTip(
            "Compara el contenido de cada fichero con el del móvil (sha1).\n"
            "Es más seguro, pero la copia tarda bastante más."
        )
        self.verify_check.setChecked(self.config.verify_hash)
        opciones.addWidget(self.verify_check)
        opciones.addStretch(1)
        izquierda.addLayout(opciones)

        self.summary = QLabel("")
        self.summary.setObjectName("subtitulo")
        izquierda.addWidget(self.summary)
        row.addLayout(izquierda, 1)

        self.go_button = QPushButton("HACER COPIA DE SEGURIDAD")
        self.go_button.setObjectName("accion")
        self.go_button.setEnabled(False)
        self.go_button.setMinimumWidth(300)
        self.go_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.go_button.clicked.connect(self._go)
        row.addWidget(self.go_button, 0, Qt.AlignmentFlag.AlignRight)
        return footer

    # -- dispositivo -------------------------------------------------------

    def set_device(self, serial: str, model: str) -> None:
        self.serial = serial
        self.model = model
        self.sources = []
        self.table.setRowCount(0)
        self.go_button.setEnabled(False)
        self.status.setText("Pulsa «Analizar el móvil» para ver qué hay dentro.")

    # -- análisis ----------------------------------------------------------

    def analyze(self) -> None:
        if not self.serial:
            QMessageBox.information(self, "Falta conectar", "Conecta antes con el móvil.")
            return
        self.analyze_button.setEnabled(False)
        self.go_button.setEnabled(False)
        self.status.setText("Analizando el móvil… puede tardar un minuto.")
        worker = DiscoverWorker(self.adb, self.serial, self.config.custom_sources, self)
        worker.progress.connect(self.status.setText)
        worker.ok.connect(self._analyzed)
        worker.failed.connect(self._failed)
        worker.finished.connect(lambda: self.analyze_button.setEnabled(True))
        self._worker = worker
        worker.start()

    def _analyzed(self, _root: str, sources: list) -> None:
        for source in sources:
            if self.config.is_disabled(source.key):
                source.enabled = False
        self.sources = sources
        self._compute_pending()
        self._fill_table()
        total = sum(s.file_count for s in sources)
        self.status.setText(f"{len(sources)} carpetas encontradas · {total:,} ficheros".replace(",", "."))

    def _compute_pending(self) -> None:
        index = BackupIndex.for_device(self.serial, self.model)
        self.pending = {}
        for source in self.sources:
            nuevos = [f for f in source.files if not index.is_copied(f)]
            self.pending[source.key] = (
                len(nuevos),
                sum(f.size for f in nuevos if f.size > 0),
            )

    def _failed(self, message: str) -> None:
        self.status.setText("No se ha podido analizar el móvil.")
        QMessageBox.warning(self, "Error al analizar", message)

    # -- tabla -------------------------------------------------------------

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.sources))
        for row, source in enumerate(self.sources):
            nuevos, bytes_nuevos = self.pending.get(source.key, (source.file_count, source.total_bytes))
            name = QTableWidgetItem(f" {source.dest_name}")
            name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            name.setCheckState(
                Qt.CheckState.Checked if source.enabled else Qt.CheckState.Unchecked
            )
            name.setToolTip(source.label)
            name.setData(Qt.ItemDataRole.UserRole, source.key)
            self.table.setItem(row, 0, name)

            for column, text in (
                (1, f"{nuevos:,}".replace(",", ".")),
                (2, human_size(bytes_nuevos)),
                (3, f"{source.file_count:,}".replace(",", ".") + f"  ·  {human_size(source.total_bytes)}"),
                (4, source.root),
            ):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self._refresh_summary()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.sources):
            enabled = item.checkState() == Qt.CheckState.Checked
            self.sources[row].enabled = enabled
            self.config.set_enabled(self.sources[row].key, enabled)
        self._refresh_summary()

    def _set_all(self, enabled: bool) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
            )
            self.sources[row].enabled = enabled
            self.config.set_enabled(self.sources[row].key, enabled)
        self.table.blockSignals(False)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        selected = [s for s in self.sources if s.enabled]
        if self.full_check.isChecked():
            ficheros = sum(s.file_count for s in selected)
            octetos = sum(s.total_bytes for s in selected)
        else:
            ficheros = sum(self.pending.get(s.key, (0, 0))[0] for s in selected)
            octetos = sum(self.pending.get(s.key, (0, 0))[1] for s in selected)

        libre = free_space(Path(self.dest_edit.text() or Path.home()))
        aviso = ""
        if libre and octetos > libre:
            aviso = f"  ⚠ No cabe: quedan {human_size(libre)} libres"
        self.summary.setText(
            f"{len(selected)} carpetas · {ficheros:,} ficheros · {human_size(octetos)}{aviso}".replace(
                ",", "."
            )
        )
        self.go_button.setEnabled(bool(selected) and ficheros > 0)
        if selected and ficheros == 0:
            self.status.setText("Todo está ya copiado: no hay nada nuevo.")

    # -- carpetas personalizadas ------------------------------------------

    def _add_custom(self) -> None:
        if not self.serial:
            QMessageBox.information(self, "Falta conectar", "Conecta antes con el móvil.")
            return
        dialog = AddFolderDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values["root"].startswith("/"):
            QMessageBox.warning(
                self, "Ruta no válida", "La ruta debe empezar por / — por ejemplo /sdcard/Notas."
            )
            return
        if not dir_exists(self.adb, self.serial, values["root"]):
            QMessageBox.warning(
                self,
                "No existe",
                f"En el móvil no hay ninguna carpeta llamada:\n{values['root']}",
            )
            return
        self.config.custom_sources = [
            c for c in self.config.custom_sources if c.get("root") != values["root"]
        ]
        self.config.custom_sources.append(values)
        self.config.save()

        source = ResolvedSource(
            key=f"custom:{values['root']}",
            label=values["label"],
            root=values["root"],
            dest_name=values["dest_name"],
            filter_key=values["filter_key"],
            custom=True,
        )
        self.status.setText(f"Analizando {source.dest_name}…")
        source.files = list_files(
            self.adb, self.serial, source.root, FILTER_SETS.get(source.filter_key, frozenset())
        )
        source.file_count = len(source.files)
        source.total_bytes = sum(f.size for f in source.files if f.size > 0)
        self.sources.append(source)
        self._compute_pending()
        self._fill_table()

    def _remove_custom(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.sources):
            return
        source = self.sources[row]
        if not source.custom:
            QMessageBox.information(
                self,
                "No se puede quitar",
                "Solo se pueden quitar las carpetas que hayas añadido tú.\n"
                "Para no copiar una de las demás, basta con desmarcarla.",
            )
            return
        self.config.custom_sources = [
            c for c in self.config.custom_sources if c.get("root") != source.root
        ]
        self.config.save()
        self.sources.pop(row)
        self._fill_table()

    # -- destino y arranque ------------------------------------------------

    def _choose_dest(self) -> None:
        current = self.dest_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Elige dónde guardar la copia", current, QFileDialog.Option.ShowDirsOnly
        )
        if chosen:
            self.dest_edit.setText(chosen)
            self.config.dest = chosen
            self.config.save()
            self._refresh_summary()

    def _go(self) -> None:
        dest = Path(self.dest_edit.text()).expanduser()
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self, "Destino no válido", f"No se puede escribir en {dest}:\n{exc}"
            )
            return
        self.config.dest = str(dest)
        self.config.verify_hash = self.verify_check.isChecked()
        self.config.save()
        selected = [s for s in self.sources if s.enabled]
        self.start_backup.emit(selected, dest, self.full_check.isChecked())
