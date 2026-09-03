"""Utilidades del sistema de ficheros local, con Windows en mente."""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

#: Caracteres prohibidos en nombres de fichero de Windows.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Nombres reservados por Windows, incluso con extensión.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(name: str) -> str:
    """Convierte un nombre de fichero de Android en uno válido en Windows."""
    cleaned = _ILLEGAL.sub("_", name).rstrip(" .")
    if not cleaned:
        return "_"
    stem = cleaned.split(".", 1)[0].upper()
    if stem in _RESERVED:
        cleaned = "_" + cleaned
    return cleaned[:200]


def sanitize_relative(relative: str) -> str:
    """Sanea cada tramo de una ruta relativa estilo POSIX."""
    parts = [p for p in relative.split("/") if p not in ("", ".", "..")]
    return os.path.join(*[sanitize_component(p) for p in parts]) if parts else ""


def relative_to_root(remote_path: str, root: str) -> str:
    """Ruta de `remote_path` relativa a `root`, en formato POSIX."""
    root = root.rstrip("/")
    if remote_path == root:
        return posixpath.basename(remote_path)
    if remote_path.startswith(root + "/"):
        return remote_path[len(root) + 1 :]
    return remote_path.lstrip("/")


def long_path(path: Path) -> str:
    """Prefija con \\\\?\\ en Windows para superar el límite de 260 caracteres."""
    text = str(path)
    if os.name == "nt" and not text.startswith("\\\\?\\") and len(text) > 240:
        return "\\\\?\\" + os.path.abspath(text)
    return text


def free_space(path: Path) -> int:
    """Bytes libres en el volumen que contiene `path` (0 si no se puede saber)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


def human_size(num_bytes: float) -> str:
    """Tamaño legible: 1536 -> '1,5 KB'."""
    if num_bytes < 0:
        return "?"
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f}".replace(".", ",") + f" {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def miles(cantidad: int) -> str:
    """Número con el separador de miles en castellano: 12345 -> '12.345'."""
    return f"{cantidad:,}".replace(",", ".")


def human_duration(seconds: float) -> str:
    """Duración legible en castellano."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"


def unique_dir(parent: Path, name: str) -> Path:
    """Devuelve `parent/name`, o `name_2`, `name_3`… si ya existe."""
    candidate = parent / name
    counter = 2
    while candidate.exists():
        candidate = parent / f"{name}_{counter}"
        counter += 1
    return candidate


#: Variables del cargador dinámico que PyInstaller retoca al arrancar. Si un
#: programa del sistema las hereda, carga nuestras bibliotecas empaquetadas en
#: vez de las suyas y no arranca (el explorador de archivos, por ejemplo).
_VARIABLES_DEL_CARGADOR = (
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "LD_PRELOAD",
)


def _apunta_al_paquete(tramo: str, base: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(tramo), base]) == base
    except (OSError, ValueError):
        return False


def entorno_del_sistema() -> dict[str, str]:
    """Entorno limpio para lanzar programas ajenos a la aplicación.

    Al empaquetar con PyInstaller, el arranque mete la carpeta `_internal/` en
    `LD_LIBRARY_PATH` y guarda el valor previo en `LD_LIBRARY_PATH_ORIG`. Aquí
    se restaura ese valor previo; si no lo hay, se quitan solo los tramos que
    apuntan dentro del paquete y se deja el resto intacto.
    """
    entorno = dict(os.environ)
    base = getattr(sys, "_MEIPASS", None)
    base = os.path.realpath(base) if base else None

    for variable in _VARIABLES_DEL_CARGADOR:
        original = entorno.pop(f"{variable}_ORIG", None)
        if original is not None:
            if original:
                entorno[variable] = original
            else:
                entorno.pop(variable, None)
            continue

        actual = entorno.get(variable)
        if not actual or not base:
            continue
        restos = [
            tramo
            for tramo in actual.split(os.pathsep)
            if tramo and not _apunta_al_paquete(tramo, base)
        ]
        if restos:
            entorno[variable] = os.pathsep.join(restos)
        else:
            entorno.pop(variable, None)

    entorno.pop("_MEIPASS2", None)
    return entorno


def open_in_file_manager(path: Path) -> bool:
    """Abre la ruta con el programa que le corresponda en el sistema.

    Devuelve False si no se ha podido lanzar nada, para que quien llame
    pueda avisar en vez de quedarse callado.
    """
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        orden = ["open" if sys.platform == "darwin" else "xdg-open", str(path)]
        subprocess.Popen(
            orden,
            env=entorno_del_sistema(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (OSError, ValueError):
        return False
