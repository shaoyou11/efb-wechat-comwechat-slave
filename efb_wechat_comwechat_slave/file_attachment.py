"""Recognize native file callbacks independently of storage layout."""
import os
import xml.etree.ElementTree as ET


def file_attachment(message):
    if not isinstance(message, str) or "<!DOCTYPE" in message.upper():
        return None
    try:
        root = ET.fromstring(message)
        app = root if root.tag == "appmsg" else root.find("appmsg")
        if app is None or app.findtext("type") not in ("6", "74"):
            return None
        name = (app.findtext("title") or "附件").replace(chr(92), "/").rsplit("/", 1)[-1]
        size = app.findtext("appattach/totallen") or "0"
        return {"name": name or "附件", "size": int(size) if size.isdecimal() else 0}
    except (ET.ParseError, ValueError):
        return None


def attachment_path(path, media_root):
    if not isinstance(path, str) or not path or chr(0) in path:
        return None
    root = os.path.realpath(media_root)
    normalized = path.replace(chr(92), "/")
    if normalized.startswith(root + "/"):
        relative = normalized[len(root) + 1:]
    elif "/WeChat Files/" in normalized:
        relative = normalized.split("/WeChat Files/", 1)[1]
    else:
        relative = normalized.lstrip("/")
    if any(part == ".." or ":" in part for part in relative.split("/")):
        return None
    resolved = os.path.realpath(os.path.join(root, relative))
    return resolved if resolved.startswith(root + os.sep) else None
