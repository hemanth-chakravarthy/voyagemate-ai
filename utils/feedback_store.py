import json
import os
from typing import Any, Dict, List


class FeedbackStore:
    def __init__(self, file_path: str = "./data/feedback.json") -> None:
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load(self) -> List[Dict[str, Any]]:
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, payload: List[Dict[str, Any]]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    def add_feedback(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load()
        data.append(entry)
        self._save(data)
        return entry
