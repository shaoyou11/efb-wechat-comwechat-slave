import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "session_events.py"
)
SPEC = importlib.util.spec_from_file_location("session_events", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SessionEventStore = MODULE.SessionEventStore


def test_session_events_are_persisted_and_restored(tmp_path):
    path = tmp_path / "session-events.json"
    store = SessionEventStore(path)

    assert store.read() == {
        "last_login_at": None,
        "last_logout_at": None,
    }
    store.record_logout(100)
    store.record_login(200)

    restored = SessionEventStore(path)
    assert restored.read() == {
        "last_login_at": 200.0,
        "last_logout_at": 100.0,
    }
