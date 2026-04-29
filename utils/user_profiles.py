import json
import os
from typing import Any, Dict, Optional


DEFAULT_PROFILE = {
    "budget_range": "mid",
    "travel_style": "backpacking",
    "preferred_places": [],
    "food_preference": "veg",
}


class UserProfileStore:
    def __init__(self, file_path: str = "./data/user_profiles.json") -> None:
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _load(self) -> Dict[str, Any]:
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, payload: Dict[str, Any]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)

    def get_profile(self, user_id: str) -> Dict[str, Any]:
        data = self._load()
        profile = data.get(user_id, {})
        merged = {**DEFAULT_PROFILE, **profile}
        merged["user_id"] = user_id
        return merged

    def upsert_profile(self, user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load()
        existing = data.get(user_id, {})
        updated = {**existing, **profile}
        updated["user_id"] = user_id
        data[user_id] = updated
        self._save(data)
        return updated
