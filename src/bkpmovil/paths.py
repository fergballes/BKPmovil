"""Catálogo de rutas conocidas de Android y clasificación de ficheros.

Este módulo no habla con el dispositivo: solo describe *qué* buscar. La
resolución real (qué existe en este móvil concreto) vive en `discovery`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Extensiones ------------------------------------------------------------

IMAGE_EXT = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif",
     ".dng", ".raw", ".cr2", ".nef", ".arw", ".tif", ".tiff", ".avif"}
)
VIDEO_EXT = frozenset(
    {".mp4", ".3gp", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg",
     ".mpeg", ".wmv", ".flv", ".ts", ".m2ts"}
)
AUDIO_EXT = frozenset(
    {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".amr", ".wma"}
)
DOC_EXT = frozenset(
    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
     ".odt", ".ods", ".rtf", ".csv", ".epub", ".zip"}
)

#: Fotos y vídeos. Es el filtro que se aplica a las carpetas de mensajería.
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT

FILTER_SETS: dict[str, frozenset[str]] = {
    "media": MEDIA_EXT,
    "media_audio_docs": MEDIA_EXT | AUDIO_EXT | DOC_EXT,
    "todo": frozenset(),  # vacío == sin filtro
}


def matches_filter(name: str, exts: frozenset[str]) -> bool:
    """¿El fichero `name` pasa el filtro de extensiones dado?

    Un conjunto vacío significa «sin filtro».
    """
    if not exts:
        return True
    dot = name.rfind(".")
    if dot < 0:
        return False
    return name[dot:].lower() in exts


# --- Raíces de almacenamiento ----------------------------------------------

#: Candidatas al almacenamiento interno, en orden de preferencia.
STORAGE_ROOTS = ("/sdcard", "/storage/emulated/0", "/mnt/sdcard")


# --- Fuentes estándar -------------------------------------------------------


@dataclass(frozen=True)
class SourceSpec:
    """Una carpeta candidata a copiar.

    `candidates` son rutas relativas a la raíz de almacenamiento; se usa la
    primera que exista realmente en el dispositivo.
    """

    key: str
    label: str
    description: str
    candidates: tuple[str, ...]
    dest_name: str
    filter_key: str = "todo"
    default_enabled: bool = True


DEFAULT_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="dcim",
        label="Cámara y capturas (DCIM)",
        description="Las fotos y vídeos que has hecho con el móvil.",
        candidates=("DCIM",),
        dest_name="DCIM",
    ),
    SourceSpec(
        key="pictures",
        label="Imágenes (Pictures)",
        description="Imágenes guardadas por otras aplicaciones y capturas de pantalla.",
        candidates=("Pictures",),
        dest_name="Pictures",
    ),
    SourceSpec(
        key="movies",
        label="Vídeos (Movies)",
        description="Vídeos guardados fuera de la carpeta de la cámara.",
        candidates=("Movies", "Video", "Videos"),
        dest_name="Movies",
    ),
    SourceSpec(
        key="download",
        label="Descargas (Download)",
        description="Todo lo que has descargado con el navegador u otras apps.",
        candidates=("Download", "Downloads"),
        dest_name="Download",
    ),
    SourceSpec(
        key="documents",
        label="Documentos",
        description="Documentos guardados en el almacenamiento del móvil.",
        candidates=("Documents", "Documento"),
        dest_name="Documents",
    ),
    SourceSpec(
        key="screenshots",
        label="Capturas de pantalla",
        description="Carpeta propia de capturas en algunos móviles (Xiaomi, Samsung).",
        candidates=("Screenshots", "MIUI/screenshot", "Pictures/Screenshots"),
        dest_name="Screenshots",
    ),
    SourceSpec(
        key="recordings",
        label="Grabaciones de voz",
        description="Notas de voz y grabaciones de la grabadora.",
        candidates=("Recordings", "Record", "Sounds", "MIUI/sound_recorder"),
        dest_name="Recordings",
        default_enabled=False,
    ),
    SourceSpec(
        key="music",
        label="Música",
        description="Ficheros de música guardados en el móvil.",
        candidates=("Music",),
        dest_name="Music",
        default_enabled=False,
    ),
    SourceSpec(
        key="bluetooth",
        label="Recibido por Bluetooth",
        description="Ficheros que te han pasado por Bluetooth.",
        candidates=("Bluetooth", "bluetooth"),
        dest_name="Bluetooth",
        default_enabled=False,
    ),
)


# --- Mensajería: descubrimiento dinámico ------------------------------------


@dataclass(frozen=True)
class AppMediaSpec:
    """Aplicación de mensajería cuyas carpetas se buscan por nombre.

    En lugar de fijar rutas (que cambian entre versiones de Android y entre
    fabricantes), se busca cualquier carpeta cuyo nombre encaje con
    `dir_patterns` y se copian de ella solo fotos y vídeos.
    """

    key: str
    label: str
    dir_patterns: tuple[str, ...]
    dest_name: str
    filter_key: str = "media"
    default_enabled: bool = True


MESSAGING_APPS: tuple[AppMediaSpec, ...] = (
    AppMediaSpec(
        key="whatsapp",
        label="Fotos y vídeos de WhatsApp",
        dir_patterns=("*whatsapp*",),
        dest_name="WhatsApp",
    ),
    AppMediaSpec(
        key="telegram",
        label="Fotos y vídeos de Telegram",
        dir_patterns=("*telegram*",),
        dest_name="Telegram",
    ),
    AppMediaSpec(
        key="signal",
        label="Fotos y vídeos de Signal",
        dir_patterns=("*signal*",),
        dest_name="Signal",
        default_enabled=False,
    ),
)

#: Profundidad máxima al buscar carpetas de mensajería bajo la raíz.
#: /sdcard/Android/media/com.whatsapp/WhatsApp está a profundidad 4.
MESSAGING_SEARCH_DEPTH = 5

#: Rutas que nunca se recorren: son ruido o están bloqueadas sin root.
EXCLUDED_DIRS = (
    "Android/data",
    "Android/obb",
    ".thumbnails",
    "LOST.DIR",
    ".trashed",
)


def is_excluded(remote_path: str) -> bool:
    """¿Esta ruta remota cae en una carpeta que nunca queremos copiar?"""
    lowered = remote_path.lower()
    return any(("/" + d.lower() + "/") in lowered + "/" for d in EXCLUDED_DIRS)


@dataclass
class ResolvedSource:
    """Una fuente ya localizada en el dispositivo, lista para copiarse."""

    key: str
    label: str
    root: str
    dest_name: str
    filter_key: str = "todo"
    enabled: bool = True
    custom: bool = False
    file_count: int = 0
    total_bytes: int = 0
    files: list = field(default_factory=list, repr=False)

    @property
    def extensions(self) -> frozenset[str]:
        return FILTER_SETS.get(self.filter_key, frozenset())
