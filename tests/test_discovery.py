"""Detección de carpetas y listado de ficheros en el móvil."""

from __future__ import annotations

from bkpmovil.discovery import (
    UNKNOWN,
    dir_exists,
    discover,
    find_app_dirs,
    list_files,
    storage_root,
)
from bkpmovil.paths import MEDIA_EXT, is_excluded


def test_storage_root_se_detecta(adb):
    assert storage_root(adb, None) == "/sdcard"


def test_dir_exists(adb):
    assert dir_exists(adb, None, "/sdcard/DCIM")
    assert not dir_exists(adb, None, "/sdcard/NoExiste")


def test_list_files_devuelve_tamano_y_fecha(adb):
    ficheros = list_files(adb, None, "/sdcard/DCIM")
    rutas = {f.path for f in ficheros}
    assert "/sdcard/DCIM/Camera/IMG_0001.jpg" in rutas
    assert "/sdcard/DCIM/Screenshots/captura.png" in rutas
    uno = next(f for f in ficheros if f.path.endswith("IMG_0001.jpg"))
    assert uno.size == len(b"foto uno" * 100)
    assert uno.mtime == 1_700_000_000
    assert uno.metadata_known


def test_list_files_filtra_por_extension(adb):
    ficheros = list_files(adb, None, "/sdcard/Download", MEDIA_EXT)
    assert ficheros == []  # solo hay un pdf y un txt


def test_list_files_admite_nombres_con_caracteres_raros(adb):
    rutas = {f.path for f in list_files(adb, None, "/sdcard/Download")}
    assert "/sdcard/Download/nombre: raro?.txt" in rutas


def test_carpetas_bloqueadas_se_ignoran(adb):
    rutas = {f.path for f in list_files(adb, None, "/sdcard")}
    assert not any("/Android/data/" in r for r in rutas)
    assert not any("/.thumbnails/" in r for r in rutas)
    assert is_excluded("/sdcard/Android/data/com.whatsapp/x")


def test_find_app_dirs_encuentra_whatsapp_y_descarta_anidadas(adb):
    encontradas = find_app_dirs(adb, None, ("*whatsapp*",), "/sdcard")
    assert "/sdcard/WhatsApp" in encontradas
    assert "/sdcard/Android/media/com.whatsapp" in encontradas
    # No debe devolver también la subcarpeta interior.
    assert "/sdcard/Android/media/com.whatsapp/WhatsApp" not in encontradas


def test_discover_completo(adb):
    raiz, fuentes = discover(adb, None)
    assert raiz == "/sdcard"
    nombres = {f.dest_name for f in fuentes}
    assert {"DCIM", "Pictures", "Download", "Documents", "Music"} <= nombres
    assert any(n.startswith("WhatsApp") for n in nombres)
    assert any(n.startswith("Telegram") for n in nombres)

    dcim = next(f for f in fuentes if f.dest_name == "DCIM")
    assert dcim.file_count == 4
    assert dcim.total_bytes > 0


def test_whatsapp_solo_trae_fotos_y_videos(adb):
    _, fuentes = discover(adb, None)
    whatsapp = [f for f in fuentes if f.dest_name.startswith("WhatsApp")]
    assert whatsapp, "no se ha detectado ninguna carpeta de WhatsApp"
    copiados = {f.path for fuente in whatsapp for f in fuente.files}
    assert any(r.endswith("IMG-20260101-WA0001.jpg") for r in copiados)
    assert any(r.endswith("VID-20260101-WA0002.mp4") for r in copiados)
    # Audios y documentos quedan fuera: solo fotos y vídeos.
    assert not any(r.endswith(".opus") for r in copiados)
    assert not any(r.endswith("contrato.pdf") for r in copiados)
    # Y nunca la base de datos de chats.
    assert not any("msgstore" in r for r in copiados)


def test_nombres_de_destino_no_chocan(adb):
    _, fuentes = discover(adb, None)
    nombres = [f.dest_name for f in fuentes]
    assert len(nombres) == len(set(nombres))


def test_fallback_sin_metadatos(adb, monkeypatch):
    original = adb.shell

    def shell_sin_stat(serial, command, timeout=30):
        if "stat -c" in command:
            return ""
        return original(serial, command, timeout)

    monkeypatch.setattr(adb, "shell", shell_sin_stat)
    ficheros = list_files(adb, None, "/sdcard/DCIM")
    assert len(ficheros) == 4
    assert all(f.size == UNKNOWN and not f.metadata_known for f in ficheros)
