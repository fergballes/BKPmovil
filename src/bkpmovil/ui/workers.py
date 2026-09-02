"""Hilos de trabajo: adb nunca se ejecuta en el hilo de la interfaz."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..adb import Adb, AdbError, DeviceInfo
from ..backup import BackupEngine, BackupResult, Progress
from ..config import Config
from ..discovery import discover
from ..index import BackupIndex
from ..report import write_reports

#: Máximo de refrescos de progreso por segundo, para no saturar la interfaz.
REFRESCO_MAXIMO = 0.05


class ConnectWorker(QThread):
    """Empareja (opcional) y conecta con el móvil."""

    progress = Signal(str)
    ok = Signal(str, object)  # serial, DeviceInfo
    failed = Signal(str)

    def __init__(
        self,
        adb: Adb,
        host: str,
        port: str,
        pair_port: str = "",
        code: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.adb = adb
        self.host = host
        self.port = port
        self.pair_port = pair_port
        self.code = code

    def run(self) -> None:
        try:
            self.progress.emit("Arrancando adb…")
            self.adb.start_server()
            if self.pair_port and self.code:
                self.progress.emit("Vinculando con el móvil…")
                self.adb.pair(self.host, self.pair_port, self.code)
                self.progress.emit("Vinculado correctamente.")
            self.progress.emit(f"Conectando con {self.host}:{self.port}…")
            self.adb.connect(self.host, self.port)
            serial = f"{self.host}:{self.port}"
            for _ in range(10):
                if self.adb.is_online(serial):
                    break
                time.sleep(0.4)
            else:
                raise AdbError(
                    "El móvil ha aceptado la conexión pero no responde. Desbloquea la "
                    "pantalla y comprueba que sigue activada la depuración inalámbrica."
                )
            info: DeviceInfo = self.adb.device_info(serial)
            self.ok.emit(serial, info)
        except AdbError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - red de seguridad
            self.failed.emit(f"Error inesperado: {exc}")


class PairOnlyWorker(QThread):
    """Solo el emparejamiento, para poder validarlo por separado."""

    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, adb: Adb, host: str, port: str, code: str, parent=None) -> None:
        super().__init__(parent)
        self.adb = adb
        self.host = host
        self.port = port
        self.code = code

    def run(self) -> None:
        try:
            self.adb.start_server()
            self.ok.emit(self.adb.pair(self.host, self.port, self.code))
        except AdbError as exc:
            self.failed.emit(str(exc))


class MdnsWorker(QThread):
    """Busca móviles que anuncien la depuración inalámbrica en la red."""

    ok = Signal(list)

    def __init__(self, adb: Adb, parent=None) -> None:
        super().__init__(parent)
        self.adb = adb

    def run(self) -> None:
        try:
            self.adb.start_server()
            self.ok.emit(self.adb.mdns_services())
        except AdbError:
            self.ok.emit([])


class DiscoverWorker(QThread):
    """Localiza y analiza las carpetas del móvil."""

    progress = Signal(str)
    ok = Signal(str, list)  # raíz, fuentes
    failed = Signal(str)

    def __init__(self, adb: Adb, serial: str, custom: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.custom = custom

    def run(self) -> None:
        try:
            root, sources = discover(
                self.adb, self.serial, self.custom, on_progress=self.progress.emit
            )
            self.ok.emit(root, sources)
        except AdbError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover
            self.failed.emit(f"Error inesperado al analizar el móvil: {exc}")


class BackupWorker(QThread):
    """Ejecuta la copia y escribe el informe."""

    progress = Signal(object)  # Progress (copia inmutable)
    log = Signal(str)
    ok = Signal(object)  # BackupResult
    failed = Signal(str)

    def __init__(
        self,
        adb: Adb,
        serial: str,
        dest: Path,
        sources: list,
        device_name: str,
        model: str,
        config: Config,
        full: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.index = BackupIndex.for_device(serial, model)
        self.engine = BackupEngine(
            adb,
            serial,
            dest,
            sources,
            self.index,
            full=full,
            verify_hash=config.verify_hash,
            device_name=device_name,
            reconnect_target=serial,
            on_progress=self._on_progress,
            on_log=self.log.emit,
        )
        self._last_emit = 0.0

    # El motor llama a esto desde este mismo hilo; emitimos una copia para
    # que la interfaz nunca lea un objeto que sigue mutando.
    def _on_progress(self, progress: Progress) -> None:
        now = time.monotonic()
        if progress.phase == "terminado" or now - self._last_emit >= REFRESCO_MAXIMO:
            self._last_emit = now
            self.progress.emit(dataclasses.replace(progress))

    def run(self) -> None:
        try:
            result: BackupResult = self.engine.run()
            write_reports(result)
            self.ok.emit(result)
        except Exception as exc:  # pragma: no cover
            self.failed.emit(f"La copia se ha detenido por un error: {exc}")

    # -- control desde la interfaz ----------------------------------------

    def pause(self) -> None:
        self.engine.pause()

    def resume(self) -> None:
        self.engine.resume()

    def cancel(self) -> None:
        self.engine.cancel()

    @property
    def is_paused(self) -> bool:
        return self.engine.is_paused
