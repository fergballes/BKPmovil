"""Paso 1: guía de conexión y emparejamiento con el móvil."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..adb import Adb, AdbError, DeviceInfo
from ..config import Config, DeviceProfile
from ..guide import (
    ANTES_DE_EMPEZAR,
    GUIDES,
    LEGACY_GUIDE,
    QUE_NO_SE_COPIA,
    QUE_SE_COPIA,
)
from .style import lista_html
from .workers import ConnectWorker, MdnsWorker, PairOnlyWorker

NUEVO_MOVIL = "— Móvil nuevo —"


class ConnectPage(QWidget):
    """Formulario de conexión con la guía al lado."""

    connected = Signal(str, object)  # serial, DeviceInfo

    def __init__(self, adb: Adb, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.adb = adb
        self.config = config
        self._worker: ConnectWorker | PairOnlyWorker | MdnsWorker | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(self._build_guide(), 5)
        layout.addWidget(self._build_form(), 4)
        self._refresh_guide()
        self._refresh_profiles()

    # -- guía --------------------------------------------------------------

    def _build_guide(self) -> QWidget:
        box = QGroupBox("Cómo preparar el móvil")
        inner = QVBoxLayout(box)

        self.brand = QComboBox()
        for guide in GUIDES:
            self.brand.addItem(guide.label, guide.key)
        self.brand.addItem(LEGACY_GUIDE.label, LEGACY_GUIDE.key)
        self.brand.currentIndexChanged.connect(self._refresh_guide)
        inner.addWidget(QLabel("Elige tu marca de móvil:"))
        inner.addWidget(self.brand)

        self.guide_view = QTextBrowser()
        self.guide_view.setOpenExternalLinks(False)
        self.guide_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner.addWidget(self.guide_view, 1)
        return box

    def _refresh_guide(self, *_args) -> None:
        key = self.brand.currentData()
        guide = LEGACY_GUIDE if key == "legacy" else next(g for g in GUIDES if g.key == key)
        legacy = key == "legacy"

        html = [
            "<h3 style='margin-top:0;'>Antes de empezar</h3>",
            lista_html(ANTES_DE_EMPEZAR),
            "<h3>1. Activar las opciones de desarrollador</h3>",
            lista_html(guide.developer_steps, ordenada=True),
            "<h3>2. "
            + ("Activar el modo WiFi" if legacy else "Activar la depuración inalámbrica")
            + "</h3>",
            lista_html(guide.wireless_steps, ordenada=True),
        ]
        if guide.notes:
            html += [
                "<div style='background:#fef9c3;border:1px solid #fde047;border-radius:8px;"
                "padding:8px 12px;'><b>Ojo:</b>",
                lista_html(guide.notes),
                "</div>",
            ]
        html += [
            "<h3>Qué se copia</h3>",
            lista_html(QUE_SE_COPIA),
            "<h3>Qué NO se puede copiar</h3>",
            lista_html(QUE_NO_SE_COPIA),
        ]
        self.guide_view.setHtml(
            "<div style='font-size:14px;line-height:1.5;color:#334155;'>"
            + "".join(html)
            + "</div>"
        )
        self.legacy_button.setVisible(legacy)
        self.pair_box.setVisible(not legacy)

    # -- formulario --------------------------------------------------------

    def _build_form(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        # Perfiles guardados
        saved = QGroupBox("Móvil")
        saved_layout = QFormLayout(saved)
        self.profile = QComboBox()
        self.profile.currentIndexChanged.connect(self._load_profile)
        saved_layout.addRow("Guardados:", self.profile)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Móvil de papá")
        saved_layout.addRow("Nombre:", self.name_edit)
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.1.50")
        saved_layout.addRow("IP del móvil:", self.host_edit)

        detect_row = QHBoxLayout()
        self.detect_button = QPushButton("Buscar móviles en mi red")
        self.detect_button.clicked.connect(self._detect)
        detect_row.addWidget(self.detect_button)
        self.forget_button = QPushButton("Olvidar este móvil")
        self.forget_button.setObjectName("peligro")
        self.forget_button.clicked.connect(self._forget)
        detect_row.addWidget(self.forget_button)
        saved_layout.addRow("", detect_row)
        outer.addWidget(saved)

        # Vinculación (solo la primera vez)
        self.pair_box = QGroupBox("Vincular  ·  solo la primera vez")
        pair_layout = QFormLayout(self.pair_box)
        self.pair_port_edit = QLineEdit()
        self.pair_port_edit.setPlaceholderText("37451  ·  el de la ventana emergente")
        pair_layout.addRow("Puerto de vinculación:", self.pair_port_edit)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("123456")
        self.code_edit.setMaxLength(6)
        pair_layout.addRow("Código de 6 cifras:", self.code_edit)
        self.pair_button = QPushButton("Vincular")
        self.pair_button.clicked.connect(self._pair)
        pair_layout.addRow("", self.pair_button)
        outer.addWidget(self.pair_box)

        # Conexión
        connect_box = QGroupBox("Conectar  ·  cada vez que hagas una copia")
        connect_layout = QFormLayout(connect_box)
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("41233  ·  el de la pantalla principal")
        connect_layout.addRow("Puerto de conexión:", self.port_edit)
        self.connect_button = QPushButton("Conectar con el móvil")
        self.connect_button.setObjectName("primario")
        self.connect_button.clicked.connect(self._connect)
        connect_layout.addRow("", self.connect_button)

        self.legacy_button = QPushButton("Activar por cable (Android 10 o anterior)")
        self.legacy_button.clicked.connect(self._tcpip)
        connect_layout.addRow("", self.legacy_button)
        outer.addWidget(connect_box)

        self.status = QLabel("Rellena la IP y el puerto y pulsa «Conectar con el móvil».")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        outer.addWidget(self.status)
        outer.addStretch(1)
        return panel

    # -- perfiles ----------------------------------------------------------

    def _refresh_profiles(self) -> None:
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItem(NUEVO_MOVIL)
        for prof in self.config.profiles:
            self.profile.addItem(prof.name)
        self.profile.blockSignals(False)
        if self.config.profiles:
            self.profile.setCurrentIndex(1)
            self._load_profile()

    def _load_profile(self, *_args) -> None:
        name = self.profile.currentText()
        prof = self.config.profile(name)
        if not prof:
            self.name_edit.clear()
            self.host_edit.clear()
            self.port_edit.clear()
            return
        self.name_edit.setText(prof.name)
        self.host_edit.setText(prof.host)
        self.port_edit.setText(prof.port)
        if prof.paired:
            self.status.setText(
                f"«{prof.name}» ya está vinculado con este ordenador.\n"
                "Solo tienes que comprobar el puerto de conexión (cambia al reiniciar "
                "el móvil o el WiFi) y pulsar «Conectar»."
            )

    def _forget(self) -> None:
        name = self.profile.currentText()
        if not self.config.profile(name):
            return
        answer = QMessageBox.question(self, "Olvidar móvil", f"¿Quitar «{name}» de la lista?")
        if answer == QMessageBox.StandardButton.Yes:
            self.config.remove_profile(name)
            self.config.save()
            self._refresh_profiles()

    def _save_profile(self, serial: str, info: DeviceInfo, paired: bool) -> None:
        name = self.name_edit.text().strip() or info.display_name or self.host_edit.text()
        self.config.upsert_profile(
            DeviceProfile(
                name=name,
                host=self.host_edit.text().strip(),
                port=self.port_edit.text().strip(),
                serial=serial,
                paired=paired or bool(self.config.profile(name) and self.config.profile(name).paired),
            )
        )
        self.config.save()

    # -- acciones ----------------------------------------------------------

    def _busy(self, busy: bool) -> None:
        for widget in (
            self.connect_button,
            self.pair_button,
            self.detect_button,
            self.legacy_button,
        ):
            widget.setEnabled(not busy)

    def _validate(self, need_pair: bool) -> bool:
        host = self.host_edit.text().strip()
        if not host or host.count(".") != 3:
            self._error("Escribe la IP del móvil, con el formato 192.168.1.50.")
            return False
        if need_pair:
            if not self.pair_port_edit.text().strip().isdigit():
                self._error("El puerto de vinculación es el número que sale tras los dos puntos "
                            "en la ventana emergente del móvil.")
                return False
            if len(self.code_edit.text().strip()) != 6:
                self._error("El código de vinculación tiene 6 cifras.")
                return False
        elif not self.port_edit.text().strip().isdigit():
            self._error("Escribe el puerto que aparece en la pantalla de Depuración inalámbrica.")
            return False
        return True

    def _error(self, message: str) -> None:
        self.status.setObjectName("estadoError")
        self.status.setText(message)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _info(self, message: str, ok: bool = False) -> None:
        self.status.setObjectName("estadoOk" if ok else "")
        self.status.setText(message)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _pair(self) -> None:
        if not self._validate(need_pair=True):
            return
        self._busy(True)
        self._info("Vinculando… mantén abierta la ventana del móvil.")
        worker = PairOnlyWorker(
            self.adb,
            self.host_edit.text().strip(),
            self.pair_port_edit.text().strip(),
            self.code_edit.text().strip(),
            self,
        )
        worker.ok.connect(self._paired)
        worker.failed.connect(self._failed)
        worker.finished.connect(lambda: self._busy(False))
        self._worker = worker
        worker.start()

    def _paired(self, _message: str) -> None:
        self.code_edit.clear()
        self.pair_port_edit.clear()
        self._info(
            "Vinculado correctamente. Ahora escribe el puerto que aparece en la "
            "pantalla principal de Depuración inalámbrica (es otro número) y pulsa "
            "«Conectar con el móvil».",
            ok=True,
        )
        name = self.name_edit.text().strip()
        if name:
            profile = self.config.profile(name) or DeviceProfile(name=name)
            profile.host = self.host_edit.text().strip()
            profile.paired = True
            self.config.upsert_profile(profile)
            self.config.save()

    def _connect(self) -> None:
        if not self._validate(need_pair=False):
            return
        self._busy(True)
        worker = ConnectWorker(
            self.adb,
            self.host_edit.text().strip(),
            self.port_edit.text().strip(),
            parent=self,
        )
        worker.progress.connect(lambda m: self._info(m))
        worker.ok.connect(self._connected)
        worker.failed.connect(self._failed)
        worker.finished.connect(lambda: self._busy(False))
        self._worker = worker
        worker.start()

    def _connected(self, serial: str, info: DeviceInfo) -> None:
        self._save_profile(serial, info, paired=True)
        self._refresh_profiles()
        self._info(f"Conectado con {info.display_name}.", ok=True)
        self.connected.emit(serial, info)

    def _failed(self, message: str) -> None:
        self._error(message)
        QMessageBox.warning(self, "No se ha podido conectar", message)

    def _detect(self) -> None:
        self._busy(True)
        self._info("Buscando móviles… abre en el móvil la pantalla de Depuración inalámbrica.")
        worker = MdnsWorker(self.adb, self)
        worker.ok.connect(self._detected)
        worker.finished.connect(lambda: self._busy(False))
        self._worker = worker
        worker.start()

    def _detected(self, services: list) -> None:
        if not services:
            self._info(
                "No se ha detectado ningún móvil automáticamente. No pasa nada: escribe "
                "a mano la IP y el puerto que ves en el móvil."
            )
            return
        _, target = services[0]
        host, _, port = target.rpartition(":")
        self.host_edit.setText(host)
        self.port_edit.setText(port)
        self._info(f"Móvil detectado en {target}. Pulsa «Conectar con el móvil».", ok=True)

    def _tcpip(self) -> None:
        try:
            self.adb.start_server()
            usb = [d for d in self.adb.devices() if d.is_ready and not d.is_wireless]
            if not usb:
                self._error(
                    "No se ve ningún móvil por cable. Conéctalo por USB y acepta en la "
                    "pantalla del móvil el aviso «¿Permitir depuración USB?»."
                )
                return
            self.adb.run(["-s", usb[0].serial, "tcpip", "5555"], check=True, timeout=30)
            info = self.adb.device_info(usb[0].serial)
            self.port_edit.setText("5555")
            self._info(
                f"Modo WiFi activado en {info.display_name}. Ya puedes desconectar el cable, "
                "escribir la IP del móvil y pulsar «Conectar con el móvil».",
                ok=True,
            )
        except AdbError as exc:
            self._error(str(exc))
