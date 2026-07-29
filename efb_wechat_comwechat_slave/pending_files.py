import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict


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
        status in {"delivered", "filtered", "skipped", "failed"}
        for status in statuses
    )


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
            self.records[str(path)] = dict(record)
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
