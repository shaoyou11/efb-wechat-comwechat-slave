import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "command_validation.py"
)
SPEC = importlib.util.spec_from_file_location("command_validation", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_group_commands_require_a_wechat_group():
    assert MODULE.group_command_error(
        "/getmemberlist",
        "wxid_private",
    ) == "该命令只能在微信群会话中使用。"
    assert MODULE.group_command_error(
        "/changename 新群名",
        "wxid_private",
    ) == "该命令只能在微信群会话中使用。"


def test_group_commands_are_allowed_in_wechat_groups():
    assert MODULE.group_command_error(
        "/getmemberlist",
        "123456@chatroom",
    ) is None


def test_contact_commands_are_allowed_in_private_chats():
    assert MODULE.group_command_error(
        "/search 张三",
        "wxid_private",
    ) is None


def test_chatroom_member_ids_filters_empty_values():
    assert MODULE.chatroom_member_ids({"members": "a^Gb^G"}) == ["a", "b"]
    assert MODULE.chatroom_member_ids({"members": ""}) == []
    assert MODULE.chatroom_member_ids({}) == []
