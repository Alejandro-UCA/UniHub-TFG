import json
import os
from config import CHECKPOINT_JSON

class CheckpointManager:
    """
    Manages crawler progress state and BOE metadata registry for incremental updates.
    Allows inspecting all universities/degrees while avoiding unnecessary PDF re-downloads.
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
        """Returns the stored BOE metadata record for a degree, if any."""
        processed = self.state.get("processed_degrees", {})
        if isinstance(processed, dict):
            return processed.get(degree_code)
        elif isinstance(processed, list):
            # Backward compatibility migration from old list format
            return {"boe_url": None, "boe_fecha": None} if degree_code in processed else None
        return None

    def is_degree_up_to_date(self, degree_code: str, current_boe_url: str, current_boe_fecha: str) -> bool:
        """
        Checks if the degree has already been processed with the EXACT SAME BOE URL/Date.
        If current_boe_url matches recorded boe_url, return True (no re-download needed).
        """
        record = self.get_degree_record(degree_code)
        if not record:
            return False
        
        recorded_url = record.get("boe_url")
        recorded_fecha = record.get("boe_fecha")
        
        if current_boe_url and recorded_url == current_boe_url:
            return True
        if current_boe_fecha and recorded_fecha == current_boe_fecha:
            return True
            
        return False

    def update_degree_record(self, degree_code: str, boe_url: str, boe_fecha: str, last_updated: str):
        if not isinstance(self.state.get("processed_degrees"), dict):
            self.state["processed_degrees"] = {}
            
        self.state["processed_degrees"][degree_code] = {
            "boe_url": boe_url,
            "boe_fecha": boe_fecha,
            "last_updated": last_updated
        }
        self._save()

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
