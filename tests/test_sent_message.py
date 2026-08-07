import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "sent_message.py"
)
SPEC = importlib.util.spec_from_file_location("sent_message", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_computer_sent_message_is_ignored_as_a_bridge_echo():
    assert MODULE.should_ignore_sent_msg(
        {"isSendMsg": 1, "isSendByPhone": 0, "msgid": "123"}
    )


def test_phone_self_message_is_not_treated_as_a_computer_echo():
    assert not MODULE.should_ignore_sent_msg(
        {"isSendMsg": 1, "isSendByPhone": 1, "msgid": "123"}
    )
