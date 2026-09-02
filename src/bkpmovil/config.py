"""Preferencias, perfiles de dispositivo y ubicación de los datos de la app."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "BKPmovil"


def app_dir() -> Path:
    """Carpeta donde la app guarda su configuración y sus índices."""
    override = os.environ.get("BKPMOVIL_HOME")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "bkpmovil"


def index_dir() -> Path:
    return app_dir() / "index"


def default_dest() -> Path:
    """Destino sugerido la primera vez."""
    for name in ("Copias BKPmovil",):
        for parent in (Path.home() / "Documentos", Path.home() / "Documents", Path.home()):
            if parent.exists():
                return parent / name
    return Path.home() / "Copias BKPmovil"


@dataclass
class DeviceProfile:
    """Un móvil recordado, para no repetir la vinculación cada vez."""

    name: str
    host: str = ""
    port: str = ""
    serial: str = ""
    paired: bool = False
    last_used: str = ""

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}" if self.host and self.port else ""


@dataclass
class Config:
    dest: str = ""
    profiles: list[DeviceProfile] = field(default_factory=list)
    custom_sources: list[dict] = field(default_factory=list)
    disabled_sources: list[str] = field(default_factory=list)
    verify_hash: bool = False
    keep_screen_hint: bool = True

    # -- persistencia ------------------------------------------------------

    @classmethod
    def path(cls) -> Path:
        return app_dir() / "config.json"

    @classmethod
    def load(cls) -> Config:
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(dest=str(default_dest()))
        profiles = [DeviceProfile(**p) for p in raw.get("profiles", []) if isinstance(p, dict)]
        return cls(
            dest=raw.get("dest") or str(default_dest()),
            profiles=profiles,
            custom_sources=list(raw.get("custom_sources", [])),
            disabled_sources=list(raw.get("disabled_sources", [])),
            verify_hash=bool(raw.get("verify_hash", False)),
            keep_screen_hint=bool(raw.get("keep_screen_hint", True)),
        )

    def save(self) -> None:
        target = self.path()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)

    # -- perfiles ----------------------------------------------------------

    def upsert_profile(self, profile: DeviceProfile) -> None:
        for i, existing in enumerate(self.profiles):
            if existing.name == profile.name:
                self.profiles[i] = profile
                return
        self.profiles.append(profile)

    def profile(self, name: str) -> DeviceProfile | None:
        return next((p for p in self.profiles if p.name == name), None)

    def remove_profile(self, name: str) -> None:
        self.profiles = [p for p in self.profiles if p.name != name]

    # -- fuentes -----------------------------------------------------------

    def is_disabled(self, key: str) -> bool:
        return key in self.disabled_sources

    def set_enabled(self, key: str, enabled: bool) -> None:
        if enabled:
            self.disabled_sources = [k for k in self.disabled_sources if k != key]
        elif key not in self.disabled_sources:
            self.disabled_sources.append(key)
