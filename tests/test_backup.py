"""El motor incremental: qué copia, qué se salta y cómo aguanta los fallos."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from bkpmovil.backup import (
    BackupEngine,
    backup_folder_name,
    rebuild_index_from_backups,
)
from bkpmovil.discovery import discover
from bkpmovil.index import BackupIndex
from bkpmovil.report import MANIFIESTO, RESUMEN, write_reports
from tests.conftest import escribir


def _motor(adb, destino: Path, indice: BackupIndex, **kwargs) -> BackupEngine:
    _, fuentes = discover(adb, None)
    return BackupEngine(adb, None, destino, fuentes, indice, **kwargs)


@pytest.fixture
def indice(tmp_path: Path) -> BackupIndex:
    return BackupIndex(tmp_path / "indice.json")


def test_nombre_de_carpeta_con_formato_pedido():
    assert backup_folder_name(datetime(2026, 9, 2)) == "bkp_02092026"


def test_copia_completa_primera_vez(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    resultado = _motor(adb, destino, indice).run()

    assert resultado.dest.name.startswith("bkp_")
    assert resultado.total_copied > 0
    assert resultado.total_failed == 0
    assert (resultado.dest / "DCIM" / "Camera" / "IMG_0001.jpg").is_file()
    assert (resultado.dest / "Pictures" / "wallpaper.jpg").is_file()
    # La estructura de carpetas del móvil se mantiene.
    assert (resultado.dest / "DCIM" / "Screenshots" / "captura.png").is_file()


def test_el_contenido_copiado_es_identico(adb, tmp_path, indice):
    resultado = _motor(adb, tmp_path / "copias", indice).run()
    origen = adb.root / "DCIM" / "Camera" / "IMG_0001.jpg"
    copia = resultado.dest / "DCIM" / "Camera" / "IMG_0001.jpg"
    assert copia.read_bytes() == origen.read_bytes()


def test_segunda_copia_no_repite_nada(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    primera = _motor(adb, destino, indice).run()
    assert primera.total_copied > 0

    segunda_motor = _motor(adb, destino, indice)
    _, pendientes, _ = segunda_motor.plan()
    assert pendientes == 0

    segunda = segunda_motor.run()
    assert segunda.total_copied == 0
    assert segunda.total_skipped == primera.total_copied


def test_solo_se_copia_lo_nuevo(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    _motor(adb, destino, indice).run()

    escribir(adb.root, "DCIM/Camera/IMG_9999.jpg", b"foto nueva" * 50, mtime=1_800_000_000)
    segunda = _motor(adb, destino, indice).run()

    assert segunda.total_copied == 1
    assert (segunda.dest / "DCIM" / "Camera" / "IMG_9999.jpg").is_file()
    assert not (segunda.dest / "DCIM" / "Camera" / "IMG_0001.jpg").exists()


def test_fichero_modificado_se_vuelve_a_copiar(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    _motor(adb, destino, indice).run()

    escribir(adb.root, "Pictures/wallpaper.jpg", b"fondo cambiado" * 90, mtime=1_900_000_000)
    segunda = _motor(adb, destino, indice).run()

    assert segunda.total_copied == 1
    copiado = segunda.dest / "Pictures" / "wallpaper.jpg"
    assert copiado.read_bytes() == b"fondo cambiado" * 90


def test_copia_completa_forzada_lo_trae_todo(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    primera = _motor(adb, destino, indice).run()
    segunda = _motor(adb, destino, indice, full=True).run()
    assert segunda.total_copied == primera.total_copied
    assert segunda.incremental is False


def test_dos_copias_el_mismo_dia_no_se_pisan(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    primera = _motor(adb, destino, indice).run()
    segunda = _motor(adb, destino, indice, full=True).run()
    assert primera.dest != segunda.dest
    assert segunda.dest.name.endswith("_2")


def test_nombres_invalidos_en_windows_se_sanean(adb, tmp_path, indice):
    resultado = _motor(adb, tmp_path / "copias", indice).run()
    copiados = [p.name for p in (resultado.dest / "Download").iterdir()]
    assert "nombre_ raro_.txt" in copiados
    assert resultado.total_failed == 0


def test_reintenta_y_acaba_copiando(adb, tmp_path, indice):
    adb.fail_paths["/sdcard/DCIM/Camera/IMG_0001.jpg"] = 2  # falla dos veces, va a la tercera
    resultado = _motor(adb, tmp_path / "copias", indice, on_log=lambda m: None).run()
    assert resultado.total_failed == 0
    assert (resultado.dest / "DCIM" / "Camera" / "IMG_0001.jpg").is_file()


def test_fichero_que_siempre_falla_se_registra_pero_no_para_la_copia(adb, tmp_path, indice):
    adb.fail_paths["/sdcard/DCIM/Camera/IMG_0001.jpg"] = 99
    resultado = _motor(adb, tmp_path / "copias", indice, on_log=lambda m: None).run()
    assert resultado.total_failed == 1
    assert resultado.total_copied > 5
    assert resultado.errors[0][0] == "/sdcard/DCIM/Camera/IMG_0001.jpg"
    # Y no se anota como copiado, para reintentarlo la próxima vez.
    assert "/sdcard/DCIM/Camera/IMG_0001.jpg" not in indice.entries


def test_cancelar_conserva_lo_copiado(adb, tmp_path, indice):
    motor = _motor(adb, tmp_path / "copias", indice)
    copiados = []

    def al_avanzar(progreso):
        if progreso.files_done >= 2 and not copiados:
            copiados.append(True)
            motor.cancel()

    motor.on_progress = al_avanzar
    resultado = motor.run()
    assert resultado.cancelled
    assert 0 < resultado.total_copied < resultado.folders[0].scanned + 20
    # Lo copiado queda registrado: la próxima vez se sigue desde ahí.
    assert len(indice) == resultado.total_copied


def test_pausar_y_reanudar(adb, tmp_path, indice):
    motor = _motor(adb, tmp_path / "copias", indice)
    motor.pause()
    hilo = threading.Thread(target=motor.run)
    hilo.start()
    time.sleep(0.3)
    assert motor.is_paused
    motor.resume()
    hilo.join(timeout=30)
    assert not hilo.is_alive()
    assert len(indice) > 0


def test_el_indice_sobrevive_a_un_corte(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    _motor(adb, destino, indice).run()
    recargado = BackupIndex(indice.path)
    assert len(recargado) == len(indice)


def test_reconstruir_indice_desde_las_copias(adb, tmp_path, indice):
    destino = tmp_path / "copias"
    primera = _motor(adb, destino, indice).run()

    vacio = BackupIndex(tmp_path / "otro.json")
    _, fuentes = discover(adb, None)
    recuperados = rebuild_index_from_backups(vacio, destino, fuentes)
    assert recuperados == primera.total_copied

    # Con el índice reconstruido, no hay nada pendiente.
    motor = BackupEngine(adb, None, destino, fuentes, vacio)
    _, pendientes, _ = motor.plan()
    assert pendientes == 0


def test_verificacion_de_tamano_detecta_copia_corrupta(adb, tmp_path, indice, monkeypatch):
    original = adb.pull

    def pull_corrupto(serial, remote, local, timeout=600):
        original(serial, remote, local, timeout)
        if remote.endswith("IMG_0002.jpg"):
            Path(str(local)).write_bytes(b"truncado")

    monkeypatch.setattr(adb, "pull", pull_corrupto)
    resultado = _motor(adb, tmp_path / "copias", indice, on_log=lambda m: None).run()
    assert resultado.total_failed == 1
    assert "tamaño distinto" in resultado.errors[0][1]


def test_se_escribe_el_informe(adb, tmp_path, indice):
    resultado = _motor(adb, tmp_path / "copias", indice).run()
    resumen, manifiesto = write_reports(resultado)
    assert resumen.name == RESUMEN and manifiesto.name == MANIFIESTO

    texto = resumen.read_text(encoding="utf-8")
    assert "FICHEROS COPIADOS" in texto
    assert "DCIM" in texto
    assert str(resultado.total_copied) in texto.replace(".", "")

    import json

    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert datos["totales"]["ficheros_copiados"] == resultado.total_copied
    assert datos["totales"]["carpetas"] == len(resultado.folders_with_content)


def test_el_resumen_cuenta_carpetas_y_ficheros(adb, tmp_path, indice):
    resultado = _motor(adb, tmp_path / "copias", indice).run()
    assert len(resultado.folders_with_content) >= 5
    assert resultado.total_copied == sum(f.copied for f in resultado.folders)
    assert resultado.total_subdirs > 0


def test_solo_se_copian_las_carpetas_marcadas(adb, tmp_path, indice):
    _, fuentes = discover(adb, None)
    for fuente in fuentes:
        fuente.enabled = fuente.dest_name == "DCIM"
    resultado = BackupEngine(adb, None, tmp_path / "copias", fuentes, indice).run()
    assert [f.dest_name for f in resultado.folders] == ["DCIM"]
    assert not (resultado.dest / "Pictures").exists()
