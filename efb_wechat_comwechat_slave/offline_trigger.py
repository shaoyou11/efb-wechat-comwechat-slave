import os
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def pending_event_path():
    return Path(os.getenv(
        "EFB_WATCHDOG_EVENT_PATH",
        "/data/watchdog/state/offline-event.json",
    ))


def persist_offline_event():
    target = pending_event_path()
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps({"version": 1, "created_at": time.time()}) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def notify_watchdog(opener=urlopen):
    url = os.getenv(
        "EFB_WATCHDOG_TRIGGER_URL",
        "http://127.0.0.1:18989/offline",
    )
    request = Request(url, data=b"", method="POST")
    try:
        opener(request, timeout=2)
    except Exception:
        # Keep the event on the shared NAS volume when the in-memory endpoint
        # is unavailable, so a watchdog restart can still recover it later.
        persist_offline_event()
        raise
