"""Ledger incremental de rastreo para UniHub.

Registra cada intento de red de forma idempotente para poder reanudar,
auditar cobertura y distinguir errores temporales de resultados válidos.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import os
from datetime import datetime, timedelta, timezone

from config import CACHE_DB_PATH, SQLITE_CONNECT_TIMEOUT


class CrawlLedger:
    def __init__(self, db_path: str = CACHE_DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.RLock()
        self._init_db()

    def _connection(self):
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECT_TIMEOUT)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.connection = conn
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connection()
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_ledger_entity ON crawl_ledger(university_code, degree_code)")
            conn.commit()

    def record_attempt(self, url: str, *, phase: str = "", university_code: str = "", degree_code: str = ""):
        if not url:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connection()
            conn.execute(
                """INSERT INTO crawl_ledger(url, phase, university_code, degree_code, status, attempts, first_seen, last_attempt)
                   VALUES (?, ?, ?, ?, 'processing', 1, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET phase=excluded.phase,
                     university_code=excluded.university_code, degree_code=excluded.degree_code,
                     status='processing', attempts=crawl_ledger.attempts+1, last_attempt=excluded.last_attempt""",
                (url, phase, str(university_code or ""), str(degree_code or ""), now, now),
            )
            conn.commit()

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
            conn = self._connection()
            conn.execute(
                """UPDATE crawl_ledger SET status=?, http_status=?, content_type=?, content_length=?,
                   content_sha256=COALESCE(?, content_sha256), cache_path=COALESCE(?, cache_path),
                   etag=COALESCE(?, etag), last_modified=COALESCE(?, last_modified), error=?, last_attempt=?, next_retry=? WHERE url=?""",
                (final_status, status_code, content_type, len(content) if content else None,
                 digest, cache_path, headers.get("ETag"), headers.get("Last-Modified"), error, now, retry_at, url),
            )
            conn.commit()

    def validators(self, url: str) -> dict:
        with self._lock:
            row = self._connection().execute(
                "SELECT etag, last_modified, cache_path FROM crawl_ledger WHERE url=?", (url,)
            ).fetchone()
        if not row:
            return {}
        return {"etag": row[0], "last_modified": row[1], "cache_path": row[2]}

    def mark_cached(self, url: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._connection().execute(
                "UPDATE crawl_ledger SET status='success', error=NULL, last_attempt=?, next_retry=NULL WHERE url=?",
                (now, url),
            )
            self._connection().commit()

    def mark_robots(self, url: str, allowed: bool):
        with self._lock:
            conn = self._connection()
            conn.execute("UPDATE crawl_ledger SET robots_allowed=? WHERE url=?", (1 if allowed else 0, url))
            conn.commit()

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
            rows = self._connection().execute(query, args).fetchall()
        keys = ("url", "phase", "university_code", "degree_code", "status", "attempts", "next_retry")
        return [dict(zip(keys, row)) for row in rows]

    def close(self):
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
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
