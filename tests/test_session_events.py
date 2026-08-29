import importlib.util
import json
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


def test_first_observation_establishes_baseline_without_fake_login(tmp_path):
    path = tmp_path / "session-events.json"
    store = SessionEventStore(path)

    assert store.observe(True, observed_at=1000) is False

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["current_state"] == "online"
    assert data["tracking_started_at"] == 1000
    assert "last_login_at" not in data


def test_transitions_record_login_and_logout_times(tmp_path):
    path = tmp_path / "session-events.json"
    store = SessionEventStore(path)

    store.observe(True, observed_at=1000)
    assert store.observe(False, observed_at=1010) is True
    assert store.observe(False, observed_at=1020) is False
    assert store.observe(True, observed_at=1030) is True

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["last_logout_at"] == 1010
    assert data["last_login_at"] == 1030
    assert data["last_observed_at"] == 1030


def test_legacy_timestamps_are_preserved_but_not_presented_as_current(tmp_path):
    path = tmp_path / "session-events.json"
    path.write_text(
        json.dumps({"last_login_at": 800, "last_logout_at": 700}),
        encoding="utf-8",
    )
    store = SessionEventStore(path)

    store.observe(True, observed_at=1000)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["legacy_last_login_at"] == 800
    assert data["legacy_last_logout_at"] == 700
    assert "last_login_at" not in data
    assert "last_logout_at" not in data


def test_explicit_action_records_event_without_existing_baseline(tmp_path):
    path = tmp_path / "session-events.json"
    store = SessionEventStore(path)

    store.record(False, observed_at=1000)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["current_state"] == "offline"
    assert data["last_logout_at"] == 1000
