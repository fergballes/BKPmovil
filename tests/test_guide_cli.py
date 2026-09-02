"""Guía por fabricante y órdenes de la línea de comandos."""

from __future__ import annotations

from bkpmovil.adb import DeviceInfo, quote_remote
from bkpmovil.cli import build_parser
from bkpmovil.guide import GUIDES, LEGACY_GUIDE, guide_for


def test_cada_marca_tiene_su_ruta_de_menu():
    for marca, clave in [
        ("Xiaomi", "xiaomi"),
        ("POCO", "xiaomi"),
        ("samsung", "samsung"),
        ("Google", "google"),
        ("HUAWEI", "huawei"),
        ("realme", "oppo"),
        ("OnePlus", "oppo"),
        ("Nothing", "generico"),
        ("", "generico"),
    ]:
        assert guide_for(marca).key == clave


def test_las_guias_estan_completas():
    for guia in (*GUIDES, LEGACY_GUIDE):
        assert guia.developer_steps and guia.wireless_steps
        assert all(paso.strip() for paso in guia.developer_steps)


def test_android_11_necesita_vinculacion():
    assert DeviceInfo(serial="x", sdk=30).needs_pairing
    assert not DeviceInfo(serial="x", sdk=29).needs_pairing


def test_nombre_visible_del_movil():
    info = DeviceInfo(serial="s", manufacturer="xiaomi", model="Redmi Note 8", android="11")
    assert info.display_name == "Xiaomi Redmi Note 8 (Android 11)"
    assert DeviceInfo(serial="solo-serial").display_name == "solo-serial"


def test_las_rutas_se_entrecomillan_para_el_shell_del_movil():
    assert quote_remote("/sdcard/a b") == "'/sdcard/a b'"
    assert quote_remote("/sdcard/o'hara") == "'/sdcard/o'\\''hara'"


def test_la_cli_acepta_las_ordenes_esperadas():
    parser = build_parser()
    for orden in ("devices", "list", "backup", "connect", "pair", "tcpip", "rebuild-index"):
        assert orden in parser.format_help()

    args = parser.parse_args(["backup", "--host", "192.168.1.50", "--port", "41233", "--full"])
    assert args.host == "192.168.1.50" and args.full

    args = parser.parse_args(["pair", "--host", "1.2.3.4", "--port", "37451", "--code", "123456"])
    assert args.code == "123456"
