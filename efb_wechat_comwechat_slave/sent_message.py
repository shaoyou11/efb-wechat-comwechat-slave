from typing import Any, Mapping


def should_ignore_sent_msg(message: Mapping[str, Any]) -> bool:
    """识别电脑端发送回环消息，避免 Bridge 因无处理器而重试入死信。"""
    return (
        isinstance(message, Mapping)
        and message.get("isSendMsg") == 1
        and message.get("isSendByPhone") == 0
    )
