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


@pytest.fixture
def carpetas_analizadas(ventana, qt_app):
    """Página 2 ya analizada, lista para tocar las carpetas personalizadas."""
    pagina = ventana.folders_page
    pagina.set_device("192.168.1.50:41233", "Redmi Note 8")
    pagina.analyze()
    pagina._worker.wait(30000)
    qt_app.processEvents()
    return pagina


def _dialogo_falso(monkeypatch, valores: dict, aceptar: bool = True):
    """Sustituye el diálogo por uno que devuelve los valores indicados."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    import bkpmovil.ui.page_folders as modulo

    class DialogoFalso:
        def __init__(self, parent=None, inicial=None):
            self.inicial = inicial

        def exec(self):
            return (
                QDialog.DialogCode.Accepted if aceptar else QDialog.DialogCode.Rejected
            )

        def values(self):
            return dict(valores)

    monkeypatch.setattr(modulo, "AddFolderDialog", DialogoFalso)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)


def test_anadir_una_carpeta_del_movil(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    antes = len(pagina.sources)
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/Notas de voz",
            "label": "Mis notas",
            "dest_name": "Mis notas",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()

    assert len(pagina.sources) == antes + 1
    nueva = pagina.sources[-1]
    assert nueva.custom and nueva.dest_name == "Mis notas"
    assert nueva.file_count > 0
    assert pagina.config.custom_sources[-1]["root"] == "/sdcard/Notas de voz"


def test_no_se_admite_una_ruta_que_no_existe(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    antes = len(pagina.sources)
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/NoExisteNada",
            "label": "x",
            "dest_name": "x",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()
    assert len(pagina.sources) == antes


def test_editar_una_carpeta_no_la_duplica(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/Notas de voz",
            "label": "Mis notas",
            "dest_name": "Mis notas",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()
    total = len(pagina.sources)
    fila = len(pagina.sources) - 1

    # Se edita: mismo sitio, otro nombre y solo fotos y vídeos.
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/Notas de voz",
            "label": "Papeles",
            "dest_name": "Papeles",
            "filter_key": "media",
            "enabled": True,
        },
    )
    pagina._edit_custom(fila)

    assert len(pagina.sources) == total  # no se ha duplicado
    editada = next(s for s in pagina.sources if s.root == "/sdcard/Notas de voz")
    assert editada.dest_name == "Papeles"
    assert editada.filter_key == "media"
    rutas = [c["root"] for c in pagina.config.custom_sources]
    assert rutas.count("/sdcard/Notas de voz") == 1


def test_no_se_pueden_editar_ni_quitar_las_carpetas_detectadas(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    antes = len(pagina.sources)
    _dialogo_falso(monkeypatch, {})
    pagina.table.setCurrentCell(0, 0)
    pagina._edit_custom(0)
    pagina._remove_custom()
    assert len(pagina.sources) == antes


def test_quitar_una_carpeta_anadida(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/Notas de voz",
            "label": "Mis notas",
            "dest_name": "Mis notas",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()
    fila = len(pagina.sources) - 1
    pagina.table.setCurrentCell(fila, 0)
    pagina._remove_custom()

    assert all(s.root != "/sdcard/Notas de voz" for s in pagina.sources)
    assert all(c["root"] != "/sdcard/Notas de voz" for c in pagina.config.custom_sources)


def test_anadir_una_carpeta_que_ya_estaba_no_la_duplica(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    antes = len(pagina.sources)
    documentos = next(f for f in pagina.sources if f.dest_name == "Documents")
    documentos.enabled = False

    _dialogo_falso(
        monkeypatch,
        {
            "root": documentos.root,
            "label": "Otra vez documentos",
            "dest_name": "Otra vez documentos",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()

    assert len(pagina.sources) == antes
    assert documentos.enabled  # se marca la que ya estaba en vez de crear otra


def test_los_nombres_de_destino_nunca_chocan(carpetas_analizadas, monkeypatch):
    pagina = carpetas_analizadas
    _dialogo_falso(
        monkeypatch,
        {
            "root": "/sdcard/Notas de voz",
            "label": "DCIM",  # nombre que ya usa una carpeta detectada
            "dest_name": "DCIM",
            "filter_key": "todo",
            "enabled": True,
        },
    )
    pagina._add_custom()

    nombres = [f.dest_name for f in pagina.sources]
    assert len(nombres) == len(set(nombres))


def test_el_resumen_de_la_seleccion_usa_los_formatos_correctos(carpetas_analizadas):
    """Miles con punto y decimales con coma, en la misma frase."""
    import re

    texto = carpetas_analizadas.summary.text()
    assert re.search(r"\d+ carpetas · [\d.]+ ficheros · [\d,]+ (B|KB|MB|GB)", texto), texto
    assert not re.search(r"\d\.\d (B|KB|MB|GB)", texto), f"decimal con punto: {texto}"
