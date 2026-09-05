import json
import os
import time
import uuid
import sqlite3
import logging
import threading
import contextlib
from datetime import datetime
from core.config import (
    CHECKPOINT_JSON, 
    CACHE_DB_PATH,
    CHECKPOINT_FLUSH_INTERVAL_SECONDS,
    SQLITE_CONNECT_TIMEOUT,
    NEGATIVE_CACHE_TTL_SECONDS,
)
from sqlite_recovery import is_sqlite_corruption, quarantine_corrupt_sqlite

logger = logging.getLogger("CheckpointManager")
DB_PATH = CACHE_DB_PATH

def is_valid_value(val) -> bool:
    """
    Returns True ONLY if val is a meaningful non-empty, non-undefined string/data.
    Rejects None, empty string '', whitespace, 'undefined', 'null', 'n/a', 'nan'.
    """
    if val is None:
        return False
    s = str(val).strip().lower()
    if s in ["", "none", "null", "undefined", "n/a", "nan"]:
        return False
    return True


def _checkpoint_timestamp_is_fresh(timestamp: str | None, max_age_seconds: float) -> bool:
    """Valida la antigüedad de una marca ISO sin romper checkpoints antiguos."""
    try:
        if max_age_seconds < 0:
            return False
        raw = str(timestamp or "").strip()
        if not raw:
            return False
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        now = datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.now()
        age = (now - parsed).total_seconds()
        return age <= max_age_seconds
    except (TypeError, ValueError, OverflowError):
        # Un registro legado sin fecha no debe bloquear indefinidamente la
        # recuperación: se trata como caducado cuando se usa un TTL.
        return False

def atomic_json_dump(data, filepath, max_retries: int = 5):
    """
    Thread-safe atomic JSON dump using temporary files and atomic replace.
    Guarantees no partial/corrupted JSON writes without hardware fsync stalls.
    """
    temp_filepath = f"{filepath}.tmp.{uuid.uuid4().hex}"
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            with open(temp_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_filepath, filepath)
            return
        except (PermissionError, OSError) as e:
            if attempt < max_retries - 1:
                time.sleep(0.05 * (2 ** attempt))
            else:
                if os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except OSError as cleanup_error:
                        logger.warning("No se pudo eliminar el temporal del checkpoint %s: %s", temp_filepath, cleanup_error)
                raise

def load_json_safe(filepath, default=None, default_val=None):
    """Safely loads JSON from disk; returns default/default_val on missing or corrupt files."""
    fallback = default if default is not None else (default_val if default_val is not None else {})
    if not os.path.exists(filepath):
        return fallback
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading JSON from {filepath}: {e}")
        return fallback

_STATIC_SELECT_QUERIES = {
    ("processed_universities", "univ_code"): "SELECT 1 FROM processed_universities WHERE univ_code = ?",
    ("non_study_plan_pdfs", "pdf_url"): "SELECT 1 FROM non_study_plan_pdfs WHERE pdf_url = ?",
    ("non_study_plan_hashes", "pdf_sha256"): "SELECT 1 FROM non_study_plan_hashes WHERE pdf_sha256 = ?",
    ("unreachable_urls", "url"): "SELECT 1 FROM unreachable_urls WHERE url = ?",
    ("extinct_degrees", "degree_code"): "SELECT 1 FROM extinct_degrees WHERE degree_code = ?",
    ("failed_pdf_downloads", "url"): "SELECT 1 FROM failed_pdf_downloads WHERE url = ?",
    ("robots_denied_universities", "univ_code"): "SELECT 1 FROM robots_denied_universities WHERE univ_code = ?",
}

_STATIC_INSERT_QUERIES = {
    "processed_universities": "INSERT OR REPLACE INTO processed_universities (univ_code) VALUES (?)",
    "non_study_plan_pdfs": "INSERT OR REPLACE INTO non_study_plan_pdfs (pdf_url) VALUES (?)",
    "non_study_plan_hashes": "INSERT OR REPLACE INTO non_study_plan_hashes (pdf_sha256) VALUES (?)",
    "unreachable_urls": "INSERT OR REPLACE INTO unreachable_urls (url) VALUES (?)",
    "robots_denied_universities": "INSERT OR REPLACE INTO robots_denied_universities (univ_code) VALUES (?)",
}

