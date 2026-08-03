import json
import os
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
    """Writes data to a temporary file first and replaces target file atomically."""
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)

class CheckpointManager:
    """
    Manages crawler progress state and BOE metadata registry for incremental updates.
    Enforces strict non-empty validation and atomic file replacements for concurrency safety.
    """
    def __init__(self, filepath=CHECKPOINT_JSON):
        self.filepath = filepath
        self.state = self._load_checkpoint()

    def _load_checkpoint(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "universities_downloaded": False,
            "processed_universities": [],
            "processed_degrees": {},  # Map: degree_code -> {"boe_url": ..., "boe_fecha": ..., "last_updated": ...}
        }

    def mark_universities_downloaded(self):
        self.state["universities_downloaded"] = True
        self._save()

    def is_university_processed(self, univ_code: str) -> bool:
        return univ_code in self.state.get("processed_universities", [])

    def mark_university_processed(self, univ_code: str):
        if "processed_universities" not in self.state:
            self.state["processed_universities"] = []
        if univ_code not in self.state["processed_universities"]:
            self.state["processed_universities"].append(univ_code)
            self._save()

    def get_degree_record(self, degree_code: str) -> dict:
        processed = self.state.get("processed_degrees", {})
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

    def _save(self):
        atomic_json_dump(self.state, self.filepath)
