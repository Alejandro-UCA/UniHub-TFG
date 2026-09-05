"""Snapshot web aislado para campañas de extracción sin red.

La adquisición y el procesamiento son fases deliberadamente separadas:
``acquire`` es la única operación que puede consultar una URL; ``load`` y
``get`` trabajan exclusivamente con los bytes guardados en el snapshot.
Esto permite reproducir una campaña y demostrar que sus resultados no
dependen de cambios posteriores de las webs ni de nuevas peticiones.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit


class SnapshotMiss(KeyError):
    """La URL no forma parte del corpus descargado."""


@dataclass(frozen=True)
class SnapshotEntry:
    url: str
    final_url: str
    status_code: int
    content_type: str
    sha256: str
    byte_length: int
    relative_path: str
    error: str = ""


class InMemoryWebSnapshot:
    """Índice en memoria de respuestas web previamente descargadas."""

    def __init__(self, entries: dict[str, tuple[SnapshotEntry, bytes]] | None = None):
        self._entries = entries or {}
        self.network_calls = 0

    @staticmethod
    def _key(url: str) -> str:
        return str(url or "").strip().rstrip("/")

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def add(self, entry: SnapshotEntry, content: bytes) -> None:
        if entry.sha256 != hashlib.sha256(content).hexdigest():
            raise ValueError(f"Hash inconsistente para snapshot: {entry.url}")
        self._entries[self._key(entry.url)] = (entry, bytes(content))
        if entry.final_url:
            self._entries.setdefault(self._key(entry.final_url), (entry, bytes(content)))

    def get(self, url: str) -> tuple[SnapshotEntry, bytes]:
        key = self._key(url)
        try:
            return self._entries[key]
        except KeyError as exc:
            raise SnapshotMiss(url) from exc

    def content(self, url: str) -> bytes:
        return self.get(url)[1]

    def load_directory(self, directory: str | Path) -> "InMemoryWebSnapshot":
        root = Path(directory)
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for raw in manifest.get("entries", []):
            entry = SnapshotEntry(**raw)
            content = (root / entry.relative_path).read_bytes()
            self.add(entry, content)
        return self

    def save_directory(self, directory: str | Path) -> None:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        entries = []
        written = set()
        for entry, content in (item for item in self._entries.values()):
            if entry.url in written:
                continue
            written.add(entry.url)
            target = root / entry.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            entries.append(asdict(entry))
        (root / "manifest.json").write_text(
            json.dumps({"schema": 1, "entries": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def response_like(self, url: str):
        """Devuelve una respuesta mínima compatible con los parsers locales."""
        entry, content = self.get(url)

        class SnapshotResponse:
            def __init__(self, metadata, body):
                self.status_code = metadata.status_code
                self.url = metadata.final_url or metadata.url
                self.headers = {"Content-Type": metadata.content_type}
                self.content = body
                self.encoding = "utf-8"

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code} en snapshot: {self.url}")

            def iter_content(self, chunk_size=65536):
                for start in range(0, len(self.content), chunk_size):
                    yield self.content[start:start + chunk_size]

            def close(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        return SnapshotResponse(entry, content)


class DiskWebSnapshot(InMemoryWebSnapshot):
    """Reproduce corpus grandes leyendo y verificando un cuerpo cada vez."""

    def __init__(self):
        super().__init__()
        self._files = {}

    @property
    def urls(self):
        return tuple(self._files)

    def load_directory(self, directory):
        root = Path(directory).resolve()
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        for raw in manifest.get('entries', []):
            entry = SnapshotEntry(**raw)
            path = (root / entry.relative_path).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Ruta de cuerpo fuera del snapshot')
            self._files[self._key(entry.url)] = (entry, path)
            if entry.final_url:
                self._files.setdefault(self._key(entry.final_url), (entry, path))
        return self

    def get(self, url):
        try:
            entry, path = self._files[self._key(url)]
        except KeyError as exc:
            raise SnapshotMiss(url) from exc
        content = path.read_bytes()
        if len(content) != entry.byte_length or hashlib.sha256(content).hexdigest() != entry.sha256:
            raise ValueError(f'Integridad de snapshot inválida: {entry.url}')
        return entry, content


class SnapshotDownloader:
    """Adaptador estricto para ejecutar el crawler contra el snapshot.

    Implementa sólo la superficie que usa ``UniversityWebCrawler``. Nunca
    intenta resolver una ausencia: ``SnapshotMiss`` es intencionadamente
    visible para que una campaña no pueda salir del corpus local.
    """

    def __init__(self, snapshot: InMemoryWebSnapshot, **_kwargs):
        self.snapshot = snapshot
        self.timeout = float(_kwargs.get("timeout", 0.0) or 0.0)
        self.last_final_url = ""

    def set_degree_context(self, degree_code: str = "", degree_title: str = "") -> None:
        return None

    def reset_university_context(self) -> None:
        return None

    def fetch_content(self, url: str, max_size_bytes: int = 50_000_000) -> bytes:
        entry, body = self.snapshot.get(url)
        if entry.status_code >= 400:
            raise RuntimeError(f"HTTP {entry.status_code} en snapshot: {url}")
        if len(body) > max_size_bytes:
            raise ValueError(f"respuesta de snapshot superior a {max_size_bytes} bytes")
        self.last_final_url = entry.final_url or entry.url
        return body

    def fetch_text(self, url: str, encoding: str = "utf-8", max_size_bytes: int = 10_000_000, **_kwargs) -> str:
        body = self.fetch_content(url, max_size_bytes=max_size_bytes)
        return body.decode(encoding, errors="replace")

    def download_file(self, url: str, target_path: str, is_pdf: bool = False) -> str:
        body = self.fetch_content(url)
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return str(target)

    def close(self) -> None:
        return None


def _safe_filename(url: str, content_type: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in {".html", ".htm", ".pdf", ".json", ".xml", ".txt"}:
        suffix = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
    return f"{digest}{suffix}"


def acquire_snapshot(
    urls: Iterable[str],
    directory: str | Path,
    *,
    timeout: float = 20.0,
    max_bytes: int = 20_000_000,
    per_host_delay: float = 0.25,
    user_agent: str = "UniHub-research-snapshot/1.0 (+local audit)",
) -> dict:
    """Descarga una vez un conjunto acotado de URLs y deja un manifiesto.

    Se procesan URLs únicas en orden estable, con pausa por host y límite de
    tamaño. Los errores quedan auditados y no se reintentan indefinidamente.
    """
    import requests

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    unique = []
    seen = set()
    for raw in urls:
        url = str(raw or "").strip()
        key = url.rstrip("/")
        if not url or key in seen or urlsplit(url).scheme not in {"http", "https"}:
            continue
        seen.add(key)
        unique.append(url)

    snapshot = InMemoryWebSnapshot()
    manifest = {"schema": 1, "requested": len(unique), "downloaded": 0, "errors": [], "entries": []}
    last_host_at: dict[str, float] = {}
    host_lock = Lock()

    def download_one(url: str):
        host = urlsplit(url).netloc.lower()
        with host_lock:
            wait = per_host_delay - (time.monotonic() - last_host_at.get(host, 0.0))
            last_host_at[host] = time.monotonic() + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)
        session = requests.Session()
        session.headers.update({"User-Agent": user_agent, "Accept": "text/html,application/pdf,*/*;q=0.1"})
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length")
            if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                raise ValueError(f"Content-Length {content_length} supera {max_bytes}")
            chunks, total = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"respuesta superior a {max_bytes} bytes")
                chunks.append(chunk)
            content = b"".join(chunks)
            relative = f"bodies/{_safe_filename(url, content_type)}"
            entry = SnapshotEntry(
                url=url,
                final_url=str(response.url or url),
                status_code=int(response.status_code),
                content_type=content_type,
                sha256=hashlib.sha256(content).hexdigest(),
                byte_length=len(content),
                relative_path=relative,
            )
            response.close()
            return url, entry, content, None
        except Exception as exc:  # auditamos, pero no interrumpimos el lote
            return url, None, None, {"url": url, "error": str(exc)[:500]}

    # La concurrencia está acotada para que los hosts lentos no bloqueen todo
    # el lote. La pausa se serializa por host, no globalmente.
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="snapshot") as executor:
        futures = [executor.submit(download_one, url) for url in unique]
        for future in as_completed(futures):
            url, entry, content, error = future.result()
            if error is not None:
                manifest["errors"].append(error)
                continue
            snapshot.add(entry, content)
            manifest["entries"].append(asdict(entry))
            manifest["downloaded"] += 1
    manifest["entries"].sort(key=lambda item: item["url"])
    snapshot.save_directory(root)
    # ``manifest["entries"]`` conserva una entrada por respuesta obtenida,
    # incluso cuando la URL final de una redirección crea un alias en el
    # índice en memoria. No se reconstruye desde el índice porque ese índice
    # deduplica aliases y perderíamos cuerpos válidos del lote.
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def assert_snapshot_only(snapshot: InMemoryWebSnapshot) -> None:
    """Contrato de campaña: el lector en memoria nunca realiza red."""
    if snapshot.network_calls:
        raise AssertionError(f"El snapshot registró {snapshot.network_calls} peticiones de red")
