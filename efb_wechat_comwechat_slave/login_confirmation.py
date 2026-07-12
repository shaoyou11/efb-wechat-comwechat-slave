import threading
from typing import Callable


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
