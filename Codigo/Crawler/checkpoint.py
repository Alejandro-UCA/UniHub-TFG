import json
import os
import uuid
import sqlite3
import threading
from datetime import datetime
from config import CHECKPOINT_JSON

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(CHECKPOINT_JSON)), "unihub_cache.sqlite3")

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

def atomic_json_dump(data, filepath):
    """
    Writes data to a thread-and-process-unique temporary file first 
    and replaces target file atomically. Ensures directory exists.
    """
    dir_path = os.path.dirname(os.path.abspath(filepath))
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    unique_id = f"{os.getpid()}_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"
    tmp_path = f"{filepath}.tmp.{unique_id}"
    
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e

def load_json_safe(filepath: str, default=None):
    """
    Safely reads a JSON file from disk if it exists.
    Returns the loaded data or default (empty dict by default) on failure/missing file.
    """
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

class CheckpointManager:
    """
    Manages crawler progress state and BOE metadata registry for incremental updates.
    Provides dual-persistence: SQLite WAL (OPT-05) for 0ms indexed queries + JSON backup.
    Supports SHA256 negative content caching for duplicate PDFs (OPT-06).
    """
    _lock = threading.RLock()

    def __init__(self, filepath=CHECKPOINT_JSON, db_path=DB_PATH):
        self.filepath = filepath
        self.db_path = db_path
        self._last_mtime = 0
        self._cached_state = None
        self._init_sqlite()
        self.state = self._load_checkpoint()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

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
            self._save()

    def is_university_processed(self, univ_code: str) -> bool:
        if not is_valid_value(univ_code):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT 1 FROM processed_universities WHERE univ_code = ?", (univ_code,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            return univ_code in self.state.get("processed_universities", [])

    def mark_university_processed(self, univ_code: str):
        if not is_valid_value(univ_code):
            return
        with CheckpointManager._lock:
            if "processed_universities" not in self.state:
                self.state["processed_universities"] = []
            if univ_code not in self.state["processed_universities"]:
                self.state["processed_universities"].append(univ_code)
            try:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO processed_universities VALUES (?)", (univ_code,))
                    conn.commit()
            except Exception:
                pass
            self._save()

    def is_non_study_plan_pdf(self, pdf_url: str) -> bool:
        if not is_valid_value(pdf_url):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT 1 FROM non_study_plan_pdfs WHERE pdf_url = ?", (pdf_url,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            return pdf_url in self.state.get("non_study_plan_pdfs", [])

    def mark_non_study_plan_pdf(self, pdf_url: str, pdf_sha256: str = None):
        if not is_valid_value(pdf_url):
            return
        with CheckpointManager._lock:
            if "non_study_plan_pdfs" not in self.state:
                self.state["non_study_plan_pdfs"] = []
            if pdf_url not in self.state["non_study_plan_pdfs"]:
                self.state["non_study_plan_pdfs"].append(pdf_url)
            try:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO non_study_plan_pdfs VALUES (?)", (pdf_url,))
                    if pdf_sha256:
                        conn.execute("INSERT OR REPLACE INTO non_study_plan_hashes VALUES (?, ?, ?)", 
                                     (pdf_sha256, "NO_PLAN_ESTUDIOS", datetime.now().isoformat()))
                        if "non_study_plan_hashes" not in self.state:
                            self.state["non_study_plan_hashes"] = []
                        if pdf_sha256 not in self.state["non_study_plan_hashes"]:
                            self.state["non_study_plan_hashes"].append(pdf_sha256)
                    conn.commit()
            except Exception:
                pass
            self._save()

    def is_non_study_plan_hash(self, pdf_sha256: str) -> bool:
        if not is_valid_value(pdf_sha256):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT 1 FROM non_study_plan_hashes WHERE pdf_sha256 = ?", (pdf_sha256,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            return pdf_sha256 in self.state.get("non_study_plan_hashes", [])

    def is_unreachable_url(self, pdf_url: str) -> bool:
        if not is_valid_value(pdf_url):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT 1 FROM unreachable_urls WHERE url = ?", (pdf_url,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            return pdf_url in self.state.get("unreachable_urls", [])

    def mark_unreachable_url(self, pdf_url: str):
        if not is_valid_value(pdf_url):
            return
        with CheckpointManager._lock:
            if "unreachable_urls" not in self.state:
                self.state["unreachable_urls"] = []
            if pdf_url not in self.state["unreachable_urls"]:
                self.state["unreachable_urls"].append(pdf_url)
            try:
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO unreachable_urls VALUES (?)", (pdf_url,))
                    conn.commit()
            except Exception:
                pass
            self._save()

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
            self._save()

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
            self._save()

    def is_extinct_degree(self, degree_code: str) -> bool:
        if not is_valid_value(degree_code):
            return False
        with CheckpointManager._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.execute("SELECT 1 FROM extinct_degrees WHERE degree_code = ?", (degree_code,))
                    if cur.fetchone():
                        return True
            except Exception:
                pass
            extinct = self.state.get("extinct_degrees", {})
            return degree_code in extinct if isinstance(extinct, dict) else False

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
            self._save()

    def is_robots_denied_university(self, univ_code: str) -> bool:
        if not is_valid_value(univ_code):
            return False
        with CheckpointManager._lock:
            denied = self.state.get("robots_denied_universities", {})
            return univ_code in denied if isinstance(denied, dict) else False

    def _save(self):
        with CheckpointManager._lock:
            atomic_json_dump(self.state, self.filepath)
