"""Persist local contact aliases and a small history of observed names."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


class ContactAliasStore:
    VERSION = 1

    def __init__(self, path: Path, max_history: int = 10):
        self.path = Path(path)
        self.max_history = max(1, int(max_history))
        self._lock = threading.RLock()
        self._data = self._load()

    @staticmethod
    def _empty() -> dict:
        return {"version": ContactAliasStore.VERSION, "aliases": {}, "history": {}}

    def _load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return self._empty()
        if not isinstance(payload, dict):
            return self._empty()
        aliases = payload.get("aliases")
        history = payload.get("history")
        if not isinstance(aliases, dict):
            aliases = {}
        if not isinstance(history, dict):
            history = {}
        return {
            "version": self.VERSION,
            "aliases": {
                str(key): str(value).strip()
                for key, value in aliases.items()
                if str(key).strip() and str(value).strip()
            },
            "history": {
                str(key): self._history_names(value)
                for key, value in history.items()
                if str(key).strip()
            },
        }

    def _history_names(self, value) -> List[str]:
        result = []
        values = value if isinstance(value, list) else []
        for item in values:
            name = item.get("name") if isinstance(item, dict) else item
            name = str(name or "").strip()
            if name and name not in result:
                result.append(name)
        return result[-self.max_history:]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                delete=False,
            ) as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = handle.name
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    @property
    def aliases(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._data["aliases"])

    def get_alias(self, wxid: str) -> Optional[str]:
        with self._lock:
            value = self._data["aliases"].get(str(wxid or "").strip())
            return value or None

    def history(self, wxid: str) -> List[str]:
        with self._lock:
            return list(self._data["history"].get(str(wxid or "").strip(), []))

    def remember(self, wxid: str, name: str, now=None) -> None:
        wxid = str(wxid or "").strip()
        name = str(name or "").strip()
        if not wxid or not name or name == wxid:
            return
        with self._lock:
            names = self._data["history"].setdefault(wxid, [])
            if name in names:
                names.remove(name)
            names.append(name)
            self._data["history"][wxid] = names[-self.max_history:]
            self._save()

    def set_alias(self, wxid: str, alias: str, previous_name: str = "", now=None) -> str:
        wxid = str(wxid or "").strip()
        alias = " ".join(str(alias or "").split())
        if not wxid:
            raise ValueError("联系人标识不能为空")
        if not alias or len(alias) > 80:
            raise ValueError("本地别名长度必须为 1 至 80 个字符")
        with self._lock:
            previous = str(previous_name or "").strip()
            if previous and previous != wxid and previous != alias:
                self.remember(wxid, previous, now=now)
            self._data["aliases"][wxid] = alias
            self._save()
        return alias

    def clear_alias(self, wxid: str, current_name: str = "", now=None) -> bool:
        wxid = str(wxid or "").strip()
        if not wxid:
            return False
        with self._lock:
            previous = self._data["aliases"].pop(wxid, None)
            current = str(current_name or previous or "").strip()
            if current and current != wxid:
                self.remember(wxid, current, now=now)
            if previous is None:
                return False
            self._save()
            return True
