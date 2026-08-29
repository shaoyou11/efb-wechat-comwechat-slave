import json
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict


EPHEMERAL_MESSAGE_FIELDS = {
    "_media_observed_size",
    "_media_stable_since",
}


def _json_safe(value):
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if str(key) not in EPHEMERAL_MESSAGE_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_pending_file_record(msg, author, chat, chat_kind: str) -> Dict[str, Any]:
    return {
        "msg": _json_safe(msg),
        "chat_kind": str(chat_kind),
        "chat_uid": str(chat.uid),
        "chat_name": str(chat.name),
        "author_uid": str(author.uid),
        "author_name": str(author.name),
        "author_alias": (
            None
            if getattr(author, "alias", None) is None
            else str(author.alias)
        ),
    }


def delivery_confirmed(results) -> bool:
    if not results:
        return False
    statuses = []
    for result in results:
        if result is None:
            return False
        vendor_specific = getattr(result, "vendor_specific", {})
        if not isinstance(vendor_specific, dict):
            return False
        status = vendor_specific.get("telegram_delivery_status")
        if not status:
            return False
        statuses.append(status)
    return all(
        status in {"delivered", "filtered", "skipped", "stored_for_retry"}
        for status in statuses
    )


def media_path_state(path: str) -> str:
    """Classify an attachment path without treating directories as media."""
    try:
        metadata = os.stat(path)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unavailable"
    if not stat.S_ISREG(metadata.st_mode):
        return "invalid"
    if metadata.st_size <= 0:
        return "empty"
    return "ready"


class PendingFileStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.records = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    str(path): record
                    for path, record in data.items()
                    if isinstance(record, dict)
                }
        except (OSError, TypeError, ValueError):
            pass
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.path.parent),
            prefix=".pending-files.",
            delete=False,
        ) as handle:
            json.dump(self.records, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = handle.name
        os.replace(temporary, self.path)

    def put(self, path: str, record: Dict[str, Any]) -> None:
        with self.lock:
            self.records[str(path)] = _json_safe(record)
            self._save()

    def remove(self, path: str) -> None:
        with self.lock:
            if self.records.pop(str(path), None) is not None:
                self._save()

    def items(self):
        with self.lock:
            return [
                (path, dict(record))
                for path, record in self.records.items()
            ]
