"""Nombres de fichero, tamaños y textos legibles."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from bkpmovil.localfs import (
    entorno_del_sistema,
    human_duration,
    human_size,
    miles,
    relative_to_root,
    sanitize_component,
    sanitize_relative,
    unique_dir,
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("foto.jpg", "foto.jpg"),
        ("nombre: raro?.txt", "nombre_ raro_.txt"),
        ('a<b>c"d|e*f.txt', "a_b_c_d_e_f.txt"),
        ("acaba en punto.", "acaba en punto"),
        ("CON.txt", "_CON.txt"),
        ("LPT1", "_LPT1"),
        ("", "_"),
        ("emoji 🎉 y ácentos.jpg", "emoji 🎉 y ácentos.jpg"),
    ],
)
def test_sanitize_component(entrada, esperado):
    assert sanitize_component(entrada) == esperado


def test_sanitize_relative_descarta_tramos_peligrosos():
    assert sanitize_relative("a/../b/c.jpg") == str(Path("a/b/c.jpg"))
    assert sanitize_relative("/") == ""


def test_relative_to_root():
    assert relative_to_root("/sdcard/DCIM/Camera/a.jpg", "/sdcard/DCIM") == "Camera/a.jpg"
    assert relative_to_root("/sdcard/DCIM", "/sdcard/DCIM") == "DCIM"
    assert relative_to_root("/sdcard/DCIM/a.jpg", "/sdcard/DCIM/") == "a.jpg"


@pytest.mark.parametrize(
    "octetos,esperado",
    [(0, "0 B"), (512, "512 B"), (1536, "1,5 KB"), (3812044, "3,6 MB"), (-1, "?")],
)
def test_human_size(octetos, esperado):
    assert human_size(octetos) == esperado


@pytest.mark.parametrize(
    "segundos,esperado", [(5, "5 s"), (65, "1 min 5 s"), (3725, "1 h 2 min")]
)
def test_human_duration(segundos, esperado):
    assert human_duration(segundos) == esperado


def test_unique_dir_no_pisa_carpetas(tmp_path):
    primera = unique_dir(tmp_path, "bkp_02092026")
    primera.mkdir()
    segunda = unique_dir(tmp_path, "bkp_02092026")
    assert segunda.name == "bkp_02092026_2"
    segunda.mkdir()
    assert unique_dir(tmp_path, "bkp_02092026").name == "bkp_02092026_3"


@pytest.mark.parametrize(
    "cantidad,esperado", [(0, "0"), (999, "999"), (1000, "1.000"), (12797, "12.797")]
)
def test_miles(cantidad, esperado):
    assert miles(cantidad) == esperado


def test_el_separador_de_miles_no_se_come_la_coma_decimal():
    """El resumen mezcla ambos formatos: 3.278 ficheros y 6,8 GB."""
    texto = f"{miles(3278)} ficheros · {human_size(7_300_000_000)}"
    assert texto == "3.278 ficheros · 6,8 GB"


# -- entorno para lanzar programas del sistema ------------------------------
#
# Empaquetado con PyInstaller, la aplicación arranca con su propia carpeta de
# bibliotecas en LD_LIBRARY_PATH. Si el explorador de archivos la hereda, carga
# nuestro libssl en vez del suyo y no arranca: los botones «Abrir la carpeta de
# la copia» y «Ver el informe» no hacían nada.


@pytest.fixture
def paquete_simulado(monkeypatch, tmp_path):
    interno = tmp_path / "_internal"
    interno.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(interno), raising=False)
    monkeypatch.setenv("_MEIPASS2", str(interno))
    return interno


def test_restaura_el_valor_que_habia_antes(monkeypatch, paquete_simulado):
    monkeypatch.setenv("LD_LIBRARY_PATH", str(paquete_simulado))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    entorno = entorno_del_sistema()
    assert entorno["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in entorno
    assert "_MEIPASS2" not in entorno


def test_quita_la_variable_si_antes_estaba_vacia(monkeypatch, paquete_simulado):
    monkeypatch.setenv("LD_LIBRARY_PATH", str(paquete_simulado))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "")
    assert "LD_LIBRARY_PATH" not in entorno_del_sistema()


def test_sin_valor_previo_solo_quita_los_tramos_del_paquete(monkeypatch, paquete_simulado):
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", f"{paquete_simulado}{os.pathsep}/opt/mio/lib")
    assert entorno_del_sistema()["LD_LIBRARY_PATH"] == "/opt/mio/lib"


def test_no_toca_las_variables_que_necesita_xdg_open(monkeypatch, paquete_simulado):
    """Vaciar XDG_DATA_DIRS dejaría a xdg-open sin saber qué programa usar."""
    monkeypatch.setenv("LD_LIBRARY_PATH", str(paquete_simulado))
    monkeypatch.setenv("XDG_DATA_DIRS", "/usr/share:/usr/local/share")
    monkeypatch.setenv("PATH", "/usr/bin")
    entorno = entorno_del_sistema()
    assert entorno["XDG_DATA_DIRS"] == "/usr/share:/usr/local/share"
    assert entorno["PATH"] == "/usr/bin"


def test_sin_empaquetar_no_cambia_nada(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/mio/lib")
    assert entorno_del_sistema()["LD_LIBRARY_PATH"] == "/opt/mio/lib"
