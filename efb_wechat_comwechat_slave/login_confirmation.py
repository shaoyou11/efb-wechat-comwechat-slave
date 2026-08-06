import threading
from typing import Callable, Optional


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


class LoginRetryState:
    """Keep a manual-login confirmation pending across transient init failures."""

    def __init__(self):
        self.confirmation_pending = False

    def observe_transition(self, login_transition: bool) -> None:
        if login_transition:
            self.confirmation_pending = True

    def consume_after_success(self) -> bool:
        pending = self.confirmation_pending
        self.confirmation_pending = False
        return pending
