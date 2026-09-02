"""Nombres de fichero, tamaños y textos legibles."""

from __future__ import annotations

from pathlib import Path

import pytest

from bkpmovil.localfs import (
    human_duration,
    human_size,
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
