"""Envoltorio fino sobre el ejecutable `adb`.

Aquí no hay lógica de copia: solo localizar el binario, hablar con él y
traducir su salida a estructuras de Python. Todo lo demás se construye
encima.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Evita ventanas de consola parpadeando en Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

DEFAULT_TIMEOUT = 30
PAIR_TIMEOUT = 45
SCAN_TIMEOUT = 600


class AdbError(RuntimeError):
    """Fallo al ejecutar adb o respuesta de error del propio adb."""


class AdbNotFound(AdbError):
    """No se encuentra el ejecutable de adb en el sistema."""


def _bundle_dir() -> Path | None:
    """Carpeta de recursos cuando la app corre empaquetada con PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def _ensure_executable(path: Path) -> None:
    """El empaquetado puede perder el permiso de ejecución; se lo devolvemos."""
    if os.name == "nt":
        return
    try:
        mode = path.stat().st_mode
        if not mode & stat.S_IXUSR:
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def find_adb() -> str:
    """Localiza el ejecutable de adb.

    Orden: variable de entorno, binario embebido en el paquete, PATH del
    sistema y por último las ubicaciones habituales del SDK de Android.
    """
    exe = "adb.exe" if os.name == "nt" else "adb"

    env = os.environ.get("BKPMOVIL_ADB")
    if env and Path(env).is_file():
        return env

    for base in (_bundle_dir(), Path(__file__).resolve().parent.parent.parent):
        if base is None:
            continue
        for candidate in (base / "vendor" / exe, base / "vendor" / "platform-tools" / exe):
            if candidate.is_file():
                _ensure_executable(candidate)
                return str(candidate)

    found = shutil.which("adb")
    if found:
        return found

    home = Path.home()
    for candidate in (
        home / "Android" / "Sdk" / "platform-tools" / exe,
        home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / exe,
        Path("/usr/lib/android-sdk/platform-tools") / exe,
        Path("C:/platform-tools") / exe,
    ):
        if candidate.is_file():
            return str(candidate)

    raise AdbNotFound(
        "No se ha encontrado 'adb'. Instálalo (en Arch: 'sudo pacman -S android-tools') "
        "o usa la versión empaquetada de BKPmovil, que ya lo incluye."
    )


@dataclass(frozen=True)
class Device:
    serial: str
    state: str  # device | unauthorized | offline
    model: str = ""

    @property
    def is_ready(self) -> bool:
        return self.state == "device"

    @property
    def is_wireless(self) -> bool:
        return ":" in self.serial and not self.serial.startswith("emulator")


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    manufacturer: str = ""
    model: str = ""
    android: str = ""
    sdk: int = 0

    @property
    def display_name(self) -> str:
        name = " ".join(p for p in (self.manufacturer.title(), self.model) if p).strip()
        if self.android:
            name = f"{name} (Android {self.android})" if name else f"Android {self.android}"
        return name or self.serial

    @property
    def needs_pairing(self) -> bool:
        """Android 11 (API 30) en adelante usa emparejamiento con código."""
        return self.sdk >= 30


def quote_remote(path: str) -> str:
    """Entrecomilla una ruta para el shell del móvil."""
    return "'" + path.replace("'", "'\\''") + "'"


