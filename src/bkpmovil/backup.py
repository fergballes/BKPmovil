"""Motor de copia incremental. No depende de Qt: se puede usar desde la CLI."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .adb import Adb, AdbError, quote_remote
from .discovery import RemoteFile
from .index import BackupIndex
from .localfs import (
    free_space,
    long_path,
    relative_to_root,
    sanitize_component,
    sanitize_relative,
    unique_dir,
)
from .paths import ResolvedSource

#: Reintentos por fichero antes de darlo por fallido.
MAX_RETRIES = 3
RETRY_WAIT = (1.0, 3.0, 6.0)

#: Cada cuántos ficheros se vuelca el índice a disco (resistencia a cortes).
INDEX_FLUSH_EVERY = 100

#: Velocidad mínima asumida para calcular el tiempo máximo de un fichero.
MIN_BYTES_PER_SECOND = 20_000


def backup_folder_name(when: datetime | None = None) -> str:
    """Nombre de la carpeta de destino: bkp_DDMMYYYY."""
    return "bkp_" + (when or datetime.now()).strftime("%d%m%Y")


# --- Estructuras de progreso y resultado ------------------------------------


@dataclass
class Progress:
    phase: str  # preparando | copiando | finalizando | terminado
    message: str = ""
    folder: str = ""
    file_name: str = ""
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    folder_files_done: int = 0
    folder_files_total: int = 0
    speed: float = 0.0
    eta: float = 0.0

    @property
    def percent(self) -> int:
        if self.bytes_total > 0:
            return min(100, int(self.bytes_done * 100 / self.bytes_total))
        if self.files_total > 0:
            return min(100, int(self.files_done * 100 / self.files_total))
        return 0


@dataclass
class FolderResult:
    key: str
    label: str
    root: str
    dest_name: str
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_copied: int = 0
    subdirs: int = 0

    @property
    def scanned(self) -> int:
        return self.copied + self.skipped + self.failed


@dataclass
class BackupResult:
    dest: Path
    device: str = ""
    serial: str = ""
    started: datetime = field(default_factory=datetime.now)
    finished: datetime | None = None
    folders: list[FolderResult] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False
    incremental: bool = True

    @property
    def total_copied(self) -> int:
        return sum(f.copied for f in self.folders)

    @property
    def total_skipped(self) -> int:
        return sum(f.skipped for f in self.folders)

    @property
    def total_failed(self) -> int:
        return sum(f.failed for f in self.folders)

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes_copied for f in self.folders)

    @property
    def folders_with_content(self) -> list[FolderResult]:
        return [f for f in self.folders if f.copied > 0]

    @property
    def total_subdirs(self) -> int:
        return sum(f.subdirs for f in self.folders)

    @property
    def duration(self) -> float:
        end = self.finished or datetime.now()
        return (end - self.started).total_seconds()


class BackupCancelled(Exception):
    """La copia se ha cancelado desde la interfaz."""


ProgressFn = Callable[[Progress], None]
LogFn = Callable[[str], None]


def _noop_progress(_: Progress) -> None:
    return None


def _noop_log(_: str) -> None:
    return None


# --- Motor ------------------------------------------------------------------


class BackupEngine:
    """Copia las fuentes seleccionadas a `dest_root/bkp_DDMMYYYY`."""

    def __init__(
        self,
        adb: Adb,
        serial: str | None,
        dest_root: Path,
        sources: Sequence[ResolvedSource],
        index: BackupIndex,
        *,
        full: bool = False,
        verify_hash: bool = False,
        device_name: str = "",
        reconnect_target: str = "",
        on_progress: ProgressFn = _noop_progress,
        on_log: LogFn = _noop_log,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.dest_root = Path(dest_root)
        self.sources = [s for s in sources if s.enabled]
        self.index = index
        self.full = full
        self.verify_hash = verify_hash
        self.device_name = device_name
        self.reconnect_target = reconnect_target
        self.on_progress = on_progress
        self.on_log = on_log

        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._since_flush = 0

    # -- control -----------------------------------------------------------

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.clear()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def _checkpoint(self) -> None:
        while self._pause.is_set() and not self._cancel.is_set():
            time.sleep(0.15)
        if self._cancel.is_set():
            raise BackupCancelled

    # -- planificación -----------------------------------------------------

    def pending(self, source: ResolvedSource) -> list[RemoteFile]:
        """Ficheros de esta fuente que aún no están copiados."""
        if self.full:
            return list(source.files)
        return [f for f in source.files if not self.index.is_copied(f)]

    def plan(self) -> tuple[dict[str, list[RemoteFile]], int, int]:
        """Devuelve (pendientes por fuente, nº total de ficheros, bytes totales)."""
        pending: dict[str, list[RemoteFile]] = {}
        files_total = 0
        bytes_total = 0
        for source in self.sources:
            items = self.pending(source)
            pending[source.key] = items
            files_total += len(items)
            bytes_total += sum(f.size for f in items if f.size > 0)
        return pending, files_total, bytes_total

    def space_check(self, bytes_total: int) -> tuple[bool, int]:
        """(¿cabe?, bytes libres) en el destino."""
        available = free_space(self.dest_root)
        if available == 0:
            return True, 0
        return available > bytes_total * 1.02, available

    # -- ejecución ---------------------------------------------------------

    def run(self, when: datetime | None = None) -> BackupResult:
        pending, files_total, bytes_total = self.plan()

        dest = unique_dir(self.dest_root, backup_folder_name(when))
        dest.mkdir(parents=True, exist_ok=True)
        result = BackupResult(
            dest=dest,
            device=self.device_name,
            serial=self.serial or "",
            incremental=not self.full,
        )
        self.on_log(f"Destino: {dest}")
        self.on_log(
            f"{files_total} ficheros pendientes "
            f"({'copia completa' if self.full else 'copia incremental'})"
        )

        progress = Progress(
            phase="copiando",
            message="Preparando…",
            files_total=files_total,
            bytes_total=bytes_total,
        )
        self.on_progress(progress)
        start = time.monotonic()

        try:
            for source in self.sources:
                self._copy_source(source, pending[source.key], dest, result, progress, start)
        except BackupCancelled:
            result.cancelled = True
            self.on_log("Copia cancelada por el usuario. Lo copiado hasta ahora es válido.")
        finally:
            self.index.save()
            result.finished = datetime.now()
            progress.phase = "terminado"
            progress.message = "Cancelada" if result.cancelled else "Copia terminada"
            self.on_progress(progress)

        return result

    def _copy_source(
        self,
        source: ResolvedSource,
        files: list[RemoteFile],
        dest: Path,
        result: BackupResult,
        progress: Progress,
        start: float,
    ) -> None:
        folder = FolderResult(
            key=source.key,
            label=source.label,
            root=source.root,
            dest_name=source.dest_name,
        )
        result.folders.append(folder)
        folder.skipped = max(0, source.file_count - len(files))

        progress.folder = source.dest_name
        progress.folder_files_total = len(files)
        progress.folder_files_done = 0
        progress.message = f"Copiando {source.dest_name}"
        self.on_progress(progress)

        if not files:
            self.on_log(f"{source.dest_name}: sin novedades ({folder.skipped} ya copiados)")
            return

        self.on_log(f"{source.dest_name}: {len(files)} ficheros nuevos")
        base = dest / sanitize_component(source.dest_name)
        created_dirs: set[str] = set()

        for remote in files:
            self._checkpoint()
            relative = relative_to_root(remote.path, source.root)
            local = base / sanitize_relative(relative)
            parent_key = str(local.parent)
            if parent_key not in created_dirs:
                local.parent.mkdir(parents=True, exist_ok=True)
                created_dirs.add(parent_key)

            progress.file_name = remote.name
            progress.message = f"Copiando {source.dest_name}"
            self.on_progress(progress)

            ok, error = self._pull_with_retries(remote, local)
            if ok:
                folder.copied += 1
                folder.bytes_copied += max(0, remote.size)
                relative_in_backup = str(
                    Path(sanitize_component(source.dest_name)) / sanitize_relative(relative)
                )
                self.index.mark(remote, dest.name, relative_in_backup)
                self._since_flush += 1
                if self._since_flush >= INDEX_FLUSH_EVERY:
                    self.index.save()
                    self._since_flush = 0
            else:
                folder.failed += 1
                result.errors.append((remote.path, error))
                self.on_log(f"  ✗ {remote.path}: {error}")

            progress.files_done += 1
            progress.folder_files_done += 1
            progress.bytes_done += max(0, remote.size)
            elapsed = time.monotonic() - start
            progress.speed = progress.bytes_done / elapsed if elapsed > 0.5 else 0.0
            remaining = max(0, progress.bytes_total - progress.bytes_done)
            progress.eta = remaining / progress.speed if progress.speed > 1000 else 0.0
            self.on_progress(progress)

        folder.subdirs = len(created_dirs)

    def _pull_with_retries(self, remote: RemoteFile, local: Path) -> tuple[bool, str]:
        timeout = max(120, int(max(0, remote.size) / MIN_BYTES_PER_SECOND) + 60)
        last_error = ""
        for attempt in range(MAX_RETRIES):
            self._checkpoint()
            try:
                self.adb.pull(self.serial, remote.path, long_path(local), timeout=timeout)
                verified, problem = self._verify(remote, local)
                if verified:
                    return True, ""
                last_error = problem
            except AdbError as exc:
                last_error = str(exc).splitlines()[0] if str(exc) else "error de adb"

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_WAIT[min(attempt, len(RETRY_WAIT) - 1)])
                self._try_reconnect()
        return False, last_error or "no se pudo copiar"

    def _verify(self, remote: RemoteFile, local: Path) -> tuple[bool, str]:
        try:
            actual = local.stat().st_size
        except OSError as exc:
            return False, f"no se ha creado el fichero local ({exc.strerror or exc})"
        if remote.size >= 0 and actual != remote.size:
            return False, f"tamaño distinto (móvil {remote.size}, copia {actual})"
        if self.verify_hash and remote.size >= 0:
            return self._verify_hash(remote, local)
        return True, ""

    def _verify_hash(self, remote: RemoteFile, local: Path) -> tuple[bool, str]:
        try:
            out = self.adb.shell(
                self.serial, f"sha1sum {quote_remote(remote.path)}", timeout=180
            ).strip()
        except AdbError:
            return True, ""  # el móvil no tiene sha1sum: nos quedamos con el tamaño
        expected = out.split()[0] if out else ""
        if len(expected) != 40:
            return True, ""
        digest = hashlib.sha1()
        with open(long_path(local), "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            return False, "la verificación sha1 no coincide"
        return True, ""

    def _try_reconnect(self) -> None:
        if not self.serial:
            return
        try:
            if self.adb.is_online(self.serial):
                return
        except AdbError:
            pass
        target = self.reconnect_target or self.serial
        if ":" not in target:
            return
        host, _, port = target.rpartition(":")
        self.on_log("Conexión perdida, reintentando conectar con el móvil…")
        try:
            self.adb.connect(host, port)
            self.on_log("Reconectado.")
        except AdbError:
            pass


def rebuild_index_from_backups(
    index: BackupIndex,
    dest_root: Path,
    sources: Iterable[ResolvedSource],
) -> int:
    """Reconstruye el índice a partir de las copias ya existentes en disco.

    Sirve para recuperarse de la pérdida del índice sin volver a copiarlo
    todo. Se recorre al revés que la copia: para cada fichero del móvil se
    calcula dónde habría quedado y se mira si está y con el mismo tamaño.
    Así el saneado de nombres (obligatorio en Windows) no estorba, porque
    se aplica la misma función que usó la copia.

    `sources` tiene que venir ya analizado (con `files` relleno).
    """
    backups = sorted(
        (p for p in dest_root.glob("bkp_*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return 0

    recovered = 0
    for source in sources:
        carpeta = sanitize_component(source.dest_name)
        for remote in source.files:
            relative = sanitize_relative(relative_to_root(remote.path, source.root))
            for backup in backups:
                local = backup / carpeta / relative
                try:
                    stat = local.stat()
                except OSError:
                    continue
                if remote.size >= 0 and stat.st_size != remote.size:
                    continue
                index.entries[remote.path] = {
                    "size": remote.size if remote.size >= 0 else stat.st_size,
                    "mtime": remote.mtime,
                    "bkp": backup.name,
                    "rel": str(Path(carpeta) / relative),
                }
                recovered += 1
                break
    index.save()
    return recovered
