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
