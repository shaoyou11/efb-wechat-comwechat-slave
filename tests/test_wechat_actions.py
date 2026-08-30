import importlib.util
from pathlib import Path
from unittest.mock import Mock


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "wechat_actions.py"
)
SPEC = importlib.util.spec_from_file_location("wechat_actions", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_native_quote_is_used_when_api_succeeds():
    bot = Mock()
    bot.SendQuoteText.return_value = {"result": "OK"}
    fallback = Mock()

    result = MODULE.send_native_quote_or_fallback(
        bot, "chat", "reply", "123", fallback
    )

    assert result == {"result": "OK"}
    bot.SendQuoteText.assert_called_once_with(
        wxid="chat", msg="reply", target_msgid="123"
    )
    fallback.assert_not_called()


def test_native_quote_failure_falls_back_once():
    bot = Mock()
    bot.SendQuoteText.return_value = {"result": "ERROR"}
    fallback = Mock(return_value={"result": "OK"})

    result = MODULE.send_native_quote_or_fallback(
        bot, "chat", "reply", "123", fallback
    )

    assert result == {"result": "OK"}
    fallback.assert_called_once_with()


def test_mark_read_is_explicit_and_idempotent_result_is_accepted():
    bot = Mock()
    bot.MarkAsRead.return_value = {"result": "OK"}

    assert MODULE.mark_chat_read(bot, "chat") == {"result": "OK"}
    bot.MarkAsRead.assert_called_once_with(wxid="chat")


def test_mark_read_rejects_api_failure():
    bot = Mock()
    bot.MarkAsRead.return_value = {"result": "ERROR"}

    try:
        MODULE.mark_chat_read(bot, "chat")
    except MODULE.WechatActionError as error:
        assert "标记已读失败" in str(error)
    else:
        raise AssertionError("failed mark-as-read must raise")
