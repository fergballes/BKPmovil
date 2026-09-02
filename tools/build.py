"""Construye el paquete distribuible para el sistema actual.

    python tools/build.py            # descarga adb, empaqueta y comprime
    python tools/build.py --sin-adb  # sin incluir adb (paquete más ligero)

Deja en dist/ una carpeta BKPmovil lista para ejecutar y un comprimido.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist"
SALIDA = DIST / "BKPmovil"


def version() -> str:
    texto = (RAIZ / "src" / "bkpmovil" / "__init__.py").read_text(encoding="utf-8")
    for linea in texto.splitlines():
        if linea.startswith("__version__"):
            return linea.split("=")[1].strip().strip('"').strip("'")
    return "0.0.0"


def ejecutar(orden: list[str]) -> None:
    print(f"$ {' '.join(orden)}")
    subprocess.run(orden, check=True, cwd=RAIZ)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-adb", action="store_true", help="no empaquetar adb")
    parser.add_argument("--sin-limpiar", action="store_true", help="no borrar dist/ antes")
    args = parser.parse_args()

    if not (RAIZ / "assets" / "icono.ico").is_file():
        ejecutar([sys.executable, "tools/build_icons.py"])

    if not args.sin_adb:
        ejecutar([sys.executable, "tools/fetch_adb.py"])

    if not args.sin_limpiar and DIST.exists():
        shutil.rmtree(DIST)

    ejecutar([sys.executable, "-m", "PyInstaller", "--noconfirm", "packaging/bkpmovil.spec"])
    if not SALIDA.is_dir():
        print("PyInstaller no ha generado dist/BKPmovil", file=sys.stderr)
        return 1

    sufijo = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower()
    )
    nombre = f"BKPmovil-{version()}-{sufijo}-{platform.machine().lower()}"

    if sufijo == "linux":
        for extra in ("instalar.sh", "bkpmovil.desktop"):
            shutil.copy2(RAIZ / "packaging" / "linux" / extra, SALIDA / extra)
        os.chmod(SALIDA / "instalar.sh", 0o755)
        shutil.copy2(RAIZ / "LEEME-INSTALACION.txt", SALIDA / "LEEME.txt")
        archivo = shutil.make_archive(str(DIST / nombre), "gztar", root_dir=DIST, base_dir="BKPmovil")
    else:
        if (RAIZ / "LEEME-INSTALACION.txt").is_file():
            shutil.copy2(RAIZ / "LEEME-INSTALACION.txt", SALIDA / "LEEME.txt")
        archivo = shutil.make_archive(str(DIST / nombre), "zip", root_dir=DIST, base_dir="BKPmovil")

    tamano = Path(archivo).stat().st_size / (1024 * 1024)
    print(f"\nListo:\n  Carpeta:    {SALIDA}\n  Comprimido: {archivo}  ({tamano:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
