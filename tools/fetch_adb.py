"""Descarga las platform-tools de Google y deja adb dentro de vendor/.

Así el ejecutable que se distribuye no obliga a instalar nada más.
"""

from __future__ import annotations

import io
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://dl.google.com/android/repository/platform-tools-latest-{}.zip"
PLATAFORMAS = {"win32": "windows", "linux": "linux", "darwin": "darwin"}

# Solo lo imprescindible para hablar con el móvil.
NECESARIOS = {
    "adb", "adb.exe",
    "AdbWinApi.dll", "AdbWinUsbApi.dll",
    "libwinpthread-1.dll",
}


def main(destino: Path | None = None) -> int:
    clave = next((v for k, v in PLATAFORMAS.items() if sys.platform.startswith(k)), None)
    if clave is None:
        print(f"Plataforma no soportada: {sys.platform}", file=sys.stderr)
        return 1

    vendor = destino or Path(__file__).resolve().parent.parent / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)

    url = BASE.format(clave)
    print(f"Descargando {url}…")
    with urllib.request.urlopen(url, timeout=180) as respuesta:
        contenido = respuesta.read()

    copiados = 0
    with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
        for miembro in zf.namelist():
            nombre = Path(miembro).name
            if nombre not in NECESARIOS:
                continue
            with zf.open(miembro) as origen, open(vendor / nombre, "wb") as salida:
                shutil.copyfileobj(origen, salida)
            copiados += 1

    adb = vendor / ("adb.exe" if clave == "windows" else "adb")
    if not adb.is_file():
        print("No se ha encontrado adb dentro del zip", file=sys.stderr)
        return 1
    adb.chmod(adb.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"{copiados} ficheros en {vendor} · {adb.name} listo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