class Adb:
    """Cliente de adb ligado a un ejecutable concreto."""

    def __init__(self, adb_path: str | None = None) -> None:
        self.path = adb_path or find_adb()

    # -- ejecución base ----------------------------------------------------

    def run(
        self,
        args: list[str],
        timeout: int = DEFAULT_TIMEOUT,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                [self.path, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb no respondió en {timeout} s: adb {' '.join(args)}") from exc
        except OSError as exc:
            raise AdbError(f"No se pudo ejecutar adb: {exc}") from exc
        if check and proc.returncode != 0:
            raise AdbError(_clean(proc.stderr) or _clean(proc.stdout) or "error desconocido de adb")
        return proc

    def _device_args(self, serial: str | None) -> list[str]:
        return ["-s", serial] if serial else []

    # -- servidor ----------------------------------------------------------

    def start_server(self) -> None:
        self.run(["start-server"], timeout=40)

    def kill_server(self) -> None:
        self.run(["kill-server"], timeout=20)

    def version(self) -> str:
        out = self.run(["version"]).stdout
        match = re.search(r"version ([\d.]+)", out)
        return match.group(1) if match else out.strip().splitlines()[0] if out.strip() else ""

    # -- conexión ----------------------------------------------------------

    def pair(self, host: str, port: int | str, code: str) -> str:
        """Empareja con el móvil (Android 11+). Devuelve el mensaje de adb."""
        proc = self.run(["pair", f"{host}:{port}", str(code)], timeout=PAIR_TIMEOUT)
        out = _clean(proc.stdout) + ("\n" + _clean(proc.stderr) if proc.stderr.strip() else "")
        if "Successfully paired" not in proc.stdout:
            raise AdbError(_friendly_pair_error(out))
        return _clean(proc.stdout)

    def connect(self, host: str, port: int | str) -> str:
        proc = self.run(["connect", f"{host}:{port}"], timeout=DEFAULT_TIMEOUT)
        out = _clean(proc.stdout) or _clean(proc.stderr)
        if "connected to" not in out:
            raise AdbError(_friendly_connect_error(out))
        return out

    def disconnect(self, target: str | None = None) -> None:
        self.run(["disconnect", *([target] if target else [])], timeout=15)

    def devices(self) -> list[Device]:
        proc = self.run(["devices", "-l"], timeout=20)
        found: list[Device] = []
        for line in proc.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            model = ""
            for token in parts[2:]:
                if token.startswith("model:"):
                    model = token[6:].replace("_", " ")
            found.append(Device(serial=parts[0], state=parts[1], model=model))
        return found

    def mdns_services(self) -> list[tuple[str, str]]:
        """Dispositivos que anuncian depuración inalámbrica en la red local.

        Devuelve pares (nombre_servicio, "ip:puerto"). Requiere que el móvil
        tenga la pantalla de *Depuración inalámbrica* abierta.
        """
        proc = self.run(["mdns", "services"], timeout=20)
        results: list[tuple[str, str]] = []
        for line in proc.stdout.splitlines():
            match = re.search(r"(\S+)\s+(_adb[-\w]*\._tcp)\s+(\d+\.\d+\.\d+\.\d+:\d+)", line)
            if match:
                results.append((match.group(1), match.group(3)))
        return results

    # -- dispositivo -------------------------------------------------------

    def getprop(self, serial: str | None, prop: str) -> str:
        proc = self.run([*self._device_args(serial), "shell", "getprop", prop], timeout=20)
        return _clean(proc.stdout)

    def device_info(self, serial: str | None = None) -> DeviceInfo:
        props = {
            "manufacturer": "ro.product.manufacturer",
            "model": "ro.product.model",
            "android": "ro.build.version.release",
            "sdk": "ro.build.version.sdk",
        }
        values = {key: self.getprop(serial, prop) for key, prop in props.items()}
        try:
            sdk = int(values["sdk"])
        except (TypeError, ValueError):
            sdk = 0
        return DeviceInfo(
            serial=serial or "",
            manufacturer=values["manufacturer"],
            model=values["model"],
            android=values["android"],
            sdk=sdk,
        )

    def shell(self, serial: str | None, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        proc = self.run([*self._device_args(serial), "shell", command], timeout=timeout)
        return proc.stdout.replace("\r\n", "\n")

    def is_online(self, serial: str) -> bool:
        return any(d.serial == serial and d.is_ready for d in self.devices())

    # -- transferencia -----------------------------------------------------

    def pull(
        self,
        serial: str | None,
        remote: str,
        local: str | os.PathLike[str],
        timeout: int = 600,
    ) -> None:
        """Descarga un fichero o carpeta preservando la fecha de modificación."""
        proc = self.run(
            [*self._device_args(serial), "pull", "-a", remote, str(local)],
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise AdbError(_clean(proc.stderr) or _clean(proc.stdout) or "fallo al descargar")


def _clean(text: str) -> str:
    return "\n".join(line.strip() for line in text.strip().splitlines() if line.strip())


def _friendly_pair_error(message: str) -> str:
    low = message.lower()
    if "failed to connect" in low or "connection refused" in low or not message:
        return (
            "No se ha podido conectar con el móvil para emparejar.\n\n"
            "Comprueba que:\n"
            "• El móvil y el ordenador están en la MISMA red WiFi.\n"
            "• La pantalla 'Vincular dispositivo con código' sigue abierta en el móvil "
            "(si la cierras, el puerto y el código caducan).\n"
            "• Has usado la IP y el PUERTO de esa ventana emergente, que son distintos "
            "de los de la pantalla principal."
        )
    if "incorrect" in low or "wrong" in low:
        return "El código de 6 dígitos no es correcto. Vuelve a abrir la ventana de vinculación en el móvil."
    return message


def _friendly_connect_error(message: str) -> str:
    low = message.lower()
    if "refused" in low or "failed to connect" in low:
        return (
            "No se ha podido conectar.\n\n"
            "• Usa la IP y el PUERTO que aparecen en la pantalla principal de "
            "'Depuración inalámbrica' (no los de la ventana de vinculación).\n"
            "• Ese puerto cambia cada vez que reinicias el móvil o el WiFi.\n"
            "• Si nunca has vinculado este ordenador, hazlo primero con el código."
        )
    if "missing port" in low or "protocol fault" in low:
        return "La dirección no es válida. Debe ser una IP como 192.168.1.50 y un puerto como 41233."
    return message or "No se ha podido conectar con el móvil."
