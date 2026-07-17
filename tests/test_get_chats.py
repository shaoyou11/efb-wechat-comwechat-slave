from unittest.mock import Mock

from efb_wechat_comwechat_slave.ComWechat import ComWeChatChannel


def test_get_chats_returns_friends_and_groups_without_exposing_internal_lists():
    channel = ComWeChatChannel.__new__(ComWeChatChannel)
    channel.friends = ["friend-a", "friend-b"]
    channel.groups = ["group-a"]

    chats = channel.get_chats()
    chats.append("external-change")

    assert chats == ["friend-a", "friend-b", "group-a", "external-change"]
    assert channel.friends == ["friend-a", "friend-b"]
    assert channel.groups == ["group-a"]


def test_get_chats_loads_contacts_when_already_logged_in():
    channel = ComWeChatChannel.__new__(ComWeChatChannel)
    channel.friends = []
    channel.groups = []
    channel.is_login = lambda: True
    channel.get_me = Mock()
    channel.GetGroupListBySql = Mock()

    def load_contacts(*, notify):
        assert notify is False
        channel.friends.append("friend")

    channel.GetContactListBySql = Mock(side_effect=load_contacts)

    assert channel.get_chats() == ["friend"]
    channel.get_me.assert_called_once_with()
    channel.GetContactListBySql.assert_called_once_with(notify=False)
    channel.GetGroupListBySql.assert_called_once_with()
