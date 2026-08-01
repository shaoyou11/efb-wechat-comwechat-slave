import colorsys
import hashlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO, Callable, Dict, Optional, Tuple

from PIL import Image


PALETTE: Tuple[Tuple[str, Tuple[int, int, int]], ...] = (
    ("🔴", (220, 50, 47)),
    ("🟠", (242, 142, 28)),
    ("🟡", (235, 196, 34)),
    ("🟢", (49, 164, 88)),
    ("🔵", (52, 120, 210)),
    ("🟣", (135, 78, 190)),
    ("🟤", (132, 91, 65)),
    ("⚫", (55, 55, 55)),
    ("⚪", (225, 225, 225)),
)

FALLBACK_PALETTE = tuple(item[0] for item in PALETTE[:7])


def fallback_marker(member_id: str) -> str:
    digest = hashlib.sha256(member_id.encode("utf-8")).digest()
    return FALLBACK_PALETTE[digest[0] % len(FALLBACK_PALETTE)]


def _nearest_marker(rgb: Tuple[int, int, int]) -> str:
    def distance(candidate: Tuple[int, int, int]) -> int:
        return sum((left - right) ** 2 for left, right in zip(rgb, candidate))

    return min(PALETTE, key=lambda item: distance(item[1]))[0]


def marker_from_avatar(file: BinaryIO) -> str:
    file.seek(0)
    with Image.open(file) as image:
        image = image.convert("RGB")
        image.thumbnail((48, 48))
        quantized = image.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette()
        colors = quantized.getcolors() or []

    candidates = []
    for count, color_index in colors:
        offset = color_index * 3
        rgb = tuple(palette[offset:offset + 3])
        red, green, blue = (component / 255 for component in rgb)
        _, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
        # Prefer a meaningful avatar accent over white backgrounds and shadows.
        score = count * (0.25 + saturation) * (0.35 + value)
        if value > 0.94 and saturation < 0.08:
            score *= 0.15
        if value < 0.08:
            score *= 0.35
        candidates.append((score, rgb))

    if not candidates:
        raise ValueError("Avatar has no usable colors")
    return _nearest_marker(max(candidates, key=lambda item: item[0])[1])


class MemberAvatarMarkerStore:
    def __init__(self, path: Path, enabled: bool = True):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="avatar-marker")
        self.inflight = set()
        self.attempted = set()
        self.data: Dict = {"enabled": bool(enabled), "members": {}}
        self._load(enabled)

    @property
    def enabled(self) -> bool:
        with self.lock:
            return bool(self.data.get("enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        with self.lock:
            self.data["enabled"] = bool(enabled)
            self._save_locked()

    def marker_for(
        self,
        member_id: str,
        avatar_loader: Callable[[str], Optional[BinaryIO]],
    ) -> Optional[str]:
        if not self.enabled:
            return None

        now = int(time.time())
        with self.lock:
            members = self.data.setdefault("members", {})
            entry = members.get(member_id)
            if not isinstance(entry, dict):
                entry = {
                    "marker": fallback_marker(member_id),
                    "source": "fallback",
                    "updated_at": now,
                }
                members[member_id] = entry
                self._save_locked()

            age = now - int(entry.get("updated_at", 0))
            needs_refresh = entry.get("source") != "avatar" or age >= 30 * 24 * 60 * 60
            if needs_refresh and member_id not in self.attempted and member_id not in self.inflight:
                self.inflight.add(member_id)
                self.attempted.add(member_id)
                self.executor.submit(self._refresh, member_id, avatar_loader)
            return str(entry.get("marker") or fallback_marker(member_id))

    def counts(self) -> Tuple[int, int]:
        with self.lock:
            entries = self.data.get("members", {}).values()
            avatar = sum(1 for entry in entries if entry.get("source") == "avatar")
            return avatar, len(self.data.get("members", {}))

    def _refresh(self, member_id: str, avatar_loader: Callable[[str], Optional[BinaryIO]]) -> None:
        avatar = None
        try:
            avatar = avatar_loader(member_id)
            if avatar is None:
                return
            marker = marker_from_avatar(avatar)
            with self.lock:
                self.data.setdefault("members", {})[member_id] = {
                    "marker": marker,
                    "source": "avatar",
                    "updated_at": int(time.time()),
                }
                self._save_locked()
        except Exception:
            return
        finally:
            if avatar is not None:
                avatar.close()
            with self.lock:
                self.inflight.discard(member_id)

    def _load(self, default_enabled: bool) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("enabled", bool(default_enabled))
                loaded.setdefault("members", {})
                self.data = loaded
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
