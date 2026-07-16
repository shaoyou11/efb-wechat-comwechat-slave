import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "contact_display.py"
SPEC = importlib.util.spec_from_file_location("contact_display", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
resolve_contact_name = MODULE.resolve_contact_name
update_existing_chat_name = MODULE.update_existing_chat_name


def test_notifymessage_is_localized_without_lookup():
    calls = []

    assert resolve_contact_name("notifymessage", "notifymessage", calls.append) == "服务通知"
    assert calls == []


def test_technical_public_account_id_is_refreshed_from_wechat_database():
    def lookup(wxid):
        assert wxid == "gh_366bf6794a09"
        return [wxid, "", "", "岁月观", "3"]

    assert resolve_contact_name("gh_366bf6794a09", "gh_366bf6794a09", lookup) == "岁月观"


def test_existing_chinese_name_does_not_query_database_again():
    calls = []

    assert resolve_contact_name("wxid_demo", "张三", calls.append) == "张三"
    assert calls == []


def test_existing_chat_object_gets_the_refreshed_name():
    class Chat:
        def __init__(self, uid, name):
            self.uid = uid
            self.name = name

    chats = [Chat("gh_366bf6794a09", "gh_366bf6794a09")]

    assert update_existing_chat_name(chats, "gh_366bf6794a09", "岁月观")
    assert chats[0].name == "岁月观"
