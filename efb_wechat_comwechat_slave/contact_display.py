import re
from typing import Callable, Iterable, Optional, Sequence


SYSTEM_CONTACT_NAMES = {
    "notifymessage": "服务通知",
    "filehelper": "文件传输助手",
    "fmessage": "新的朋友",
    "weixin": "微信团队",
    "medianote": "语音记事本",
    "newsapp": "腾讯新闻",
    "qqmail": "QQ邮箱提醒",
}

TECHNICAL_ID_PATTERN = re.compile(r"^(?:gh_|wxid_|v1_).+", re.IGNORECASE)


def _is_technical_name(wxid: str, name: Optional[str]) -> bool:
    value = (name or "").strip()
    return not value or value == wxid or value in SYSTEM_CONTACT_NAMES or bool(TECHNICAL_ID_PATTERN.match(value))


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
