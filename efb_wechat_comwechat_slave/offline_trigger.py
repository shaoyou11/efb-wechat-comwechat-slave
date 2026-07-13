import os
from urllib.request import Request, urlopen


def notify_watchdog(opener=urlopen):
    url = os.getenv(
        "EFB_WATCHDOG_TRIGGER_URL",
        "http://127.0.0.1:18989/offline",
    )
    request = Request(url, data=b"", method="POST")
    opener(request, timeout=2)
