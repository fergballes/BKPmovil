"""Comprobación de que la ventana se construye y navega sin errores."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from bkpmovil.backup import BackupResult, FolderResult, Progress
from bkpmovil.config import Config
from bkpmovil.ui.main_window import MainWindow
from bkpmovil.ui.style import STYLESHEET, paso_html


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    return app


@pytest.fixture
def ventana(qt_app, adb, entorno):
    window = MainWindow(adb, Config.load())
    yield window
    window.close()


def test_la_ventana_arranca_en_el_paso_uno(ventana):
    assert ventana.stack.currentIndex() == 0
    assert "Conectar" in paso_html(0)


def test_la_guia_cambia_con_la_marca(ventana):
    pagina = ventana.connect_page
    for indice in range(pagina.brand.count()):
        pagina.brand.setCurrentIndex(indice)
        assert pagina.guide_view.toPlainText().strip()
    # Al elegir Android antiguo aparece el botón del cable y desaparece vincular.
    pagina.brand.setCurrentIndex(pagina.brand.count() - 1)
    assert pagina.legacy_button.isVisible() or not pagina.pair_box.isVisible()


def test_validacion_de_ip_y_puerto(ventana):
    pagina = ventana.connect_page
    pagina.host_edit.setText("esto no es una ip")
    assert not pagina._validate(need_pair=False)
    pagina.host_edit.setText("192.168.1.50")
    pagina.port_edit.setText("")
    assert not pagina._validate(need_pair=False)
    pagina.port_edit.setText("41233")
    assert pagina._validate(need_pair=False)


def test_el_codigo_de_vinculacion_debe_tener_seis_cifras(ventana):
    pagina = ventana.connect_page
    pagina.host_edit.setText("192.168.1.50")
    pagina.pair_port_edit.setText("37451")
    pagina.code_edit.setText("123")
    assert not pagina._validate(need_pair=True)
    pagina.code_edit.setText("123456")
    assert pagina._validate(need_pair=True)


def test_analizar_llena_la_tabla_y_habilita_el_boton(ventana, qt_app):
    ventana.folders_page.set_device("192.168.1.50:41233", "Redmi Note 8")
    ventana.folders_page.analyze()
    ventana.folders_page._worker.wait(30000)
    qt_app.processEvents()

    tabla = ventana.folders_page.table
    assert tabla.rowCount() >= 5
    nombres = {tabla.item(f, 0).text().strip() for f in range(tabla.rowCount())}
    assert "DCIM" in nombres
    assert any(n.startswith("WhatsApp") for n in nombres)
    assert ventana.folders_page.go_button.isEnabled()


def test_desmarcar_todo_deshabilita_la_copia(ventana, qt_app):
    ventana.folders_page.set_device("192.168.1.50:41233", "Redmi Note 8")
    ventana.folders_page.analyze()
    ventana.folders_page._worker.wait(30000)
    qt_app.processEvents()

    ventana.folders_page._set_all(False)
    assert not ventana.folders_page.go_button.isEnabled()
    ventana.folders_page._set_all(True)
    assert ventana.folders_page.go_button.isEnabled()


def test_la_pagina_de_progreso_muestra_los_datos(ventana):
    pagina = ventana.progress_page
    pagina.reset()
    pagina.update_progress(
        Progress(
            "copiando",
            folder="WhatsApp",
            file_name="IMG-0001.jpg",
            files_done=120,
            files_total=400,
            bytes_done=500,
            bytes_total=1000,
            folder_files_done=20,
            folder_files_total=50,
            speed=5_000_000,
            eta=90,
        )
    )
    assert pagina.bar.value() == 50
    assert pagina.folder_bar.value() == 40
    assert pagina.valores["ficheros"].text() == "120"
    assert "WhatsApp" in pagina.title.text()


def test_el_resumen_muestra_carpetas_y_ficheros(ventana):
    resultado = BackupResult(dest=Path("/tmp/bkp_02092026"), device="Xiaomi Redmi Note 8")
    resultado.finished = resultado.started + timedelta(minutes=3)
    resultado.folders = [
        FolderResult("a", "Cámara", "/sdcard/DCIM", "DCIM", copied=10, skipped=2, bytes_copied=100),
        FolderResult("b", "WhatsApp", "/sdcard/WhatsApp", "WhatsApp", copied=5, bytes_copied=50),
        FolderResult("c", "Música", "/sdcard/Music", "Music", copied=0, skipped=7),
    ]
    ventana.report_page.show_result(resultado)
    assert ventana.report_page.valores["carpetas"].text() == "2"
    assert ventana.report_page.valores["ficheros"].text() == "15"
    assert ventana.report_page.table.rowCount() == 3


def test_navegacion_entre_pasos(ventana):
    for paso in range(4):
        ventana._go(paso)
        assert ventana.stack.currentIndex() == paso
    ventana._go(1)
    ventana._back()
    assert ventana.stack.currentIndex() == 0
