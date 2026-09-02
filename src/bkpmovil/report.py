"""Informe final de la copia: RESUMEN.txt legible y manifiesto.json."""

from __future__ import annotations

import json
from pathlib import Path

from .backup import BackupResult
from .localfs import human_duration, human_size

RESUMEN = "RESUMEN.txt"
MANIFIESTO = "manifiesto.json"


def _column_widths(rows: list[list[str]], headers: list[str]) -> list[int]:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    return widths


def summary_table(result: BackupResult) -> str:
    """Tabla de carpetas copiadas en texto monoespaciado."""
    headers = ["Carpeta", "Ficheros", "Tamaño", "Ya copiados", "Fallos"]
    rows = [
        [
            folder.dest_name,
            f"{folder.copied:,}".replace(",", "."),
            human_size(folder.bytes_copied),
            f"{folder.skipped:,}".replace(",", "."),
            str(folder.failed),
        ]
        for folder in result.folders
    ]
    total_row = [
        "TOTAL",
        f"{result.total_copied:,}".replace(",", "."),
        human_size(result.total_bytes),
        f"{result.total_skipped:,}".replace(",", "."),
        str(result.total_failed),
    ]
    widths = _column_widths(rows + [total_row], headers)

    def line(cells: list[str]) -> str:
        out = cells[0].ljust(widths[0])
        for i, cell in enumerate(cells[1:], start=1):
            out += "  " + cell.rjust(widths[i])
        return out

    separator = "─" * (sum(widths) + 2 * (len(widths) - 1))
    parts = [line(headers), separator]
    parts += [line(row) for row in rows]
    parts += [separator, line(total_row)]
    return "\n".join(parts)


def summary_text(result: BackupResult) -> str:
    """Informe completo en texto plano."""
    estado = "CANCELADA (lo copiado es válido)" if result.cancelled else "TERMINADA"
    tipo = "incremental (solo lo nuevo)" if result.incremental else "completa"
    lines = [
        "COPIA DE SEGURIDAD — BKPmovil",
        "=" * 60,
        f"Estado:      {estado}",
        f"Tipo:        {tipo}",
        f"Móvil:       {result.device or result.serial or 'desconocido'}",
        f"Inicio:      {result.started.strftime('%d/%m/%Y %H:%M:%S')}",
        f"Fin:         {(result.finished or result.started).strftime('%d/%m/%Y %H:%M:%S')}",
        f"Duración:    {human_duration(result.duration)}",
        f"Destino:     {result.dest}",
        "",
        f"Carpetas copiadas:     {len(result.folders_with_content)}",
        f"Subcarpetas creadas:   {result.total_subdirs}",
        f"FICHEROS COPIADOS:     {result.total_copied:,}".replace(",", "."),
        f"Tamaño copiado:        {human_size(result.total_bytes)}",
        f"Omitidos (ya estaban): {result.total_skipped:,}".replace(",", "."),
        f"Fallidos:              {result.total_failed}",
        "",
        summary_table(result),
    ]

    if result.errors:
        lines += ["", f"ERRORES ({len(result.errors)})", "-" * 60]
        for path, message in result.errors[:200]:
            lines.append(f"{path}\n    → {message}")
        if len(result.errors) > 200:
            lines.append(f"… y {len(result.errors) - 200} más (ver {MANIFIESTO})")

    lines += [
        "",
        "-" * 60,
        "Nota: sin acceso de superusuario, Android no permite copiar el",
        "historial de chats de WhatsApp (/sdcard/Android/data), solo sus",
        "fotos, vídeos y audios. Tampoco contactos, SMS ni datos internos",
        "de las aplicaciones.",
    ]
    return "\n".join(lines) + "\n"


def manifest(result: BackupResult) -> dict:
    return {
        "app": "BKPmovil",
        "version": 1,
        "dispositivo": result.device,
        "serial": result.serial,
        "inicio": result.started.isoformat(timespec="seconds"),
        "fin": (result.finished or result.started).isoformat(timespec="seconds"),
        "duracion_segundos": round(result.duration, 1),
        "cancelada": result.cancelled,
        "incremental": result.incremental,
        "destino": str(result.dest),
        "totales": {
            "carpetas": len(result.folders_with_content),
            "subcarpetas": result.total_subdirs,
            "ficheros_copiados": result.total_copied,
            "bytes_copiados": result.total_bytes,
            "omitidos": result.total_skipped,
            "fallidos": result.total_failed,
        },
        "carpetas": [
            {
                "nombre": f.dest_name,
                "origen": f.root,
                "descripcion": f.label,
                "copiados": f.copied,
                "omitidos": f.skipped,
                "fallidos": f.failed,
                "bytes": f.bytes_copied,
                "subcarpetas": f.subdirs,
            }
            for f in result.folders
        ],
        "errores": [{"ruta": p, "motivo": m} for p, m in result.errors],
    }


def write_reports(result: BackupResult) -> tuple[Path, Path]:
    """Escribe RESUMEN.txt y manifiesto.json dentro de la copia."""
    dest = Path(result.dest)
    dest.mkdir(parents=True, exist_ok=True)
    resumen = dest / RESUMEN
    manifiesto = dest / MANIFIESTO
    resumen.write_text(summary_text(result), encoding="utf-8")
    manifiesto.write_text(
        json.dumps(manifest(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return resumen, manifiesto
