import threading
import time
from typing import Callable, Optional


def stable_login_state(
    check: Callable[[], bool],
    probes: int = 3,
    interval_seconds: float = 2,
) -> bool:
    """Reject a momentary API login value before success is announced."""
    probes = max(1, int(probes))
    for index in range(probes):
        if not check():
            return False
        if index + 1 < probes:
            time.sleep(max(0, interval_seconds))
    return True


def login_confirmation_message(
    logged_in: bool,
    has_pending_qr: bool,
    auto_recovery: bool = False,
) -> Optional[str]:
    if not has_pending_qr and not auto_recovery:
        return None
    return "登录成功" if logged_in else "登录失败，请重新登录"


class LoginConfirmation:
    """Serialize login callbacks and skip confirmation already completed."""

    def __init__(self):
        self._lock = threading.Lock()

    def run(
        self,
        is_confirmed: Callable[[], bool],
        confirm: Callable[[], bool],
    ) -> bool:
        with self._lock:
            if is_confirmed():
                return True
            return confirm()
