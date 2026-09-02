"""Índice incremental: recuerda qué ficheros ya se copiaron y en qué copia."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import index_dir
from .discovery import RemoteFile

SCHEMA = 1


def device_key(serial: str, model: str = "") -> str:
    """Nombre de fichero estable para un dispositivo."""
    raw = f"{model}_{serial}".strip("_ ") or "dispositivo"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw)[:80]


class BackupIndex:
    """Registro persistente de lo ya copiado, por dispositivo.

    La clave es la ruta en el móvil. Un fichero se considera ya copiado si
    coinciden ruta, tamaño y fecha de modificación; si el móvil no ha sabido
    darnos metadatos, basta con la ruta.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict] = {}
        self._load()

    # -- carga y guardado --------------------------------------------------

    @classmethod
    def for_device(cls, serial: str, model: str = "") -> BackupIndex:
        return cls(index_dir() / f"{device_key(serial, model)}.json")

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
            self.entries = raw["entries"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "entries": self.entries}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # -- consulta ----------------------------------------------------------

    def is_copied(self, remote: RemoteFile) -> bool:
        entry = self.entries.get(remote.path)
        if entry is None:
            return False
        if not remote.metadata_known:
            return True
        if int(entry.get("size", -1)) != remote.size:
            return False
        recorded = int(entry.get("mtime", -1))
        if recorded < 0:
            return True
        return remote.mtime <= recorded

    def where(self, remote_path: str) -> str:
        return str(self.entries.get(remote_path, {}).get("bkp", ""))

    # -- actualización -----------------------------------------------------

    def mark(self, remote: RemoteFile, backup_name: str, relative: str) -> None:
        self.entries[remote.path] = {
            "size": remote.size,
            "mtime": remote.mtime,
            "bkp": backup_name,
            "rel": relative,
        }

    def forget(self, remote_path: str) -> None:
        self.entries.pop(remote_path, None)

    def clear(self) -> None:
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)
