import json

import pytest

from efb_wechat_comwechat_slave.contact_aliases import ContactAliasStore


def test_contact_alias_store_keeps_alias_and_name_history(tmp_path):
    path = tmp_path / "contact-aliases.json"
    store = ContactAliasStore(path)

    store.remember("gh_demo", "旧名称", now=1000)
    store.set_alias("gh_demo", "本地名称", previous_name="旧名称", now=1100)

    reloaded = ContactAliasStore(path)
    assert reloaded.get_alias("gh_demo") == "本地名称"
    assert reloaded.history("gh_demo") == ["旧名称"]
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_contact_alias_store_deduplicates_history_and_limits_entries(tmp_path):
    store = ContactAliasStore(tmp_path / "contact-aliases.json", max_history=2)

    for index in range(4):
        store.remember("wxid_demo", f"名称{index}", now=index)
    store.remember("wxid_demo", "名称3", now=10)

    assert store.history("wxid_demo") == ["名称2", "名称3"]


def test_contact_alias_store_rejects_invalid_values(tmp_path):
    store = ContactAliasStore(tmp_path / "contact-aliases.json")

    with pytest.raises(ValueError):
        store.set_alias("", "名称")
    with pytest.raises(ValueError):
        store.set_alias("wxid_demo", "\n")


def test_contact_alias_store_can_clear_alias_without_losing_history(tmp_path):
    store = ContactAliasStore(tmp_path / "contact-aliases.json")
    store.set_alias("wxid_demo", "本地名称", previous_name="微信名称", now=1000)

    store.clear_alias("wxid_demo", current_name="本地名称", now=1100)

    assert store.get_alias("wxid_demo") is None
    assert store.history("wxid_demo") == ["微信名称", "本地名称"]
