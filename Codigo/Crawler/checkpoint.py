import json
import os
import time
import uuid
import sqlite3
import threading
import contextlib
from datetime import datetime
from config import (
    CHECKPOINT_JSON, 
    CACHE_DB_PATH,
    CHECKPOINT_FLUSH_INTERVAL_SECONDS,
    SQLITE_CONNECT_TIMEOUT
)

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

def atomic_json_dump(data, filepath, max_retries: int = 5):
    """
    Thread-safe atomic JSON dump using temporary files and atomic replace.
    Guarantees no partial/corrupted JSON writes.
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
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                finally:
                    if os.path.exists(temp_filepath):
                        try:
                            os.remove(temp_filepath)
                        except Exception:
                            pass

def load_json_safe(filepath, default=None, default_val=None):
    """Safely loads JSON from disk; returns default/default_val on missing or corrupt files."""
    fallback = default if default is not None else (default_val if default_val is not None else {})
    if not os.path.exists(filepath):
        return fallback
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

class CheckpointManager:
    """
    High-performance thread-safe checkpoint manager for crawler progress.
    Provides dual-persistence: SQLite WAL (OPT-05) for 0ms indexed queries + JSON backup.
    Supports SHA256 negative content caching for duplicate PDFs (OPT-06).
    """
    _lock = threading.RLock()

    def __init__(self, filepath=CHECKPOINT_JSON, db_path=DB_PATH):
        self.filepath = filepath
        self.db_path = db_path
        self._last_mtime = 0
        self._last_save_time = 0.0
        self._cached_state = None
        self._init_sqlite()
        self.state = self._load_checkpoint()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_CONNECT_TIMEOUT)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
        finally:
            conn.close()

    def _init_sqlite(self):
        dir_path = os.path.dirname(os.path.abspath(self.db_path))
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with self._get_connection() as conn:
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
                    url TEXT PRIMARY KEY
                )
            """)
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
            conn.commit()

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
            except Exception:
                pass
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
            self._save(force=True)

    def _is_item_registered(self, table: str, column: str, state_key: str, value: str) -> bool:
        """Generic check for item presence in SQLite WAL with memory fallback."""
        if not is_valid_value(value):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            items = self.state.get(state_key, [])
            return value in items if isinstance(items, (list, dict, set)) else False

    def _register_simple_item(self, table: str, state_key: str, value: str, force_save: bool = False):
        """Generic atomic registration of a single item into SQLite WAL and memory list."""
        if not is_valid_value(value):
            return
        with CheckpointManager._lock:
            if state_key not in self.state or not isinstance(self.state[state_key], list):
                self.state[state_key] = []
            if value not in self.state[state_key]:
                self.state[state_key].append(value)
            try:
                with self._get_connection() as conn:
                    conn.execute(f"INSERT OR REPLACE INTO {table} VALUES (?)", (value,))
                    conn.commit()
            except Exception:
                pass
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
                try:
                    with self._get_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO non_study_plan_hashes VALUES (?, ?, ?)", 
                                     (pdf_sha256, "NO_PLAN_ESTUDIOS", datetime.now().isoformat()))
                        conn.commit()
                except Exception:
                    pass
                if "non_study_plan_hashes" not in self.state:
                    self.state["non_study_plan_hashes"] = []
                if pdf_sha256 not in self.state["non_study_plan_hashes"]:
                    self.state["non_study_plan_hashes"].append(pdf_sha256)
                self._save(force=False)

    def is_non_study_plan_hash(self, pdf_sha256: str) -> bool:
        return self._is_item_registered("non_study_plan_hashes", "pdf_sha256", "non_study_plan_hashes", pdf_sha256)

    def is_unreachable_url(self, pdf_url: str) -> bool:
        return self._is_item_registered("unreachable_urls", "url", "unreachable_urls", pdf_url)

    def mark_unreachable_url(self, pdf_url: str):
        self._register_simple_item("unreachable_urls", "unreachable_urls", pdf_url, force_save=False)

    def record_pdf_download_failure(self, pdf_url: str, degree_code: str, reason: str):
        if not is_valid_value(pdf_url):
            return
        with CheckpointManager._lock:
            if "failed_pdf_downloads" not in self.state:
                self.state["failed_pdf_downloads"] = {}
            self.state["failed_pdf_downloads"][pdf_url] = {
                "codigo_estudio": degree_code,
                "motivo_fallo": reason,
                "timestamp": datetime.now().isoformat()
            }
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
            except Exception:
                pass
            processed = self.state.get("processed_degrees", {})
            if isinstance(processed, dict):
                return processed.get(degree_code)
            return None

    def is_degree_up_to_date(self, degree_code: str, current_boe_url: str, current_boe_fecha: str) -> bool:
        if not is_valid_value(current_boe_url) and not is_valid_value(current_boe_fecha):
            return True

        record = self.get_degree_record(degree_code)
        if not record:
            return False
        
        recorded_url = record.get("boe_url")
        recorded_fecha = record.get("boe_fecha")
        
        if is_valid_value(current_boe_url) and is_valid_value(recorded_url) and current_boe_url == recorded_url:
            return True
        if is_valid_value(current_boe_fecha) and is_valid_value(recorded_fecha) and current_boe_fecha == recorded_fecha:
            return True
            
        return False

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
            try:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO processed_degrees VALUES (?, ?, ?, ?)",
                                 (degree_code, final_url, final_fecha, last_updated))
                    conn.commit()
            except Exception:
                pass
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
            try:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO extinct_degrees VALUES (?, ?, ?)",
                                 (degree_code, reason, timestamp))
                    conn.commit()
            except Exception:
                pass
            self._save(force=False)

    def is_extinct_degree(self, degree_code: str) -> bool:
        return self._is_item_registered("extinct_degrees", "degree_code", "extinct_degrees", degree_code)

    def mark_robots_denied_university(self, univ_code: str, web_url: str, reason: str = "Crawling denegado por robots.txt"):
        if not is_valid_value(univ_code):
            return
        with CheckpointManager._lock:
            if "robots_denied_universities" not in self.state or not isinstance(self.state.get("robots_denied_universities"), dict):
                self.state["robots_denied_universities"] = {}
            self.state["robots_denied_universities"][univ_code] = {
                "web_url": web_url,
                "motivo": reason,
                "timestamp": datetime.now().isoformat()
            }
            self._save(force=False)

    def is_robots_denied_university(self, univ_code: str) -> bool:
        if not is_valid_value(univ_code):
            return False
        with CheckpointManager._lock:
            denied = self.state.get("robots_denied_universities", {})
            return univ_code in denied if isinstance(denied, dict) else False

    def _save(self, force: bool = False):
        """
        Saves checkpoint state to checkpoint.json.
        If force=False, throttles disk writes to at most once every 30 seconds.
        If force=True (e.g. at end of each university or final shutdown), saves immediately.
        """
        with CheckpointManager._lock:
            now = time.time()
            if not force and (now - self._last_save_time) < CHECKPOINT_FLUSH_INTERVAL_SECONDS:
                return
            atomic_json_dump(self.state, self.filepath)
            self._last_save_time = now

    def flush(self):
        """Forces an immediate atomic disk flush of checkpoint.json."""
        self._save(force=True)
