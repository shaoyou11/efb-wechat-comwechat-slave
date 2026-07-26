import os
from pathlib import PurePosixPath
from typing import Any, Dict, Optional


HISTORICAL_MEDIA_AGE_SECONDS = 10 * 60
HISTORICAL_MEDIA_WAIT_SECONDS = 10
NORMAL_MEDIA_WAIT_SECONDS = 120
WECHAT_FILES_MARKER = "/WeChat Files/"


def is_historical_media(
    original_timestamp: Optional[int],
    started_at: int,
) -> bool:
    if not original_timestamp:
        return False
    return started_at - int(original_timestamp) > HISTORICAL_MEDIA_AGE_SECONDS


def media_wait_timeout(historical: bool) -> int:
    if historical:
        return HISTORICAL_MEDIA_WAIT_SECONDS
    return NORMAL_MEDIA_WAIT_SECONDS


def should_use_thumbnail(
    full_image_exists: bool,
    thumbnail_exists: bool,
    elapsed_seconds: int,
    timeout_seconds: int,
) -> bool:
    return (
        not full_image_exists
        and thumbnail_exists
        and elapsed_seconds >= timeout_seconds
    )


def should_request_original_media(
    media_type: str,
    original_timestamp: Optional[int],
    started_at: int,
) -> bool:
    return (
        media_type in ("image", "video")
        and not is_historical_media(original_timestamp, started_at)
    )


def cdn_media_path(
    result: Dict[str, Any],
    media_root: str,
) -> Optional[str]:
    if not isinstance(result, dict) or not result.get("msg"):
        return None

    windows_path = result.get("path")
    if not isinstance(windows_path, str):
        return None

    normalized_path = windows_path.replace("\\", "/")
    marker_index = normalized_path.lower().find(WECHAT_FILES_MARKER.lower())
    if marker_index < 0:
        return None

    relative_path = normalized_path[
        marker_index + len(WECHAT_FILES_MARKER):
    ]
    relative_parts = PurePosixPath(relative_path).parts
    if not relative_parts or ".." in relative_parts:
        return None

    return os.path.join(media_root, *relative_parts)
