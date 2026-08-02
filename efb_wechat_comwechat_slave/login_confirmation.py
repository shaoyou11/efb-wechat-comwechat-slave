import threading
from typing import Callable, Optional


def login_confirmation_message(
    logged_in: bool,
    has_pending_qr: bool,
) -> Optional[str]:
    if not has_pending_qr:
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
