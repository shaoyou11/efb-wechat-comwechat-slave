"""Small, non-sensitive metadata helpers for WeChat recall events."""


def build_wechat_recall_metadata(message, self_uid):
    """Identify the actor without retaining the original XML payload."""
    recaller_uid = str(message.get("wxid") or "")
    is_self = bool(message.get("isSendMsg")) or (
        bool(recaller_uid) and recaller_uid == str(self_uid or "")
    )
    return {"actor": "self" if is_self else "other"}
