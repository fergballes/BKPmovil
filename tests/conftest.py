"""Móvil simulado: el árbol de ficheros vive en una carpeta temporal.

Las órdenes que la app manda al móvil (`find`, `stat`, `[ -d … ]`) se
ejecutan de verdad contra esa carpeta, así que se prueba el mismo texto que
se enviaría a un Android real, con sus mismas comillas y sus mismos parseos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from bkpmovil.adb import AdbError, DeviceInfo

RAIZ_REMOTA = "/sdcard"


@dataclass
class FakeDevice:
    serial: str
    state: str = "device"
    model: str = "Movil Simulado"

    @property
    def is_ready(self) -> bool:
        return self.state == "device"

    @property
    def is_wireless(self) -> bool:
        return ":" in self.serial


class FakeAdb:
    """Sustituto de `Adb` que opera sobre una carpeta local."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.path = "adb-simulado"
        self.pulls: list[tuple[str, str]] = []
        self.fail_paths: dict[str, int] = {}  # ruta -> veces que debe fallar
        self.offline = False

    # -- traducción de rutas ----------------------------------------------

    def to_local(self, remote: str) -> Path:
        if remote == RAIZ_REMOTA:
            return self.root
        if remote.startswith(RAIZ_REMOTA + "/"):
            return self.root / remote[len(RAIZ_REMOTA) + 1 :]
        return Path(remote)

    # -- API que usa la aplicación ----------------------------------------

    def start_server(self) -> None:
        return None

    def devices(self) -> list[FakeDevice]:
        return [] if self.offline else [FakeDevice("192.168.1.50:41233")]

    def is_online(self, serial: str) -> bool:
        return not self.offline

    def device_info(self, serial: str | None = None) -> DeviceInfo:
        return DeviceInfo(
            serial=serial or "",
            manufacturer="Xiaomi",
            model="Redmi Note 8",
            android="11",
            sdk=30,
        )

    def shell(self, serial, command: str, timeout: int = 30) -> str:
        if self.offline:
            raise AdbError("device offline")
        if "$EXTERNAL_STORAGE" in command:
            return "\n"
        traducido = command.replace(f"'{RAIZ_REMOTA}", f"'{self.root}").replace(
            f" {RAIZ_REMOTA}", f" {self.root}"
        )
        proc = subprocess.run(
            ["/bin/sh", "-c", traducido], capture_output=True, text=True, timeout=timeout
        )
        # Devolvemos las rutas en el espacio de nombres del "móvil".
        return proc.stdout.replace(str(self.root), RAIZ_REMOTA)

    def pull(self, serial, remote: str, local, timeout: int = 600) -> None:
        if self.offline:
            raise AdbError("device offline")
        restantes = self.fail_paths.get(remote, 0)
        if restantes > 0:
            self.fail_paths[remote] = restantes - 1
            raise AdbError(f"adb: error: failed to copy '{remote}'")
        origen = self.to_local(remote)
        if not origen.exists():
            raise AdbError(f"adb: error: remote object '{remote}' does not exist")
        destino = Path(str(local))
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        self.pulls.append((remote, str(destino)))

    def connect(self, host, port) -> str:
        self.offline = False
        return f"connected to {host}:{port}"

    def run(self, args, timeout: int = 30, check: bool = False):
        raise AdbError("no implementado en el simulador")


def escribir(base: Path, relativa: str, contenido: bytes, mtime: int = 1_700_000_000) -> Path:
    destino = base / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    os.utime(destino, (mtime, mtime))
    return destino


@pytest.fixture
def movil(tmp_path: Path) -> Path:
    """Árbol representativo de un Android real."""
    base = tmp_path / "movil"
    escribir(base, "DCIM/Camera/IMG_0001.jpg", b"foto uno" * 100)
    escribir(base, "DCIM/Camera/IMG_0002.jpg", b"foto dos" * 120)
    escribir(base, "DCIM/Camera/VID_0003.mp4", b"video" * 500)
    escribir(base, "DCIM/Screenshots/captura.png", b"captura" * 40)
    escribir(base, "Pictures/wallpaper.jpg", b"fondo" * 60)
    escribir(base, "Download/manual.pdf", b"pdf" * 300)
    escribir(base, "Download/nombre: raro?.txt", b"nombre raro")
    escribir(base, "Documents/notas.txt", b"notas")
    escribir(base, "Music/cancion.mp3", b"musica" * 200)

    # WhatsApp moderno (Android 11+): media accesible, datos no.
    wa = "Android/media/com.whatsapp/WhatsApp/Media"
    escribir(base, f"{wa}/WhatsApp Images/IMG-20260101-WA0001.jpg", b"wa foto" * 90)
    escribir(base, f"{wa}/WhatsApp Video/VID-20260101-WA0002.mp4", b"wa video" * 400)
    escribir(base, f"{wa}/WhatsApp Voice Notes/202601/AUD-0001.opus", b"audio" * 30)
    escribir(base, f"{wa}/WhatsApp Documents/contrato.pdf", b"documento" * 50)
    # Zona bloqueada en un móvil real; aquí existe para probar que se ignora.
    escribir(base, "Android/data/com.whatsapp/files/msgstore.db", b"chats")

    # WhatsApp antiguo y Telegram
    escribir(base, "WhatsApp/Media/WhatsApp Images/viejo.jpg", b"antiguo" * 70)
    escribir(base, "Telegram/Telegram Images/tg.jpg", b"telegram" * 45)

    escribir(base, ".thumbnails/basura.jpg", b"basura")
    return base


@pytest.fixture
def adb(movil: Path) -> FakeAdb:
    return FakeAdb(movil)


@pytest.fixture
def entorno(tmp_path: Path, monkeypatch) -> Path:
    """Aísla la configuración y el índice de la app en la carpeta temporal."""
    home = tmp_path / "bkpmovil-home"
    monkeypatch.setenv("BKPMOVIL_HOME", str(home))
    return home
