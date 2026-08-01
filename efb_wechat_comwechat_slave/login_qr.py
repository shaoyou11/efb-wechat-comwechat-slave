import json
import threading
from pathlib import Path


def select_revoke_uids(records, now, ttl_seconds, completed):
    selected = []
    for record in records:
        uid = str(record.get("uid", "")).strip()
        if not uid:
            continue
        created_at = int(record.get("created_at", 0))
        if completed or now - created_at >= ttl_seconds:
            selected.append(uid)
    return selected


class LoginQrStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        records = []
        for record in data:
            if not isinstance(record, dict):
                continue
            uid = str(record.get("uid", "")).strip()
            try:
                created_at = int(record.get("created_at", 0))
            except (TypeError, ValueError):
                continue
            if uid:
                records.append({"uid": uid, "created_at": created_at})
        return records

    def _save(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def records(self):
        with self.lock:
            return self._load()

    def add(self, uid, created_at):
        uid = str(uid)
        with self.lock:
            records = [record for record in self._load() if record["uid"] != uid]
            records.append({"uid": uid, "created_at": int(created_at)})
            self._save(records)

    def remove(self, uid):
        uid = str(uid)
        with self.lock:
            records = [record for record in self._load() if record["uid"] != uid]
            self._save(records)
