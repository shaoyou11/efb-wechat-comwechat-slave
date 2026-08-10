import json
import threading
import time
from pathlib import Path


class SessionEventStore:
    VERSION = 1

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _migrate(data):
        if data.get("version") == SessionEventStore.VERSION:
            return data
        migrated = {}
        for key in ("last_login_at", "last_logout_at"):
            if data.get(key) is not None:
                migrated[f"legacy_{key}"] = data[key]
        return migrated

    def observe(self, logged_in, observed_at=None):
        state = "online" if bool(logged_in) else "offline"
        observed_at = time.time() if observed_at is None else float(observed_at)
        with self.lock:
            stored = self._load()
            if (
                stored.get("version") == self.VERSION
                and stored.get("current_state") == state
            ):
                return False
            data = self._migrate(stored)
            previous_state = data.get("current_state")
            data["version"] = self.VERSION
            data.setdefault("tracking_started_at", observed_at)
            data["current_state"] = state
            data["last_observed_at"] = observed_at

            transitioned = previous_state in {"online", "offline"} and previous_state != state
            if transitioned:
                key = "last_login_at" if state == "online" else "last_logout_at"
                data[key] = observed_at
            self._save(data)
            return transitioned

    def record(self, logged_in, observed_at=None):
        state = "online" if bool(logged_in) else "offline"
        observed_at = time.time() if observed_at is None else float(observed_at)
        with self.lock:
            data = self._migrate(self._load())
            data["version"] = self.VERSION
            data.setdefault("tracking_started_at", observed_at)
            data["current_state"] = state
            data["last_observed_at"] = observed_at
            key = "last_login_at" if state == "online" else "last_logout_at"
            data[key] = observed_at
            self._save(data)
