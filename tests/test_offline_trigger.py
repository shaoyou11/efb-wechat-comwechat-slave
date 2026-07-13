import importlib.util
from pathlib import Path


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

    MODULE.notify_watchdog(opener=opener)

    assert requests[0][0].full_url == "http://127.0.0.1:18989/offline"
    assert requests[0][0].method == "POST"
    assert requests[0][1] == 2
