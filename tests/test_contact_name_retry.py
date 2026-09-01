import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "contact_name_retry.py"
SPEC = importlib.util.spec_from_file_location("contact_name_retry", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ContactNameRetryQueue = MODULE.ContactNameRetryQueue


def test_unresolved_name_retries_with_bounded_backoff():
    queue = ContactNameRetryQueue(initial_delay=15, max_delay=60, max_items=2)

    assert queue.schedule("room@chatroom", now=100)
    assert not queue.schedule("room@chatroom", now=101)
    assert queue.due(114) == []
    assert queue.due(115) == ["room@chatroom"]

    queue.failed("room@chatroom", now=115)
    assert queue.due(144) == []
    assert queue.due(145) == ["room@chatroom"]

    queue.failed("room@chatroom", now=145)
    assert queue.due(204) == []
    assert queue.due(205) == ["room@chatroom"]


def test_new_active_name_replaces_the_least_urgent_item_when_capacity_is_full():
    queue = ContactNameRetryQueue(initial_delay=1, max_items=2)

    assert queue.schedule("first", now=0)
    assert queue.schedule("second", now=10)
    assert queue.schedule("third", now=20)
    assert len(queue) == 2
    assert queue.due(11) == ["first"]

    queue.resolved("first")
    assert len(queue) == 1
    assert queue.due(21) == ["third"]
