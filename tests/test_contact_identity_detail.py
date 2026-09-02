import threading
from types import SimpleNamespace

import pytest

from efb_wechat_comwechat_slave.ComWechat import ComWeChatChannel
from efb_wechat_comwechat_slave.contact_aliases import ContactAliasStore
from efb_wechat_comwechat_slave.contact_name_retry import ContactNameRetryQueue


def channel(tmp_path, lookup):
    result = ComWeChatChannel.__new__(ComWeChatChannel)
    result.contacts = {"wxid_demo": "wxid_demo"}
    result.friends, result.groups = [], []
    result._contact_name_update_lock = threading.RLock()
    result._contact_lookup_state = {}
    result.contact_alias_store = ContactAliasStore(tmp_path / "aliases.json")
    result.contact_name_retry_queue = ContactNameRetryQueue()
    result.bot = SimpleNamespace(GetContactBySql=lookup)
    result._publish_resolved_contact_name = lambda *args, **kwargs: None
    return result


def test_targeted_refresh_and_cooldown_preserve_alias(tmp_path):
    calls = []
    ch = channel(tmp_path, lambda **kwargs: calls.append(kwargs) or [0, 0, 0, "微信名称"])
    ch.contact_alias_store.set_alias("wxid_demo", "自定义名称")
    assert ch.contact_identity_detail("wxid_demo")["queried_at"] is None
    detail = ch.contact_identity_detail("wxid_demo", refresh=True)
    assert detail["source"] == "本地别名"
    assert detail["name"] == "自定义名称"
    assert detail["queried_at"]
    ch.contact_identity_detail("wxid_demo", refresh=True)
    assert len(calls) == 1
    assert "微信名称" in detail["history"]


def test_missing_name_and_query_failure_are_distinguished(tmp_path):
    ch = channel(tmp_path, lambda **_: None)
    detail = ch.contact_identity_detail("wxid_demo", refresh=True)
    assert detail["resolved"] is False
    assert "未返回可用名称" in detail["reason"]
    ch._contact_lookup_state.clear()
    ch.bot.GetContactBySql = lambda **_: (_ for _ in ()).throw(RuntimeError("private detail"))
    with pytest.raises(RuntimeError):
        ch.contact_identity_detail("wxid_demo", refresh=True)
    detail = ch.contact_identity_detail("wxid_demo")
    assert "查询接口失败" in detail["reason"]
    assert "private detail" not in str(detail)


def test_unknown_contact_does_not_trigger_lookup(tmp_path):
    calls = []
    ch = channel(tmp_path, lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ValueError):
        ch.contact_identity_detail("wxid_unknown", refresh=True)
    assert calls == []
