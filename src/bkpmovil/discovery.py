"""Localiza en el dispositivo qué carpetas existen y qué ficheros contienen."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .adb import Adb, AdbError, quote_remote
from .paths import (
    DEFAULT_SOURCES,
    FILTER_SETS,
    MESSAGING_APPS,
    MESSAGING_SEARCH_DEPTH,
    STORAGE_ROOTS,
    AppMediaSpec,
    ResolvedSource,
    SourceSpec,
    is_excluded,
    matches_filter,
)

#: Tamaño/fecha desconocidos (el móvil no soporta `stat`).
UNKNOWN = -1


@dataclass(frozen=True, slots=True)
class RemoteFile:
    path: str
    size: int
    mtime: int

    @property
    def name(self) -> str:
        return posixpath.basename(self.path)

    @property
    def metadata_known(self) -> bool:
        return self.size >= 0


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    return None


# --- Raíz de almacenamiento -------------------------------------------------


def storage_root(adb: Adb, serial: str | None) -> str:
    """Devuelve la raíz del almacenamiento interno del móvil."""
    try:
        env = adb.shell(serial, "echo $EXTERNAL_STORAGE").strip()
    except AdbError:
        env = ""
    for candidate in ([env] if env.startswith("/") else []) + list(STORAGE_ROOTS):
        if candidate and dir_exists(adb, serial, candidate):
            return candidate.rstrip("/")
    raise AdbError(
        "No se encuentra el almacenamiento del móvil. Desbloquea la pantalla y, si aparece "
        "un aviso de 'Permitir acceso a los datos del teléfono', acéptalo."
    )


def dir_exists(adb: Adb, serial: str | None, path: str) -> bool:
    out = adb.shell(serial, f"[ -d {quote_remote(path)} ] && echo SI || echo NO").strip()
    return out.endswith("SI")


# --- Listado de ficheros ----------------------------------------------------


def list_files(
    adb: Adb,
    serial: str | None,
    root: str,
    extensions: Iterable[str] | None = None,
    timeout: int = 600,
) -> list[RemoteFile]:
    """Lista recursivamente los ficheros de `root` con tamaño y fecha.

    Usa `find … -exec stat`, disponible en el toybox de Android. Si el móvil
    no lo soporta, cae a un listado sin metadatos: en ese caso el motor
    incremental se guía solo por la ruta.
    """
    exts = frozenset(e.lower() for e in extensions) if extensions else frozenset()
    quoted = quote_remote(root)

    command = f"find {quoted} -type f -exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null"
    out = adb.shell(serial, command, timeout=timeout)
    files = _parse_stat_lines(out, exts)
    if files:
        return files

    # Fallback: sin metadatos.
    out = adb.shell(serial, f"find {quoted} -type f 2>/dev/null", timeout=timeout)
    return _parse_plain_lines(out, exts)


def _parse_stat_lines(out: str, exts: frozenset[str]) -> list[RemoteFile]:
    files: list[RemoteFile] = []
    for line in out.splitlines():
        line = line.rstrip("\r")
        if "|" not in line or not line[:1].isdigit():
            continue
        size_s, _, rest = line.partition("|")
        mtime_s, _, path = rest.partition("|")
        if not path.startswith("/"):
            continue
        if is_excluded(path) or not matches_filter(posixpath.basename(path), exts):
            continue
        try:
            files.append(RemoteFile(path, int(size_s), int(float(mtime_s))))
        except ValueError:
            continue
    return files


def _parse_plain_lines(out: str, exts: frozenset[str]) -> list[RemoteFile]:
    files: list[RemoteFile] = []
    for line in out.splitlines():
        path = line.rstrip("\r").strip()
        if not path.startswith("/"):
            continue
        if is_excluded(path) or not matches_filter(posixpath.basename(path), exts):
            continue
        files.append(RemoteFile(path, UNKNOWN, UNKNOWN))
    return files


# --- Carpetas de mensajería -------------------------------------------------


def find_app_dirs(
    adb: Adb,
    serial: str | None,
    patterns: Iterable[str],
    root: str,
    depth: int = MESSAGING_SEARCH_DEPTH,
) -> list[str]:
    """Busca carpetas cuyo nombre encaje con los patrones dados.

    Devuelve solo las carpetas más altas: si aparecen `X` y `X/Y`, se
    descarta `X/Y` porque ya está contenida en la primera.
    """
    clauses = " -o ".join(f"-iname {quote_remote(p)}" for p in patterns)
    if not clauses:
        return []
    command = (
        f"find {quote_remote(root)} -maxdepth {depth} -type d \\( {clauses} \\) 2>/dev/null"
    )
    try:
        out = adb.shell(serial, command, timeout=180)
    except AdbError:
        return []

    found = sorted(
        {
            line.rstrip("\r").strip()
            for line in out.splitlines()
            if line.strip().startswith("/")
        }
    )
    tops: list[str] = []
    for path in found:
        if is_excluded(path + "/"):
            continue
        if any(path == t or path.startswith(t + "/") for t in tops):
            continue
        tops.append(path)
    return tops


# --- Resolución completa ----------------------------------------------------


def unique_dest(base: str, used: set[str], root: str) -> str:
    if base not in used:
        used.add(base)
        return base
    hint = posixpath.basename(posixpath.dirname(root)) or "2"
    candidate = f"{base} ({hint})"
    counter = 2
    while candidate in used:
        counter += 1
        candidate = f"{base} ({hint} {counter})"
    used.add(candidate)
    return candidate


def resolve_standard_sources(
    adb: Adb,
    serial: str | None,
    root: str,
    specs: Iterable[SourceSpec] = DEFAULT_SOURCES,
    used_dests: set[str] | None = None,
) -> list[ResolvedSource]:
    """Devuelve las fuentes estándar que existen de verdad en este móvil."""
    used = used_dests if used_dests is not None else set()
    resolved: list[ResolvedSource] = []
    for spec in specs:
        for relative in spec.candidates:
            path = posixpath.join(root, relative)
            if dir_exists(adb, serial, path):
                resolved.append(
                    ResolvedSource(
                        key=spec.key,
                        label=spec.label,
                        root=path,
                        dest_name=unique_dest(spec.dest_name, used, path),
                        filter_key=spec.filter_key,
                        enabled=spec.default_enabled,
                    )
                )
                break
    return resolved


def resolve_messaging_sources(
    adb: Adb,
    serial: str | None,
    root: str,
    apps: Iterable[AppMediaSpec] = MESSAGING_APPS,
    used_dests: set[str] | None = None,
    on_progress: ProgressFn = _noop,
) -> list[ResolvedSource]:
    """Busca las carpetas de WhatsApp, Telegram y similares en todo el móvil.

    No se asume ninguna ruta fija: se localiza cualquier carpeta con ese
    nombre y de ella se copian solo fotos y vídeos.
    """
    used = used_dests if used_dests is not None else set()
    resolved: list[ResolvedSource] = []
    for app in apps:
        on_progress(f"Buscando carpetas de {app.label.split()[-1]}…")
        for found in find_app_dirs(adb, serial, app.dir_patterns, root):
            resolved.append(
                ResolvedSource(
                    key=f"{app.key}:{found}",
                    label=f"{app.label} — {found}",
                    root=found,
                    dest_name=unique_dest(app.dest_name, used, found),
                    filter_key=app.filter_key,
                    enabled=app.default_enabled,
                )
            )
    return resolved


def resolve_custom_sources(
    adb: Adb,
    serial: str | None,
    custom: Iterable[dict],
    used_dests: set[str] | None = None,
) -> list[ResolvedSource]:
    """Fuentes añadidas a mano por el usuario (rutas del móvil)."""
    used = used_dests if used_dests is not None else set()
    resolved: list[ResolvedSource] = []
    for entry in custom:
        path = str(entry.get("root", "")).rstrip("/")
        if not path or not dir_exists(adb, serial, path):
            continue
        base = str(entry.get("dest_name") or posixpath.basename(path) or "Personalizada")
        resolved.append(
            ResolvedSource(
                key=f"custom:{path}",
                label=str(entry.get("label") or path),
                root=path,
                dest_name=unique_dest(base, used, path),
                filter_key=str(entry.get("filter_key", "todo")),
                enabled=bool(entry.get("enabled", True)),
                custom=True,
            )
        )
    return resolved


def scan_sources(
    adb: Adb,
    serial: str | None,
    sources: Iterable[ResolvedSource],
    on_progress: ProgressFn = _noop,
) -> list[ResolvedSource]:
    """Rellena `files`, `file_count` y `total_bytes` de cada fuente."""
    result = []
    for source in sources:
        on_progress(f"Analizando {source.dest_name}…")
        files = list_files(adb, serial, source.root, source.extensions)
        source.files = files
        source.file_count = len(files)
        source.total_bytes = sum(f.size for f in files if f.size > 0)
        result.append(source)
    return result


def discover(
    adb: Adb,
    serial: str | None,
    custom: Iterable[dict] = (),
    on_progress: ProgressFn = _noop,
    scan: bool = True,
) -> tuple[str, list[ResolvedSource]]:
    """Descubrimiento completo: raíz, carpetas presentes y su contenido."""
    on_progress("Localizando el almacenamiento del móvil…")
    root = storage_root(adb, serial)

    used: set[str] = set()
    on_progress("Buscando carpetas habituales…")
    sources = resolve_standard_sources(adb, serial, root, used_dests=used)
    sources += resolve_messaging_sources(adb, serial, root, used_dests=used, on_progress=on_progress)
    sources += resolve_custom_sources(adb, serial, custom, used_dests=used)

    if scan:
        scan_sources(adb, serial, sources, on_progress)
    return root, sources


__all__ = [
    "RemoteFile",
    "UNKNOWN",
    "discover",
    "dir_exists",
    "find_app_dirs",
    "list_files",
    "resolve_custom_sources",
    "resolve_messaging_sources",
    "resolve_standard_sources",
    "scan_sources",
    "storage_root",
    "unique_dest",
    "FILTER_SETS",
]
