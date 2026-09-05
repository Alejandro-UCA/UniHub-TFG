"""Ledger incremental de rastreo para UniHub.

Registra cada intento de red de forma idempotente para poder reanudar,
auditar cobertura y distinguir errores temporales de resultados válidos.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import os
from datetime import datetime, timedelta, timezone

from core.config import CACHE_DB_PATH, SQLITE_CONNECT_TIMEOUT, LEDGER_WRITE_BATCH_SIZE
from sqlite_recovery import is_sqlite_corruption, quarantine_corrupt_sqlite

logger = logging.getLogger(__name__)


class CrawlLedger:
    def __init__(self, db_path: str | None = None):
        # El ledger y el checkpoint tienen patrones de escritura distintos.
        # Separarlos evita que un lote de auditoría mantenga bloqueado el
        # archivo principal del checkpoint. Se conserva db_path explícito para
        # integraciones y pruebas que necesiten una base compartida.
        if db_path:
            self.db_path = db_path
        else:
            import core.config as config
            configured_cache = config.CACHE_DB_PATH
            default_ledger_path = os.path.join(
                os.path.dirname(os.path.abspath(configured_cache)),
                "crawl_ledger.sqlite3",
            )
            self.db_path = os.getenv("CRAWLER_LEDGER_DB_PATH", "").strip() or default_ledger_path
        self._local = threading.local()
        self._lock = threading.RLock()
        self._disabled = False
        self._disable_reason = None
        self.recovered_corrupt_path = None
        self._recovering = False
        # Una única conexión por ledger. Todas las operaciones públicas están
        # protegidas por _lock, por lo que no se necesitan transacciones
        # concurrentes y se evita que SQLite mantenga varios escritores en
        # espera dentro de la misma instancia.
        self._shared_connection = None
        self._connections = {}
        self._pending_writes = {}
        self._init_db()

    def _disable(self, err: Exception):
        """Desactiva el ledger de esta instancia sin modificar un fichero dañado."""
        if not self._recovering and is_sqlite_corruption(err):
            try:
                quarantine_path = quarantine_corrupt_sqlite(self.db_path)
            except OSError as recovery_error:
                quarantine_path = None
                logger.error("No se pudo poner en cuarentena el ledger SQLite corrupto %s: %s", self.db_path, recovery_error)
            if quarantine_path:
                self.recovered_corrupt_path = quarantine_path
                self._recovering = True
                self._disabled = False
                self._disable_reason = None
                self.close()
                try:
                    self._init_db()
                finally:
                    self._recovering = False
                if not self._disabled:
                    logger.warning(
                        "Ledger SQLite corrupto apartado en %s y reemplazado por una base nueva",
                        quarantine_path,
                    )
                    return
        if not self._disabled:
            logger.warning(
                "Ledger SQLite no disponible en %s; se continúa sin caché transaccional: %s",
                self.db_path,
                err,
            )
        self._disabled = True
        self._disable_reason = str(err)
        self.close()

    def _ensure_parent_directory(self) -> bool:
        if not self.db_path or self.db_path == ":memory:":
            return True
        try:
            parent = os.path.dirname(os.path.abspath(self.db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            return True
        except OSError as err:
            self._disable(err)
            return False

    def _connection(self):
        if self._disabled:
            return None
        conn = self._shared_connection
        if conn is None:
            if not self._ensure_parent_directory():
                return None
            conn = None
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=SQLITE_CONNECT_TIMEOUT,
                    check_same_thread=False,
                )
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute(f"PRAGMA busy_timeout={max(1000, int(SQLITE_CONNECT_TIMEOUT * 1000))}")
                self._shared_connection = conn
                self._connections[0] = conn
                self._pending_writes[id(conn)] = 0
            except sqlite3.Error as err:
                if conn is not None:
                    conn.close()
                self._disable(err)
                return None
        return conn

    def _mark_write(self, conn) -> None:
        """Confirma por lotes para reducir bloqueos/fsync sin perder el flush final."""
        key = id(conn)
        self._pending_writes[key] = self._pending_writes.get(key, 0) + 1
        batch_size = max(1, int(LEDGER_WRITE_BATCH_SIZE))
        if self._pending_writes[key] >= batch_size:
            conn.commit()
            self._pending_writes[key] = 0

    def _flush_connections(self) -> None:
        """Confirma todas las conexiones conocidas antes de leer/cerrar el ledger."""
        for conn in list(self._connections.values()):
            try:
                if self._pending_writes.get(id(conn), 0):
                    conn.commit()
                    self._pending_writes[id(conn)] = 0
            except sqlite3.Error as err:
                # Este método también se usa durante _disable()/close(). No debe
                # volver a invocar _disable(), pues provocaría una recursión al
                # cerrar una conexión bloqueada o dañada.
                logger.warning("No se pudo confirmar una conexión SQLite del ledger: %s", err)
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                self._pending_writes[id(conn)] = 0

    def _init_db(self):
        with self._lock:
            conn = self._connection()
            if conn is None:
                return
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            try:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS crawl_ledger (
                        url TEXT PRIMARY KEY,
                        phase TEXT,
                        university_code TEXT,
                        degree_code TEXT,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        http_status INTEGER,
                        content_type TEXT,
                        content_length INTEGER,
                        content_sha256 TEXT,
                        cache_path TEXT,
                        cache_updated_at TEXT,
                        etag TEXT,
                        last_modified TEXT,
                        robots_allowed INTEGER,
                        error TEXT,
                        first_seen TEXT NOT NULL,
                        last_attempt TEXT,
                        next_retry TEXT
                    )"""
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_ledger_status ON crawl_ledger(status, next_retry)")
                try:
                    conn.execute("ALTER TABLE crawl_ledger ADD COLUMN cache_path TEXT")
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute("ALTER TABLE crawl_ledger ADD COLUMN cache_updated_at TEXT")
                except sqlite3.OperationalError:
                    pass
                conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_ledger_entity ON crawl_ledger(university_code, degree_code)")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS discovery_evidence (
                        url TEXT PRIMARY KEY,
                        university_code TEXT NOT NULL DEFAULT '',
                        phase TEXT NOT NULL DEFAULT '',
                        source_kind TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT '',
                        anchor_text TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        heading TEXT NOT NULL DEFAULT '',
                        lastmod TEXT NOT NULL DEFAULT '',
                        content_type TEXT NOT NULL DEFAULT '',
                        content_sha256 TEXT NOT NULL DEFAULT '',
                        robots_allowed INTEGER,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_discovery_evidence_univ "
                    "ON discovery_evidence(university_code, last_seen)"
                )
                conn.commit()
            except sqlite3.Error as err:
                self._disable(err)

    def record_attempt(self, url: str, *, phase: str = "", university_code: str = "", degree_code: str = ""):
        if not url:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return
                conn.execute(
                    """INSERT INTO crawl_ledger(url, phase, university_code, degree_code, status, attempts, first_seen, last_attempt)
                       VALUES (?, ?, ?, ?, 'processing', 1, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET phase=excluded.phase,
                         university_code=excluded.university_code, degree_code=excluded.degree_code,
                         status='processing', attempts=crawl_ledger.attempts+1, last_attempt=excluded.last_attempt""",
                    (url, phase, str(university_code or ""), str(degree_code or ""), now, now),
                )
                self._mark_write(conn)
            except sqlite3.Error as err:
                self._disable(err)

    def record_response(self, url: str, response=None, *, content: bytes | None = None, status: str | None = None, error: str | None = None, cache_path: str | None = None):
        if not url:
            return
        now = datetime.now(timezone.utc).isoformat()
        status_code = getattr(response, "status_code", None)
        content_type = getattr(response, "headers", {}).get("Content-Type") if response is not None else None
        headers = getattr(response, "headers", {}) if response is not None else {}
        digest = hashlib.sha256(content).hexdigest() if content else None
        final_status = status or ("success" if status_code is not None and 200 <= status_code < 400 else "failed")
        retry_at = None
        if final_status == "failed":
            retry_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return
                conn.execute(
                    """UPDATE crawl_ledger SET status=?, http_status=?, content_type=?, content_length=?,
                       content_sha256=COALESCE(?, content_sha256), cache_path=COALESCE(?, cache_path),
                       cache_updated_at=COALESCE(?, cache_updated_at),
                       etag=COALESCE(?, etag), last_modified=COALESCE(?, last_modified), error=?, last_attempt=?, next_retry=? WHERE url=?""",
                    (final_status, status_code, content_type, len(content) if content else None,
                     digest, cache_path, now if (content or cache_path) else None,
                     headers.get("ETag"), headers.get("Last-Modified"), error, now, retry_at, url),
                )
                self._mark_write(conn)
            except sqlite3.Error as err:
                self._disable(err)

    def validators(self, url: str) -> dict:
        if not url:
            return {}
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return {}
                row = conn.execute(
                    "SELECT etag, last_modified, cache_path, cache_updated_at FROM crawl_ledger WHERE url=?", (url,)
                ).fetchone()
                if not row:
                    return {}
                return {
                    "etag": row[0],
                    "last_modified": row[1],
                    "cache_path": row[2],
                    "cache_updated_at": row[3],
                }
            except sqlite3.Error as err:
                self._disable(err)
                return {}

    def record_discovery_evidence(
        self,
        records,
        *,
        university_code: str = "",
        phase: str = "",
    ) -> int:
        """Persiste evidencias de URLs académicas de forma idempotente."""
        if not records:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        written = 0
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return 0
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    url = str(record.get("url") or "").strip()
                    if not url:
                        continue
                    conn.execute(
                        """INSERT INTO discovery_evidence(
                            url, university_code, phase, source_kind, source_url,
                            anchor_text, title, heading, lastmod, content_type,
                            content_sha256, robots_allowed, first_seen, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(url) DO UPDATE SET
                            university_code=COALESCE(NULLIF(excluded.university_code, ''), discovery_evidence.university_code),
                            phase=COALESCE(NULLIF(excluded.phase, ''), discovery_evidence.phase),
                            source_kind=COALESCE(NULLIF(excluded.source_kind, ''), discovery_evidence.source_kind),
                            source_url=COALESCE(NULLIF(excluded.source_url, ''), discovery_evidence.source_url),
                            anchor_text=COALESCE(NULLIF(excluded.anchor_text, ''), discovery_evidence.anchor_text),
                            title=COALESCE(NULLIF(excluded.title, ''), discovery_evidence.title),
                            heading=COALESCE(NULLIF(excluded.heading, ''), discovery_evidence.heading),
                            lastmod=COALESCE(NULLIF(excluded.lastmod, ''), discovery_evidence.lastmod),
                            content_type=COALESCE(NULLIF(excluded.content_type, ''), discovery_evidence.content_type),
                            content_sha256=COALESCE(NULLIF(excluded.content_sha256, ''), discovery_evidence.content_sha256),
                            robots_allowed=COALESCE(excluded.robots_allowed, discovery_evidence.robots_allowed),
                            last_seen=excluded.last_seen""",
                        (
                            url,
                            str(university_code or "").strip(),
                            str(phase or record.get("phase") or "").strip(),
                            str(record.get("source_kind") or "").strip(),
                            str(record.get("source_url") or "").strip(),
                            str(record.get("anchor_text") or "").strip(),
                            str(record.get("title") or "").strip(),
                            str(record.get("heading") or "").strip(),
                            str(record.get("lastmod") or "").strip(),
                            str(record.get("content_type") or "").strip(),
                            str(record.get("content_sha256") or "").strip(),
                            record.get("robots_allowed"),
                            now,
                            now,
                        ),
                    )
                    written += 1
                    self._mark_write(conn)
                return written
            except sqlite3.Error as err:
                self._disable(err)
                return 0

    def get_discovery_evidence(
        self,
        university_code: str,
        *,
        limit: int = 5000,
        max_age_seconds: int | None = None,
    ) -> list[dict]:
        """Recupera evidencias académicas reutilizables para una universidad."""
        with self._lock:
            try:
                self._flush_connections()
                conn = self._connection()
                if conn is None:
                    return []
                query = (
                    "SELECT url, university_code, phase, source_kind, source_url, "
                    "anchor_text, title, heading, lastmod, content_type, "
                    "content_sha256, robots_allowed, first_seen, last_seen "
                    "FROM discovery_evidence WHERE university_code=?"
                )
                args: list = [str(university_code or "").strip()]
                if max_age_seconds is not None and int(max_age_seconds) > 0:
                    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=int(max_age_seconds))).isoformat()
                    query += " AND last_seen >= ?"
                    args.append(cutoff)
                query += " ORDER BY last_seen DESC, url LIMIT ?"
                args.append(max(1, int(limit)))
                rows = conn.execute(query, args).fetchall()
                keys = (
                    "url", "university_code", "phase", "source_kind", "source_url",
                    "anchor_text", "title", "heading", "lastmod", "content_type",
                    "content_sha256", "robots_allowed", "first_seen", "last_seen",
                )
                return [dict(zip(keys, row)) for row in rows]
            except sqlite3.Error as err:
                self._disable(err)
                return []

    def mark_cached(self, url: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return
                conn.execute(
                    "UPDATE crawl_ledger SET status='success', error=NULL, last_attempt=?, next_retry=NULL WHERE url=?",
                    (now, url),
                )
                self._mark_write(conn)
            except sqlite3.Error as err:
                self._disable(err)

    def mark_robots(self, url: str, allowed: bool, reason: str | None = None):
        """Registra robots y cierra la solicitud si el acceso está denegado."""
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return
                if allowed:
                    conn.execute("UPDATE crawl_ledger SET robots_allowed=1 WHERE url=?", (url,))
                else:
                    conn.execute(
                        """UPDATE crawl_ledger
                           SET robots_allowed=0, status='robots_denied',
                               error=COALESCE(?, error), next_retry=NULL,
                               last_attempt=?
                         WHERE url=?""",
                        (reason or "robots.txt deniega el rastreo", datetime.now(timezone.utc).isoformat(), url),
                    )
                self._mark_write(conn)
            except sqlite3.Error as err:
                self._disable(err)

    def mark_robots_denied(self, url: str, reason: str | None = None):
        """Alias explícito para consumidores que necesitan un estado terminal."""
        self.mark_robots(url, False, reason=reason)

    def reconcile_processing(self, *, phase_prefix: str | None = None, reason: str = "fase cerrada") -> int:
        """Convierte intentos huérfanos ``processing`` en ``cancelled``.

        Un intento puede quedar abierto si una señal interrumpe un worker entre
        ``record_attempt`` y la respuesta. ``processing`` no es reanudable de
        forma segura porque no distingue un intento activo de uno huérfano;
        se cierra al finalizar la fase y el siguiente run podrá reintentarlo
        como una nueva solicitud.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                conn = self._connection()
                if conn is None:
                    return 0
                query = (
                    "UPDATE crawl_ledger SET status='cancelled', error=COALESCE(error, ?), "
                    "last_attempt=?, next_retry=NULL WHERE status='processing'"
                )
                args = [reason, now]
                if phase_prefix:
                    query += " AND phase LIKE ?"
                    args.append(f"{phase_prefix}%")
                cursor = conn.execute(query, args)
                self._mark_write(conn)
                return max(0, int(cursor.rowcount or 0))
            except sqlite3.Error as err:
                self._disable(err)
                return 0

    def pending(self, *, phase: str | None = None, limit: int = 100) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        query = "SELECT url, phase, university_code, degree_code, status, attempts, next_retry FROM crawl_ledger WHERE status IN ('processing', 'failed') AND (next_retry IS NULL OR next_retry <= ?)"
        args: list = [now]
        if phase:
            query += " AND phase=?"
            args.append(phase)
        query += " ORDER BY last_attempt IS NOT NULL, last_attempt LIMIT ?"
        args.append(max(1, int(limit)))
        with self._lock:
            try:
                self._flush_connections()
                conn = self._connection()
                if conn is None:
                    return []
                rows = conn.execute(query, args).fetchall()
                keys = ("url", "phase", "university_code", "degree_code", "status", "attempts", "next_retry")
                return [dict(zip(keys, row)) for row in rows]
            except sqlite3.Error as err:
                self._disable(err)
                return []

    def close(self):
        with self._lock:
            self._flush_connections()
            for conn in list(self._connections.values()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
            self._pending_writes.clear()
            self._shared_connection = None
        self._local.connection = None

    @staticmethod
    def prune_http_cache(directory: str, max_bytes: int):
        """Elimina entradas antiguas hasta mantener la caché bajo el presupuesto."""
        if not directory or max_bytes <= 0 or not os.path.isdir(directory):
            return
        files = []
        total = 0
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if not os.path.isfile(path) or not name.endswith(".body"):
                continue
            try:
                size = os.path.getsize(path)
                files.append((os.path.getmtime(path), path, size))
                total += size
            except OSError:
                continue
        if total <= max_bytes:
            return
        for _, path, size in sorted(files):
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass
            if total <= max_bytes:
                break
