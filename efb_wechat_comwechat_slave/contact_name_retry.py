import threading
from typing import Dict, List, Tuple


class ContactNameRetryQueue:
    """Keep a bounded retry schedule for unresolved WeChat display names."""

    def __init__(
        self,
        initial_delay: float = 15.0,
        max_delay: float = 300.0,
        max_items: int = 256,
    ):
        self.initial_delay = max(1.0, float(initial_delay))
        self.max_delay = max(self.initial_delay, float(max_delay))
        self.max_items = max(1, int(max_items))
        self._entries: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.RLock()

    def schedule(self, uid: str, now: float) -> bool:
        uid = str(uid or "").strip()
        if not uid:
            return False
        with self._lock:
            if uid in self._entries:
                return False
            if len(self._entries) >= self.max_items:
                evicted = max(self._entries, key=lambda item: self._entries[item][1])
                self._entries.pop(evicted, None)
            self._entries[uid] = (0, float(now) + self.initial_delay)
            return True

    def due(self, now: float, limit: int = 8) -> List[str]:
        with self._lock:
            ready = [
                (next_at, uid)
                for uid, (_attempts, next_at) in self._entries.items()
                if next_at <= float(now)
            ]
        ready.sort()
        return [uid for _next_at, uid in ready[:max(1, int(limit))]]

    def failed(self, uid: str, now: float) -> None:
        uid = str(uid or "").strip()
        if not uid:
            return
        with self._lock:
            attempts, _next_at = self._entries.get(uid, (0, float(now)))
            attempts += 1
            delay = min(self.max_delay, self.initial_delay * (2 ** min(attempts, 5)))
            self._entries[uid] = (attempts, float(now) + delay)

    def resolved(self, uid: str) -> None:
        with self._lock:
            self._entries.pop(str(uid or "").strip(), None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
