import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "offline_trigger.py"
)
SPEC = importlib.util.spec_from_file_location("offline_trigger", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_posts_to_local_watchdog():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))

    with TemporaryDirectory() as directory, patch.dict(
        os.environ,
        {"EFB_WATCHDOG_EVENT_PATH": str(Path(directory) / "offline-event.json")},
        clear=True,
    ):
        MODULE.notify_watchdog(opener=opener)

    assert requests[0][0].full_url == "http://127.0.0.1:18989/offline"
    assert requests[0][0].method == "POST"
    assert requests[0][1] == 2


def test_persists_event_when_watchdog_endpoint_is_unavailable():
    def opener(_request, timeout):
        assert timeout == 2
        raise OSError("watchdog is restarting")

    with TemporaryDirectory() as directory, patch.dict(
        os.environ,
        {"EFB_WATCHDOG_EVENT_PATH": str(Path(directory) / "offline-event.json")},
        clear=True,
    ):
        try:
            MODULE.notify_watchdog(opener=opener)
        except OSError:
            pass
        event_path = Path(directory) / "offline-event.json"
        event = json.loads(event_path.read_text(encoding="utf-8"))

    assert event["version"] == 1
    assert event["created_at"] > 0
