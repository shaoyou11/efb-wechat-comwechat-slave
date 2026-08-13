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
from efb_wechat_comwechat_slave.MsgDeco import efb_share_link_wrapper, efb_miniprogram_wrapper


def test_customer_service_menu_does_not_expose_raw_anchor_markup():
    xml = '''<msg><appmsg><type>5</type><showtype>0</showtype>
      <title>请选择</title><url>weixin://kefumenu?id=1</url>
      <des>1.&lt;a href="weixin://kefumenu?id=2"&gt;查询进度&lt;/a&gt;</des>
    </appmsg></msg>'''

    message = efb_share_link_wrapper({"message": xml}, None)

    assert "<a href" not in (message.attributes.description or "")
    assert "查询进度" in (message.attributes.description or "")


def test_miniprogram_missing_optional_fields_falls_back_without_crashing():
    message = efb_miniprogram_wrapper(
        "<msg><appmsg><title>测试小程序</title><type>33</type></appmsg></msg>"
    )

    assert message.text == "微信小程序\n测试小程序"
