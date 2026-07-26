from typing import Any, Dict, List, Optional


GROUP_ONLY_COMMANDS = {
    "/addtogroup",
    "/at",
    "/changename",
    "/getmemberlist",
}


def group_command_error(text: str, chat_uid: str) -> Optional[str]:
    command = text.split(maxsplit=1)[0] if text else ""
    if command in GROUP_ONLY_COMMANDS and not chat_uid.endswith("@chatroom"):
        return "该命令只能在微信群会话中使用。"
    return None


def chatroom_member_ids(result: Dict[str, Any]) -> List[str]:
    members = result.get("members", "")
    if not isinstance(members, str):
        return []
    return [member for member in members.split("^G") if member]
