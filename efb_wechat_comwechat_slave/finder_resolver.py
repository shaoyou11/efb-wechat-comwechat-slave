"""Optional private resolver adapter; disabled unless explicitly configured."""

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests


LOGGER = logging.getLogger(__name__)


def _read_token(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def resolve_feed(object_id: str, object_nonce_id: str) -> Optional[dict]:
    """Call a private resolver using opaque IDs; never log its response URL."""
    endpoint = os.getenv("EFB_FINDER_RESOLVER_URL", "").strip()
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        LOGGER.warning("视频号解析器地址无效")
        return None
    token = _read_token(os.getenv("EFB_FINDER_RESOLVER_TOKEN_FILE", ""))
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(
            endpoint,
            json={"object_id": str(object_id), "object_nonce_id": str(object_nonce_id)},
            headers=headers,
            timeout=(3, 8),
        )
        response.raise_for_status()
        payload = response.json()
    except (OSError, ValueError, requests.RequestException, json.JSONDecodeError) as error:
        LOGGER.warning("视频号私有解析器失败: %s", type(error).__name__)
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "video_url": str(payload.get("video_url") or ""),
        "cover_url": str(payload.get("cover_url") or ""),
    }
