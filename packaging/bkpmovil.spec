# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller. Se construye con  pyinstaller packaging/bkpmovil.spec"""

import sys
from pathlib import Path

RAIZ = Path(SPECPATH).parent  # noqa: F821 - lo define PyInstaller
ES_WINDOWS = sys.platform.startswith("win")

datos = [(str(RAIZ / "assets"), "assets")]
vendor = RAIZ / "vendor"
if vendor.is_dir():
    datos.append((str(vendor), "vendor"))

# Qt trae mucho que aquí no se usa; fuera para que el paquete no engorde.
SOBRA = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtOpenGL",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "tkinter", "unittest", "pydoc_data",
]

a = Analysis(
    [str(RAIZ / "tools" / "lanzador.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    datas=datos,
    hiddenimports=["bkpmovil.ui.app"],
    excludes=SOBRA,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BKPmovil",
    console=False,
    icon=str(RAIZ / "assets" / "icono.ico") if ES_WINDOWS else None,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BKPmovil",
)
