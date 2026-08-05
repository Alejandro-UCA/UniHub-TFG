import json
import os
import uuid
import threading
from config import CHECKPOINT_JSON

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

class CheckpointManager:
    """
    Manages crawler progress state and BOE metadata registry for incremental updates.
    Enforces strict non-empty validation, thread locks, and atomic file replacements.
    """
    _lock = threading.Lock()

    def __init__(self, filepath=CHECKPOINT_JSON):
        self.filepath = filepath
        self._last_mtime = 0
        self._cached_state = None
        self.state = self._load_checkpoint()

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
                    if "failed_pdf_downloads" not in data:
                        data["failed_pdf_downloads"] = {}
                    if "unreachable_urls" not in data:
                        data["unreachable_urls"] = []
                    if "extinct_degrees" not in data:
                        data["extinct_degrees"] = {}
                    self._last_mtime = mtime
                    self._cached_state = data
                    return data
            except Exception:
                pass
        default_state = {
            "universities_downloaded": False,
            "processed_universities": [],
            "processed_degrees": {},  # Map: degree_code -> {"boe_url": ..., "boe_fecha": ..., "last_updated": ...}
            "non_study_plan_pdfs": [], # URLs de PDFs descartados por no ser de plan de estudios
            "failed_pdf_downloads": {}, # Mapa de URLs fallidas -> {degree_code, reason, timestamp}
            "unreachable_urls": [], # Lista de URLs confirmadas inalcanzables (HTTP + HTTPS rechazada)
            "extinct_degrees": {} # Mapa de titulaciones confirmadas extinguidas/inactivas -> {motivo, timestamp}
        }
        self._cached_state = default_state
        return default_state

    def mark_universities_downloaded(self):
        self.state["universities_downloaded"] = True
        self._save()

    def is_university_processed(self, univ_code: str) -> bool:
        with CheckpointManager._lock:
            disk_state = self._load_checkpoint()
            return univ_code in disk_state.get("processed_universities", []) or univ_code in self.state.get("processed_universities", [])

    def mark_university_processed(self, univ_code: str):
        if "processed_universities" not in self.state:
            self.state["processed_universities"] = []
        if univ_code not in self.state["processed_universities"]:
            self.state["processed_universities"].append(univ_code)
        self._save()

    def is_non_study_plan_pdf(self, pdf_url: str) -> bool:
        if not is_valid_value(pdf_url):
            return False
        with CheckpointManager._lock:
            disk_state = self._load_checkpoint()
            non_plans = set(disk_state.get("non_study_plan_pdfs", [])).union(set(self.state.get("non_study_plan_pdfs", [])))
            return pdf_url in non_plans

    def mark_non_study_plan_pdf(self, pdf_url: str):
        if not is_valid_value(pdf_url):
            return
        if "non_study_plan_pdfs" not in self.state:
            self.state["non_study_plan_pdfs"] = []
        if pdf_url not in self.state["non_study_plan_pdfs"]:
            self.state["non_study_plan_pdfs"].append(pdf_url)
            self._save()

    def is_unreachable_url(self, pdf_url: str) -> bool:
        if not is_valid_value(pdf_url):
            return False
        with CheckpointManager._lock:
            disk_state = self._load_checkpoint()
            unreachable = set(disk_state.get("unreachable_urls", [])).union(set(self.state.get("unreachable_urls", [])))
            return pdf_url in unreachable

    def mark_unreachable_url(self, pdf_url: str):
        if not is_valid_value(pdf_url):
            return
        if "unreachable_urls" not in self.state:
            self.state["unreachable_urls"] = []
        if pdf_url not in self.state["unreachable_urls"]:
            self.state["unreachable_urls"].append(pdf_url)
            self._save()

    def record_pdf_download_failure(self, pdf_url: str, degree_code: str, reason: str):
        if not is_valid_value(pdf_url):
            return
        if "failed_pdf_downloads" not in self.state:
            self.state["failed_pdf_downloads"] = {}
        self.state["failed_pdf_downloads"][pdf_url] = {
            "codigo_estudio": degree_code,
            "motivo_fallo": reason,
            "timestamp": datetime.now().isoformat()
        }
        self.mark_unreachable_url(pdf_url)

    def get_degree_record(self, degree_code: str) -> dict:
        disk_state = self._load_checkpoint()
        processed = disk_state.get("processed_degrees", self.state.get("processed_degrees", {}))
        if isinstance(processed, dict):
            return processed.get(degree_code)
        elif isinstance(processed, list):
            return {"boe_url": None, "boe_fecha": None} if degree_code in processed else None
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
        self._save()

    def mark_extinct_degree(self, degree_code: str, reason: str = "Extinguida"):
        if not is_valid_value(degree_code):
            return
        if "extinct_degrees" not in self.state or not isinstance(self.state.get("extinct_degrees"), dict):
            self.state["extinct_degrees"] = {}
        self.state["extinct_degrees"][degree_code] = {
            "motivo": reason,
            "timestamp": datetime.now().isoformat()
        }
        self._save()

    def is_extinct_degree(self, degree_code: str) -> bool:
        if not is_valid_value(degree_code):
            return False
        with CheckpointManager._lock:
            disk_state = self._load_checkpoint()
            extinct = disk_state.get("extinct_degrees", self.state.get("extinct_degrees", {}))
            if isinstance(extinct, dict):
                return degree_code in extinct
            return False

    def _save(self):
        with CheckpointManager._lock:
            # Merge state with disk to prevent concurrent overwrites
            if os.path.exists(self.filepath):
                try:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        disk_state = json.load(f)
                    
                    # Merge processed_universities
                    disk_univs = set(disk_state.get("processed_universities", []))
                    local_univs = set(self.state.get("processed_universities", []))
                    self.state["processed_universities"] = list(disk_univs.union(local_univs))
                    
                    # Merge processed_degrees
                    disk_degrees = disk_state.get("processed_degrees", {})
                    if isinstance(disk_degrees, dict):
                        if not isinstance(self.state.get("processed_degrees"), dict):
                            self.state["processed_degrees"] = {}
                        for k, v in disk_degrees.items():
                            if k not in self.state["processed_degrees"]:
                                self.state["processed_degrees"][k] = v

                    # Merge extinct_degrees
                    disk_extinct = disk_state.get("extinct_degrees", {})
                    if isinstance(disk_extinct, dict):
                        if not isinstance(self.state.get("extinct_degrees"), dict):
                            self.state["extinct_degrees"] = {}
                        for k, v in disk_extinct.items():
                            if k not in self.state["extinct_degrees"]:
                                self.state["extinct_degrees"][k] = v

                    # Merge non_study_plan_pdfs
                    disk_non_plans = set(disk_state.get("non_study_plan_pdfs", []))
                    local_non_plans = set(self.state.get("non_study_plan_pdfs", []))
                    self.state["non_study_plan_pdfs"] = list(disk_non_plans.union(local_non_plans))

                    # Merge failed_pdf_downloads
                    disk_failed = disk_state.get("failed_pdf_downloads", {})
                    if isinstance(disk_failed, dict):
                        if not isinstance(self.state.get("failed_pdf_downloads"), dict):
                            self.state["failed_pdf_downloads"] = {}
                        for k, v in disk_failed.items():
                            if k not in self.state["failed_pdf_downloads"]:
                                self.state["failed_pdf_downloads"][k] = v

                    # Merge unreachable_urls
                    disk_unreachable = set(disk_state.get("unreachable_urls", []))
                    local_unreachable = set(self.state.get("unreachable_urls", []))
                    self.state["unreachable_urls"] = list(disk_unreachable.union(local_unreachable))
                except Exception:
                    pass

            atomic_json_dump(self.state, self.filepath)
