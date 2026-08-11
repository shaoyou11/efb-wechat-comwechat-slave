import importlib.util
from pathlib import Path
import threading
import time


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "login_confirmation.py"
)
SPEC = importlib.util.spec_from_file_location("login_confirmation", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LoginConfirmation = MODULE.LoginConfirmation
login_confirmation_message = MODULE.login_confirmation_message
stable_login_state = MODULE.stable_login_state


def test_concurrent_login_callbacks_confirm_only_once():
    confirmation = LoginConfirmation()
    state = {"confirmed": False, "calls": 0}

    def confirm():
        state["calls"] += 1
        time.sleep(0.01)
        state["confirmed"] = True
        return True

    threads = [
        threading.Thread(
            target=lambda: confirmation.run(
                is_confirmed=lambda: state["confirmed"],
                confirm=confirm,
            )
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert state["calls"] == 1


def test_existing_session_recovery_does_not_announce_login():
    assert login_confirmation_message(logged_in=True, has_pending_qr=False) is None
    assert login_confirmation_message(logged_in=True, has_pending_qr=True) == "登录成功"
    assert login_confirmation_message(logged_in=False, has_pending_qr=False) is None
    assert login_confirmation_message(logged_in=False, has_pending_qr=True) == "登录失败，请重新登录"


def test_watchdog_recovery_announces_login_without_qr():
    assert (
        login_confirmation_message(
            logged_in=True,
            has_pending_qr=False,
            auto_recovery=True,
        )
        == "登录成功"
    )


def test_stable_login_requires_all_probes(monkeypatch):
    results = iter([True, True, True])
    sleeps = []
    monkeypatch.setattr(MODULE.time, "sleep", sleeps.append)

    assert stable_login_state(lambda: next(results), probes=3, interval_seconds=2)
    assert sleeps == [2, 2]


def test_stable_login_rejects_transient_success(monkeypatch):
    results = iter([True, False, True])
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    assert not stable_login_state(lambda: next(results), probes=3, interval_seconds=2)
