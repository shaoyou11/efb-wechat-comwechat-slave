import re
from typing import Callable, Iterable, Optional, Sequence


SYSTEM_CONTACT_NAMES = {
    "notifymessage": "服务通知",
    "notification_messages": "服务通知",
    "filehelper": "文件传输助手",
    "fmessage": "新的朋友",
    "weixin": "微信团队",
    "medianote": "语音记事本",
    "newsapp": "腾讯新闻",
    "tmessage": "腾讯微博",
    "weibo": "微博",
    "qqmail": "QQ邮箱提醒",
}

TECHNICAL_ID_PATTERN = re.compile(
    r"^(?:(?:gh_|wxid_|v1_).+|[^@\s]+@(?:chatroom|(?:kefu\.)?openim))$",
    re.IGNORECASE,
)
MENTION_ALIAS_PATTERN = re.compile(r"^@([^\u2005\r\n]+?)(?:\u2005|\s|$)")


def extract_mentioned_alias(message: str) -> Optional[str]:
    """Return the leading WeChat @-mention name when its separator is valid."""
    match = MENTION_ALIAS_PATTERN.match(str(message or ""))
    return match.group(1).strip() if match else None


def _is_technical_name(wxid: str, name: Optional[str]) -> bool:
    value = (name or "").strip()
    return not value or value == wxid or value in SYSTEM_CONTACT_NAMES or bool(TECHNICAL_ID_PATTERN.match(value))


def is_technical_contact_id(wxid: str) -> bool:
    """Return whether a WeChat ID is unsuitable as a lasting display name."""
    return bool(TECHNICAL_ID_PATTERN.match(str(wxid or "")))


def should_publish_resolved_name(
    wxid: str,
    cached_name: Optional[str],
    resolved_name: Optional[str],
) -> bool:
    """Return whether a resolved name replaces a technical cached value."""
    resolved = (resolved_name or "").strip()
    cached = (cached_name or "").strip()
    return bool(resolved) and resolved != wxid and resolved != cached and is_technical_contact_id(wxid)


def should_force_name_sync(
    wxid: str,
    previous_name: Optional[str],
    resolved_name: Optional[str],
) -> bool:
    """Force a topic rename only when a cached technical name was replaced."""
    previous = (previous_name or "").strip()
    resolved = (resolved_name or "").strip()
    return (
        bool(previous)
        and is_technical_contact_id(wxid)
        and _is_technical_name(wxid, previous)
        and bool(resolved)
        and resolved != wxid
        and resolved != previous
    )


def resolve_contact_name(
    wxid: str,
    cached_name: Optional[str],
    lookup: Callable[[str], Optional[Sequence]],
) -> str:
    if wxid in SYSTEM_CONTACT_NAMES:
        return SYSTEM_CONTACT_NAMES[wxid]
    if not _is_technical_name(wxid, cached_name):
        return cached_name.strip()

    data = lookup(wxid)
    if data and len(data) > 3 and data[3]:
        return str(data[3]).strip()
    return (cached_name or wxid).strip()


def update_existing_chat_name(chats: Iterable, uid: str, name: str) -> bool:
    for chat in chats:
        if chat.uid == uid:
            chat.name = name
            return True
    return False
