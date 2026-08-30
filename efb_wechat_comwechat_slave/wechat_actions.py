from typing import Callable, Dict


class WechatActionError(RuntimeError):
    pass


def api_succeeded(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    value = str(result.get("result", "")).strip().upper()
    if value:
        return value in {"OK", "SUCCESS"}
    if "success" in result:
        return bool(result["success"])
    if "msg" in result:
        return str(result["msg"]).strip() not in {"", "0", "FALSE"}
    return False


def send_native_quote_or_fallback(
    bot: object,
    wxid: str,
    text: str,
    target_msgid: str,
    fallback: Callable[[], Dict],
) -> Dict:
    send_quote = getattr(bot, "SendQuoteText", None)
    if callable(send_quote) and str(target_msgid).strip():
        try:
            result = send_quote(
                wxid=wxid,
                msg=text,
                target_msgid=str(target_msgid),
            )
            if api_succeeded(result):
                return result
        except Exception:
            pass
    return fallback()


def mark_chat_read(bot: object, wxid: str) -> Dict:
    mark_read = getattr(bot, "MarkAsRead", None)
    if not callable(mark_read):
        raise WechatActionError("当前微信接口不支持标记已读")
    try:
        result = mark_read(wxid=wxid)
    except Exception as error:
        raise WechatActionError("标记已读失败，请稍后重试") from error
    if not api_succeeded(result):
        raise WechatActionError("标记已读失败，请稍后重试")
    return result
