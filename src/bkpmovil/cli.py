"""Interfaz de línea de órdenes. Hace todo lo que hace la ventana gráfica."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adb import Adb, AdbError
from .backup import BackupEngine, Progress, rebuild_index_from_backups
from .config import Config
from .discovery import discover
from .index import BackupIndex
from .localfs import human_size, open_in_file_manager
from .report import summary_text, write_reports


def _connect(adb: Adb, args: argparse.Namespace) -> str:
    """Conecta si hacen falta host/puerto y devuelve el serial a usar."""
    if args.host:
        port = args.port or "5555"
        print(f"Conectando con {args.host}:{port}…")
        print(adb.connect(args.host, port))
        return f"{args.host}:{port}"
    ready = [d for d in adb.devices() if d.is_ready]
    if not ready:
        raise SystemExit(
            "No hay ningún móvil conectado. Usa --host y --port, o conéctalo antes con 'pair'."
        )
    return ready[0].serial


def _print_progress(progress: Progress, state: dict) -> None:
    if progress.phase == "terminado":
        sys.stdout.write("\n")
        return
    if progress.files_done == state.get("last"):
        return
    state["last"] = progress.files_done
    speed = f"{human_size(progress.speed)}/s" if progress.speed else "…"
    bar_width = 24
    filled = int(bar_width * progress.percent / 100)
    bar = "█" * filled + "·" * (bar_width - filled)
    line = (
        f"\r[{bar}] {progress.percent:3d}%  "
        f"{progress.files_done}/{progress.files_total}  "
        f"{progress.folder[:18]:<18}  {speed:>10}  {progress.file_name[:28]:<28}"
    )
    sys.stdout.write(line[:160])
    sys.stdout.flush()


def cmd_devices(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    adb.start_server()
    devices = adb.devices()
    if not devices:
        print("No hay dispositivos conectados.")
        for name, target in adb.mdns_services():
            print(f"  Detectado en la red: {target}  ({name})")
        return 1
    for device in devices:
        info = adb.device_info(device.serial) if device.is_ready else None
        extra = f" — {info.display_name}" if info else ""
        print(f"{device.serial:<28} {device.state}{extra}")
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    print(adb.pair(args.host, args.port, args.code))
    print("Emparejado. Ahora conecta con el puerto de la pantalla principal:")
    print(f"  bkpmovil connect --host {args.host} --port <puerto>")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    print(adb.connect(args.host, args.port))
    info = adb.device_info(f"{args.host}:{args.port}")
    print(f"Conectado a {info.display_name}")
    return 0


def cmd_tcpip(args: argparse.Namespace) -> int:
    """Android 10 o anterior: activa el modo WiFi con el móvil por cable."""
    adb = Adb(args.adb)
    usb = [d for d in adb.devices() if d.is_ready and not d.is_wireless]
    if not usb:
        raise SystemExit("Conecta el móvil por cable USB y acepta el aviso de depuración.")
    adb.run(["-s", usb[0].serial, "tcpip", "5555"], check=True, timeout=30)
    print("Modo WiFi activado en el puerto 5555. Ya puedes desconectar el cable.")
    print("Después:  bkpmovil connect --host <IP del móvil> --port 5555")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    serial = _connect(adb, args)
    config = Config.load()
    root, sources = discover(adb, serial, config.custom_sources, on_progress=lambda m: print(m))
    print(f"\nAlmacenamiento: {root}\n")
    for source in sources:
        mark = "x" if source.enabled and not config.is_disabled(source.key) else " "
        print(
            f" [{mark}] {source.dest_name:<22} {source.file_count:>7} ficheros"
            f"  {human_size(source.total_bytes):>10}   {source.root}"
        )
    total = sum(s.file_count for s in sources)
    print(f"\nTotal detectado: {total} ficheros")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    serial = _connect(adb, args)
    config = Config.load()
    dest = Path(args.dest or config.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    info = adb.device_info(serial)
    print(f"Móvil: {info.display_name}")
    root, sources = discover(adb, serial, config.custom_sources, on_progress=lambda m: print(m))

    only = set(args.only or [])
    for source in sources:
        if only:
            source.enabled = source.dest_name in only or source.key in only
        elif config.is_disabled(source.key):
            source.enabled = False

    selected = [s for s in sources if s.enabled]
    if not selected:
        raise SystemExit("No hay ninguna carpeta seleccionada.")
    print("\nSe copiarán:")
    for source in selected:
        print(f"  · {source.dest_name:<22} {source.file_count:>7} ficheros  "
              f"{human_size(source.total_bytes):>10}")

    index = BackupIndex.for_device(serial, info.model)
    engine = BackupEngine(
        adb,
        serial,
        dest,
        selected,
        index,
        full=args.full,
        verify_hash=args.verify,
        device_name=info.display_name,
        reconnect_target=serial,
        on_progress=lambda p, s={}: _print_progress(p, s),
        on_log=print,
    )

    _, files_total, bytes_total = engine.plan()
    fits, available = engine.space_check(bytes_total)
    if not fits:
        raise SystemExit(
            f"No hay espacio suficiente en {dest}: hacen falta {human_size(bytes_total)} "
            f"y quedan {human_size(available)}."
        )
    if files_total == 0:
        print("\nNo hay nada nuevo que copiar: la copia anterior ya está al día.")
        return 0

    result = engine.run()
    write_reports(result)
    print("\n" + summary_text(result))
    if args.open:
        open_in_file_manager(result.dest)
    return 1 if result.total_failed else 0


def cmd_rebuild_index(args: argparse.Namespace) -> int:
    adb = Adb(args.adb)
    serial = _connect(adb, args)
    config = Config.load()
    info = adb.device_info(serial)
    print("Analizando el móvil para comparar con las copias…")
    _, sources = discover(adb, serial, config.custom_sources)
    index = BackupIndex.for_device(serial, info.model)
    index.clear()
    dest = Path(args.dest or config.dest).expanduser()
    recovered = rebuild_index_from_backups(index, dest, sources)
    print(f"Índice reconstruido a partir de {dest}: {recovered} ficheros registrados.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bkpmovil",
        description="Copias de seguridad incrementales de un móvil Android por WiFi.",
    )
    parser.add_argument("--adb", help="Ruta al ejecutable adb (si no, se busca solo)")
    subparsers = parser.add_subparsers(dest="command")

    def add_target(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--host", help="IP del móvil")
        sub.add_argument("--port", help="Puerto de conexión")

    subparsers.add_parser("devices", help="Lista los móviles conectados").set_defaults(
        func=cmd_devices
    )

    pair = subparsers.add_parser("pair", help="Empareja con el código de 6 cifras (Android 11+)")
    pair.add_argument("--host", required=True)
    pair.add_argument("--port", required=True, help="Puerto de la VENTANA de vinculación")
    pair.add_argument("--code", required=True, help="Código de 6 cifras")
    pair.set_defaults(func=cmd_pair)

    connect = subparsers.add_parser("connect", help="Conecta con el móvil ya emparejado")
    connect.add_argument("--host", required=True)
    connect.add_argument("--port", required=True, help="Puerto de la pantalla principal")
    connect.set_defaults(func=cmd_connect)

    tcpip = subparsers.add_parser("tcpip", help="Android 10 o anterior: activa WiFi por cable")
    tcpip.set_defaults(func=cmd_tcpip)

    listing = subparsers.add_parser("list", help="Muestra qué carpetas se han detectado")
    add_target(listing)
    listing.set_defaults(func=cmd_list)

    backup = subparsers.add_parser("backup", help="Hace la copia de seguridad")
    add_target(backup)
    backup.add_argument("--dest", help="Carpeta de destino en el ordenador")
    backup.add_argument("--only", nargs="*", help="Copiar solo estas carpetas (por nombre)")
    backup.add_argument("--full", action="store_true", help="Copia completa, sin incremental")
    backup.add_argument("--verify", action="store_true", help="Verificar cada fichero con sha1")
    backup.add_argument("--open", action="store_true", help="Abrir la carpeta al terminar")
    backup.set_defaults(func=cmd_backup)

    rebuild = subparsers.add_parser(
        "rebuild-index", help="Reconstruye el índice desde las copias ya hechas"
    )
    add_target(rebuild)
    rebuild.add_argument("--dest", help="Carpeta donde están las copias")
    rebuild.set_defaults(func=cmd_rebuild_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except AdbError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrumpido.", file=sys.stderr)
        return 130
