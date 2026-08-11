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


def _matches_stack_generation(record, stack_generation):
    if stack_generation is None:
        return True
    return str(record.get("stack_generation", "")).strip() == str(
        stack_generation
    ).strip()


def has_active_qr(records, now, ttl_seconds, stack_generation=None):
    for record in records:
        try:
            created_at = int(record.get("created_at", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if (
            _matches_stack_generation(record, stack_generation)
            and now - created_at < ttl_seconds
        ):
            return True
    return False


def has_recent_qr(records, now, grace_seconds, stack_generation=None):
    for record in records:
        try:
            created_at = int(record.get("created_at", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if (
            _matches_stack_generation(record, stack_generation)
            and now - created_at < grace_seconds
        ):
            return True
    return False


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
                normalized = {"uid": uid, "created_at": created_at}
                stack_generation = str(
                    record.get("stack_generation", "")
                ).strip()
                if stack_generation:
                    normalized["stack_generation"] = stack_generation
                records.append(normalized)
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

    def add(self, uid, created_at, stack_generation=None):
        uid = str(uid)
        with self.lock:
            records = [record for record in self._load() if record["uid"] != uid]
            record = {"uid": uid, "created_at": int(created_at)}
            stack_generation = str(stack_generation or "").strip()
            if stack_generation:
                record["stack_generation"] = stack_generation
            records.append(record)
            self._save(records)

    def remove(self, uid):
        uid = str(uid)
        with self.lock:
            records = [record for record in self._load() if record["uid"] != uid]
            self._save(records)
