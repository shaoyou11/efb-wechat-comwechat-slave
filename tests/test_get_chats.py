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
