"""Índice incremental y preferencias guardadas."""

from __future__ import annotations

from bkpmovil.config import Config, DeviceProfile, app_dir
from bkpmovil.discovery import RemoteFile
from bkpmovil.index import BackupIndex, device_key


def test_fichero_desconocido_no_esta_copiado(tmp_path):
    indice = BackupIndex(tmp_path / "i.json")
    assert not indice.is_copied(RemoteFile("/sdcard/a.jpg", 10, 20))


def test_mismo_tamano_y_fecha_cuenta_como_copiado(tmp_path):
    indice = BackupIndex(tmp_path / "i.json")
    fichero = RemoteFile("/sdcard/a.jpg", 10, 20)
    indice.mark(fichero, "bkp_02092026", "DCIM/a.jpg")
    assert indice.is_copied(fichero)
    assert indice.where("/sdcard/a.jpg") == "bkp_02092026"


def test_cambios_obligan_a_recopiar(tmp_path):
    indice = BackupIndex(tmp_path / "i.json")
    indice.mark(RemoteFile("/sdcard/a.jpg", 10, 20), "bkp", "a.jpg")
    assert not indice.is_copied(RemoteFile("/sdcard/a.jpg", 11, 20))  # otro tamaño
    assert not indice.is_copied(RemoteFile("/sdcard/a.jpg", 10, 21))  # más reciente
    assert indice.is_copied(RemoteFile("/sdcard/a.jpg", 10, 19))  # más antiguo: ya estaba


def test_sin_metadatos_basta_la_ruta(tmp_path):
    indice = BackupIndex(tmp_path / "i.json")
    indice.mark(RemoteFile("/sdcard/a.jpg", 10, 20), "bkp", "a.jpg")
    assert indice.is_copied(RemoteFile("/sdcard/a.jpg", -1, -1))


def test_el_indice_se_guarda_y_se_recarga(tmp_path):
    ruta = tmp_path / "i.json"
    indice = BackupIndex(ruta)
    indice.mark(RemoteFile("/sdcard/ñ á.jpg", 10, 20), "bkp", "ñ á.jpg")
    indice.save()
    assert len(BackupIndex(ruta)) == 1


def test_indice_corrupto_no_rompe(tmp_path):
    ruta = tmp_path / "i.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    assert len(BackupIndex(ruta)) == 0


def test_device_key_es_valido_como_nombre_de_fichero():
    clave = device_key("192.168.1.50:41233", "Redmi Note 8")
    assert "/" not in clave and ":" not in clave


def test_configuracion_va_a_la_carpeta_de_la_app(entorno):
    assert app_dir() == entorno


def test_configuracion_ida_y_vuelta(entorno):
    config = Config.load()
    config.dest = "/tmp/copias"
    config.upsert_profile(DeviceProfile(name="Móvil de papá", host="192.168.1.50", paired=True))
    config.set_enabled("music", False)
    config.custom_sources.append({"root": "/sdcard/Notas", "dest_name": "Notas"})
    config.save()

    recargada = Config.load()
    assert recargada.dest == "/tmp/copias"
    assert recargada.profile("Móvil de papá").paired
    assert recargada.is_disabled("music")
    assert recargada.custom_sources[0]["root"] == "/sdcard/Notas"


def test_perfiles_no_se_duplican(entorno):
    config = Config.load()
    config.upsert_profile(DeviceProfile(name="X", host="1.1.1.1"))
    config.upsert_profile(DeviceProfile(name="X", host="2.2.2.2"))
    assert len(config.profiles) == 1
    assert config.profiles[0].host == "2.2.2.2"
    config.remove_profile("X")
    assert config.profiles == []
