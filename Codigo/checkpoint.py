import json
import os
from config import CHECKPOINT_JSON

class CheckpointManager:
    """
    Manages crawler progress state to allow resuming without duplicate requests.
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
            "processed_degrees": []
        }

    def mark_universities_downloaded(self):
        self.state["universities_downloaded"] = True
        self._save()

    def is_university_processed(self, univ_code: str) -> bool:
        return univ_code in self.state["processed_universities"]

    def mark_university_processed(self, univ_code: str):
        if univ_code not in self.state["processed_universities"]:
            self.state["processed_universities"].append(univ_code)
            self._save()

    def is_degree_processed(self, degree_code: str) -> bool:
        return degree_code in self.state["processed_degrees"]

    def mark_degree_processed(self, degree_code: str):
        if degree_code not in self.state["processed_degrees"]:
            self.state["processed_degrees"].append(degree_code)
            self._save()

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