class CheckpointManager:
    """
    High-performance thread-safe and multi-process consistent checkpoint manager for crawler progress.
    Provides dual-persistence: SQLite WAL (OPT-05) for 0ms indexed queries + JSON backup.
    Supports SHA256 negative content caching for duplicate PDFs (OPT-06).
    """
    _lock = threading.RLock()
    _local = threading.local()

    def __init__(self, filepath=None, db_path=None):
        import core.config as config
        self.filepath = filepath or config.CHECKPOINT_JSON
        self.db_path = db_path or config.CACHE_DB_PATH
        # SQLite es una optimización del checkpoint JSON. Si el fichero está
        # dañado o el volumen no permite abrirlo, la ejecución debe continuar
        # usando el estado en memoria y el volcado JSON.
        self._sqlite_disabled = False
        self._sqlite_disable_reason = None
        self.sqlite_recovered_corrupt_path = None
        self._recovering_sqlite = False
        # Cada instancia mantiene sus propias conexiones por hilo. Compartir
        # el almacenamiento de conexiones entre gestores podía dejar a una
        # instancia usando una conexión cerrada por otra durante la
        # recuperación de SQLite.
        self._local = threading.local()
        self._last_mtime = 0
        self._last_save_time = 0.0
        self._cached_state = None
        self._init_sqlite()
        self.state = self._load_checkpoint()

    def _disable_sqlite(self, error: Exception):
        """Recupera una SQLite corrupta o desactiva SQLite si no es recuperable."""
        if not self._recovering_sqlite and is_sqlite_corruption(error):
            try:
                quarantine_path = quarantine_corrupt_sqlite(self.db_path)
            except OSError as recovery_error:
                quarantine_path = None
                logger.error(
                    "No se pudo poner en cuarentena el checkpoint SQLite corrupto %s: %s",
                    self.db_path,
                    recovery_error,
                )
            if quarantine_path:
                self.sqlite_recovered_corrupt_path = quarantine_path
                self._recovering_sqlite = True
                self._sqlite_disabled = False
                self._sqlite_disable_reason = None
                try:
                    self._init_sqlite()
                finally:
                    self._recovering_sqlite = False
                if not self._sqlite_disabled:
                    logger.warning(
                        "Checkpoint SQLite corrupto apartado en %s y reemplazado por una base nueva",
                        quarantine_path,
                    )
                    return
        if not self._sqlite_disabled:
            logger.warning(
                "SQLite del checkpoint no disponible en %s; se continúa con JSON: %s",
                self.db_path,
                error,
            )
        self._sqlite_disabled = True
        self._sqlite_disable_reason = str(error)
        conns = getattr(self._local, "connections", None)
        if conns and self.db_path in conns:
            conn = conns.pop(self.db_path)
            try:
                conn.close()
            except Exception:
                pass

    @contextlib.contextmanager
    def _get_connection(self):
        """Thread-local persistent SQLite WAL connection with in-memory page cache."""
        if self._sqlite_disabled:
            raise sqlite3.DatabaseError(self._sqlite_disable_reason or "SQLite desactivado")
        conns = getattr(self._local, "connections", None)
        if conns is None:
            conns = {}
            self._local.connections = conns

        if self.db_path not in conns:
            conn = None
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=SQLITE_CONNECT_TIMEOUT,
                    check_same_thread=False,
                )
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute(f"PRAGMA busy_timeout={max(1000, int(SQLITE_CONNECT_TIMEOUT * 1000))};")
                conn.execute("PRAGMA temp_store=MEMORY;")
                conn.execute("PRAGMA mmap_size=268435456;")
                conn.execute("PRAGMA cache_size=-64000;")
                integrity_rows = conn.execute("PRAGMA integrity_check;").fetchall()
                if not integrity_rows or any(
                    str(row[0]).strip().lower() != "ok" for row in integrity_rows
                ):
                    raise sqlite3.DatabaseError(
                        "database disk image is malformed: integrity check failed"
                    )
                conns[self.db_path] = conn
            except (OSError, sqlite3.Error) as error:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                self._disable_sqlite(error)
                if self._sqlite_disabled:
                    raise
                # La recuperación ha creado y preparado una conexión nueva.
                # No propagamos la excepción de apertura del fichero antiguo.
                conns = getattr(self._local, "connections", {})
                if self.db_path not in conns:
                    raise

        conn = conns[self.db_path]
        try:
            yield conn
        except Exception as e:
            try:
                conn.rollback()
            except Exception as error:
                logger.warning("No se pudo leer el checkpoint SQLite/JSON; se usará el estado seguro por defecto: %s", error)
            if isinstance(e, sqlite3.Error):
                self._disable_sqlite(e)
            logger.debug(f"Error en transacción SQLite checkpoint: {e}")
            raise

    def _init_sqlite(self):
        try:
            dir_path = os.path.dirname(os.path.abspath(self.db_path))
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with self._get_connection() as conn:
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                except Exception:
                    pass
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_degrees (
                        degree_code TEXT PRIMARY KEY,
                        boe_url TEXT,
                        boe_fecha TEXT,
                        last_updated TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS non_study_plan_pdfs (
                        pdf_url TEXT PRIMARY KEY
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS non_study_plan_hashes (
                        pdf_sha256 TEXT PRIMARY KEY,
                        reason TEXT,
                        timestamp TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS unreachable_urls (
                        url TEXT PRIMARY KEY,
                        marked_at TEXT
                    )
                """)
                try:
                    conn.execute("ALTER TABLE unreachable_urls ADD COLUMN marked_at TEXT")
                except sqlite3.OperationalError:
                    pass
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS extinct_degrees (
                        degree_code TEXT PRIMARY KEY,
                        motivo TEXT,
                        timestamp TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_universities (
                        univ_code TEXT PRIMARY KEY
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS failed_pdf_downloads (
                        url TEXT PRIMARY KEY,
                        degree_code TEXT,
                        reason TEXT,
                        timestamp TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS robots_denied_universities (
                        univ_code TEXT PRIMARY KEY,
                        web_url TEXT,
                        reason TEXT,
                        timestamp TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            self._disable_sqlite(e)

    def _load_checkpoint(self):
        if os.path.exists(self.filepath):
            try:
                mtime = os.path.getmtime(self.filepath)
                if self._cached_state and mtime == self._last_mtime:
                    return self._cached_state

                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "non_study_plan_pdfs" not in data:
                        data["non_study_plan_pdfs"] = []
                    if "non_study_plan_hashes" not in data:
                        data["non_study_plan_hashes"] = []
                    if "failed_pdf_downloads" not in data:
                        data["failed_pdf_downloads"] = {}
                    if "unreachable_urls" not in data:
                        data["unreachable_urls"] = []
                    if "extinct_degrees" not in data:
                        data["extinct_degrees"] = {}
                    if "robots_denied_universities" not in data:
                        data["robots_denied_universities"] = {}
                    self._last_mtime = mtime
                    self._cached_state = data
                    return data
            except Exception as error:
                logger.debug("No se pudo consultar la caché de URLs inaccesibles: %s", error, exc_info=True)
        default_state = {
            "universities_downloaded": False,
            "processed_universities": [],
            "processed_degrees": {},
            "non_study_plan_pdfs": [],
            "non_study_plan_hashes": [],
            "failed_pdf_downloads": {},
            "unreachable_urls": [],
            "extinct_degrees": {},
            "robots_denied_universities": {}
        }
        self._cached_state = default_state
        return default_state

    def mark_universities_downloaded(self):
        with CheckpointManager._lock:
            self.state["universities_downloaded"] = True
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO app_metadata VALUES (?, ?)", ("universities_downloaded", "1"))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar universities_downloaded en SQLite: {e}")
            self._save(force=True)

    def _is_item_registered(self, table: str, column: str, state_key: str, value: str) -> bool:
        """Generic check for item presence in SQLite WAL with memory fallback."""
        if not is_valid_value(value):
            return False
        query = _STATIC_SELECT_QUERIES.get((table, column))
        if not query:
            raise ValueError(f"Consulta estática no definida para tabla='{table}', columna='{column}'.")
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute(query, (value,))
                    if cur.fetchone():
                        return True
            except Exception as e:
                logger.debug(f"Error al consultar tabla {table} en SQLite: {e}")
            items = self.state.get(state_key, [])
            return value in items if isinstance(items, (list, dict, set)) else False

    def _register_simple_item(self, table: str, state_key: str, value: str, force_save: bool = False):
        """Generic atomic registration of a single item into SQLite WAL and memory list."""
        if not is_valid_value(value):
            return
        query = _STATIC_INSERT_QUERIES.get(table)
        if not query:
            raise ValueError(f"Sentencia INSERT estática no definida para tabla='{table}'.")
        with CheckpointManager._lock:
            if state_key not in self.state or not isinstance(self.state[state_key], list):
                self.state[state_key] = []
            if value not in self.state[state_key]:
                self.state[state_key].append(value)
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute(query, (value,))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar en tabla {table} en SQLite: {e}")
            self._save(force=force_save)

    def is_university_processed(self, univ_code: str) -> bool:
        return self._is_item_registered("processed_universities", "univ_code", "processed_universities", univ_code)

    def mark_university_processed(self, univ_code: str):
        self._register_simple_item("processed_universities", "processed_universities", univ_code, force_save=True)

    def is_non_study_plan_pdf(self, pdf_url: str) -> bool:
        return self._is_item_registered("non_study_plan_pdfs", "pdf_url", "non_study_plan_pdfs", pdf_url)

    def mark_non_study_plan_pdf(self, pdf_url: str, pdf_sha256: str = None):
        if not is_valid_value(pdf_url):
            return
        self._register_simple_item("non_study_plan_pdfs", "non_study_plan_pdfs", pdf_url, force_save=False)
        if pdf_sha256:
            with CheckpointManager._lock:
                if not self._sqlite_disabled:
                    try:
                        with self._get_connection() as conn:
                            conn.execute("INSERT OR REPLACE INTO non_study_plan_hashes VALUES (?, ?, ?)",
                                         (pdf_sha256, "NO_PLAN_ESTUDIOS", datetime.now().isoformat()))
                            conn.commit()
                    except Exception as e:
                        logger.warning(f"Error al registrar hash en SQLite: {e}")
                if "non_study_plan_hashes" not in self.state:
                    self.state["non_study_plan_hashes"] = []
                if pdf_sha256 not in self.state["non_study_plan_hashes"]:
                    self.state["non_study_plan_hashes"].append(pdf_sha256)
                self._save(force=False)

    def is_non_study_plan_hash(self, pdf_sha256: str) -> bool:
        return self._is_item_registered("non_study_plan_hashes", "pdf_sha256", "non_study_plan_hashes", pdf_sha256)

    def is_unreachable_url(self, pdf_url: str) -> bool:
        if not is_valid_value(pdf_url):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    row = conn.execute("SELECT marked_at FROM unreachable_urls WHERE url = ?", (pdf_url,)).fetchone()
                    if row:
                        if not row[0]:
                            return False
                        try:
                            age = time.time() - datetime.fromisoformat(row[0]).timestamp()
                            return age < NEGATIVE_CACHE_TTL_SECONDS
                        except (TypeError, ValueError, OSError):
                            return False
            except Exception as error:
                logger.warning("No se pudo consultar el registro de URLs inalcanzables: %s", error, exc_info=True)
            # Sin marca temporal fiable se fuerza un nuevo intento.
            return False

    def mark_unreachable_url(self, pdf_url: str):
        if not is_valid_value(pdf_url):
            return
        now = datetime.now().isoformat()
        with CheckpointManager._lock:
            items = self.state.setdefault("unreachable_urls", [])
            if pdf_url not in items:
                items.append(pdf_url)
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO unreachable_urls (url, marked_at) VALUES (?, ?)", (pdf_url, now))
                        conn.commit()
                except Exception as exc:
                    logger.warning("Error al registrar URL inalcanzable: %s", exc)
            self._save(force=False)

    def record_pdf_download_failure(self, pdf_url: str, degree_code: str, reason: str):
        if not is_valid_value(pdf_url):
            return
        with CheckpointManager._lock:
            if "failed_pdf_downloads" not in self.state:
                self.state["failed_pdf_downloads"] = {}
            now_iso = datetime.now().isoformat()
            self.state["failed_pdf_downloads"][pdf_url] = {
                "codigo_estudio": degree_code,
                "motivo_fallo": reason,
                "timestamp": now_iso
            }
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO failed_pdf_downloads VALUES (?, ?, ?, ?)",
                                     (pdf_url, degree_code, reason, now_iso))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar fallo de descarga PDF en SQLite: {e}")
            self.mark_unreachable_url(pdf_url)

    def get_degree_record(self, degree_code: str) -> dict:
        if not is_valid_value(degree_code):
            return None
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT boe_url, boe_fecha, last_updated FROM processed_degrees WHERE degree_code = ?", (degree_code,))
                    row = cur.fetchone()
                    if row:
                        return {"boe_url": row[0], "boe_fecha": row[1], "last_updated": row[2]}
            except Exception as e:
                logger.debug(f"Error al consultar degree record en SQLite: {e}")
            processed = self.state.get("processed_degrees", {})
            if isinstance(processed, dict):
                return processed.get(degree_code)
            return None

    def is_degree_up_to_date(self, degree_code: str, current_boe_url: str, current_boe_fecha: str) -> bool:
        if not is_valid_value(current_boe_url) and not is_valid_value(current_boe_fecha):
            return False

        record = self.get_degree_record(degree_code)
        if not record:
            return False
        
        recorded_url = record.get("boe_url")
        recorded_fecha = record.get("boe_fecha")
        
        comparisons = []
        if is_valid_value(current_boe_url):
            comparisons.append(is_valid_value(recorded_url) and current_boe_url == recorded_url)
        if is_valid_value(current_boe_fecha):
            comparisons.append(is_valid_value(recorded_fecha) and current_boe_fecha == recorded_fecha)

        # Cuando se conocen ambos identificadores, ambos deben coincidir. Así
        # no se omite una actualización por conservar solo una URL o una fecha.
        return bool(comparisons) and all(comparisons)

    def update_degree_record(self, degree_code: str, boe_url: str, boe_fecha: str, last_updated: str):
        if not is_valid_value(degree_code):
            return
        with CheckpointManager._lock:
            if not isinstance(self.state.get("processed_degrees"), dict):
                self.state["processed_degrees"] = {}
                
            existing = self.state["processed_degrees"].get(degree_code, {})
            final_url = boe_url if is_valid_value(boe_url) else existing.get("boe_url")
            final_fecha = boe_fecha if is_valid_value(boe_fecha) else existing.get("boe_fecha")
            
            self.state["processed_degrees"][degree_code] = {
                "boe_url": final_url,
                "boe_fecha": final_fecha,
                "last_updated": last_updated
            }
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO processed_degrees VALUES (?, ?, ?, ?)",
                                     (degree_code, final_url, final_fecha, last_updated))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar processed_degrees en SQLite: {e}")
            self._save(force=False)

    def mark_extinct_degree(self, degree_code: str, reason: str = "Extinguida"):
        if not is_valid_value(degree_code):
            return
        with CheckpointManager._lock:
            if "extinct_degrees" not in self.state or not isinstance(self.state.get("extinct_degrees"), dict):
                self.state["extinct_degrees"] = {}
            timestamp = datetime.now().isoformat()
            self.state["extinct_degrees"][degree_code] = {
                "motivo": reason,
                "timestamp": timestamp
            }
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO extinct_degrees VALUES (?, ?, ?)",
                                     (degree_code, reason, timestamp))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar extinct_degrees en SQLite: {e}")
            self._save(force=False)

    def is_extinct_degree(self, degree_code: str) -> bool:
        return self._is_item_registered("extinct_degrees", "degree_code", "extinct_degrees", degree_code)

    def mark_robots_denied_university(self, univ_code: str, web_url: str, reason: str = "Crawling denegado por robots.txt"):
        if not is_valid_value(univ_code):
            return
        with CheckpointManager._lock:
            if "robots_denied_universities" not in self.state or not isinstance(self.state.get("robots_denied_universities"), dict):
                self.state["robots_denied_universities"] = {}
            now_iso = datetime.now().isoformat()
            self.state["robots_denied_universities"][univ_code] = {
                "web_url": web_url,
                "motivo": reason,
                "timestamp": now_iso
            }
            if not self._sqlite_disabled:
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO robots_denied_universities VALUES (?, ?, ?, ?)",
                                     (univ_code, web_url, reason, now_iso))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Error al registrar robots_denied_universities en SQLite: {e}")
            self._save(force=False)

    def is_robots_denied_university(self, univ_code: str, max_age_seconds: float | None = None) -> bool:
        """Indica si existe un bloqueo vigente para la universidad.

        Los bloqueos persistidos son una protección contra reintentos
        inmediatos, no una prohibición permanente. Cuando se proporciona
        ``max_age_seconds``, un registro sin fecha válida o más antiguo que
        ese límite se considera caducado y permite revalidar robots.txt.
        ``None`` conserva la semántica histórica de bloqueo permanente para
        los consumidores que aún no necesitan TTL.
        """
        if not is_valid_value(univ_code):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute(
                        "SELECT timestamp FROM robots_denied_universities WHERE univ_code = ?",
                        (univ_code,),
                    )
                    row = cur.fetchone()
                    if row:
                        if max_age_seconds is None:
                            return True
                        return _checkpoint_timestamp_is_fresh(row[0], max_age_seconds)
            except Exception as error:
                logger.warning("No se pudo consultar robots_denied_universities para %s: %s", univ_code, error, exc_info=True)
            denied = self.state.get("robots_denied_universities", {})
            if not isinstance(denied, dict) or univ_code not in denied:
                return False
            if max_age_seconds is None:
                return True
            entry = denied.get(univ_code)
            timestamp = entry.get("timestamp") if isinstance(entry, dict) else None
            return _checkpoint_timestamp_is_fresh(timestamp, max_age_seconds)

    def _consolidate_state_from_sqlite(self) -> dict:
        """Consolida el estado global leyendo directamente de SQLite WAL para consistencia multi-proceso."""
        state = dict(self.state)
        if self._sqlite_disabled:
            return state
        try:
            with self._get_connection() as conn:
                # 1. processed_universities
                cur = conn.execute("SELECT univ_code FROM processed_universities")
                state["processed_universities"] = [r[0] for r in cur.fetchall()]
                
                # 2. processed_degrees
                cur = conn.execute("SELECT degree_code, boe_url, boe_fecha, last_updated FROM processed_degrees")
                state["processed_degrees"] = {
                    r[0]: {"boe_url": r[1], "boe_fecha": r[2], "last_updated": r[3]}
                    for r in cur.fetchall()
                }
                
                # 3. non_study_plan_pdfs
                cur = conn.execute("SELECT pdf_url FROM non_study_plan_pdfs")
                state["non_study_plan_pdfs"] = [r[0] for r in cur.fetchall()]
                
                # 4. non_study_plan_hashes
                cur = conn.execute("SELECT pdf_sha256 FROM non_study_plan_hashes")
                state["non_study_plan_hashes"] = [r[0] for r in cur.fetchall()]
                
                # 5. unreachable_urls
                cur = conn.execute("SELECT url FROM unreachable_urls")
                state["unreachable_urls"] = [r[0] for r in cur.fetchall()]
                
                # 6. extinct_degrees
                cur = conn.execute("SELECT degree_code, motivo, timestamp FROM extinct_degrees")
                state["extinct_degrees"] = {
                    r[0]: {"motivo": r[1], "timestamp": r[2]}
                    for r in cur.fetchall()
                }
                
                # 7. failed_pdf_downloads
                cur = conn.execute("SELECT url, degree_code, reason, timestamp FROM failed_pdf_downloads")
                state["failed_pdf_downloads"] = {
                    r[0]: {"codigo_estudio": r[1], "motivo_fallo": r[2], "timestamp": r[3]}
                    for r in cur.fetchall()
                }
                
                # 8. robots_denied_universities
                cur = conn.execute("SELECT univ_code, web_url, reason, timestamp FROM robots_denied_universities")
                state["robots_denied_universities"] = {
                    r[0]: {"web_url": r[1], "motivo": r[2], "timestamp": r[3]}
                    for r in cur.fetchall()
                }
                
                # 9. app_metadata
                cur = conn.execute("SELECT key, value FROM app_metadata")
                for k, v in cur.fetchall():
                    if k == "universities_downloaded":
                        state["universities_downloaded"] = (v == "1" or v.lower() == "true")
        except Exception as e:
            logger.warning(f"Error al consolidar estado desde SQLite: {e}")
            if isinstance(e, sqlite3.Error):
                self._disable_sqlite(e)
        return state

    def _save(self, force: bool = False):
        """
        Saves checkpoint state to checkpoint.json.
        If force=False, throttles disk writes to at most once every 30 seconds.
        If force=True (e.g. at end of each university or final shutdown), saves immediately.
        Consolidates state from SQLite WAL to guarantee multi-process consistency.
        """
        with CheckpointManager._lock:
            now = time.time()
            if not force and (now - self._last_save_time) < CHECKPOINT_FLUSH_INTERVAL_SECONDS:
                return
            consolidated = self._consolidate_state_from_sqlite()
            atomic_json_dump(consolidated, self.filepath)
            self._last_save_time = now

    def flush(self):
        """Forces an immediate atomic disk flush of checkpoint.json."""
        self._save(force=True)

    def close(self):
        """Closes thread-local SQLite connections and flushes pending state."""
        try:
            self.flush()
        except Exception as error:
            logger.error("No se pudo cerrar/volcar el checkpoint: %s", error, exc_info=True)
        conns = getattr(self._local, "connections", None)
        if conns:
            for conn in list(conns.values()):
                try:
                    conn.close()
                except Exception as error:
                    logger.warning("No se pudo cerrar una conexión SQLite del checkpoint: %s", error, exc_info=True)
            conns.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
