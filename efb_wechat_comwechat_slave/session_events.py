import json
import threading
import time
from pathlib import Path


DEFAULT_EVENTS = {
    "last_login_at": None,
    "last_logout_at": None,
}


class SessionEventStore:
    """Persist the latest observed WeChat login and logout times."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return dict(DEFAULT_EVENTS)
        if not isinstance(data, dict):
            return dict(DEFAULT_EVENTS)
        events = dict(DEFAULT_EVENTS)
        for key in events:
            value = data.get(key)
            if value is None:
                continue
            try:
                events[key] = float(value)
            except (TypeError, ValueError):
                pass
        return events

    def _save(self, events):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def read(self):
        with self.lock:
            return self._load()

    def _record(self, key, timestamp=None):
        with self.lock:
            events = self._load()
            events[key] = float(time.time() if timestamp is None else timestamp)
            self._save(events)
            return events[key]

    def record_login(self, timestamp=None):
        return self._record("last_login_at", timestamp)

    def record_logout(self, timestamp=None):
        return self._record("last_logout_at", timestamp)
