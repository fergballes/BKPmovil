"""Genera los PNG y el .ico de la aplicación a partir de assets/icono.svg.

Se ejecuta a mano cuando cambia el icono; los resultados se versionan para
que el empaquetado no dependa de tener Qt instalado.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> Path:
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    destino = ASSETS / f"icono-{size}.png"
    image.save(str(destino), "PNG")
    return destino


def build_ico(pngs: list[Path], destino: Path) -> None:
    """Empaqueta varios PNG en un .ico (formato PNG embebido, Vista+)."""
    datos = [p.read_bytes() for p in pngs]
    cabecera = struct.pack("<HHH", 0, 1, len(datos))
    offset = len(cabecera) + 16 * len(datos)
    entradas = b""
    for png, contenido in zip(pngs, datos, strict=True):
        lado = int(png.stem.split("-")[1])
        entradas += struct.pack(
            "<BBBBHHII", lado % 256, lado % 256, 0, 0, 1, 32, len(contenido), offset
        )
        offset += len(contenido)
    destino.write_bytes(cabecera + entradas + b"".join(datos))


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 - Qt lo necesita para pintar
    svg = ASSETS / "icono.svg"
    if not svg.is_file():
        print(f"Falta {svg}", file=sys.stderr)
        return 1
    renderer = QSvgRenderer(str(svg))
    pngs = [render(renderer, size) for size in TAMANOS]
    (ASSETS / "icono.png").write_bytes((ASSETS / "icono-256.png").read_bytes())
    build_ico(pngs, ASSETS / "icono.ico")
    print(f"Generados {len(pngs)} PNG, icono.png e icono.ico en {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
