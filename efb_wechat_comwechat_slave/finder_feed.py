from dataclasses import dataclass
import re
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse

from lxml import etree


VIDEO_MEDIA_ALLOWED_HOSTS = (
    "qq.com",
    "qpic.cn",
    "weixin.qq.com",
)
SHARE_URL_PATTERN = re.compile(
    r"https://(?:www\.)?weixin\.qq\.com/sph/[A-Za-z0-9_-]+"
)


def _safe_text(value: str, limit: int = 2000) -> str:
    text = str(value or "")
    text = re.sub(r"https?://\S+", "[链接已隐藏]", text)
    return text[:limit]


@dataclass(frozen=True)
class FinderFeed:
    author: str
    description: str
    video_url: str
    cover_url: str
    duration_seconds: Optional[int]
    object_id: str
    object_nonce_id: str
    source_url: str = ""

    @property
    def share_url(self) -> str:
        # The old channels.weixin.qq.com page often only displays the
        # unsupported-version screen. Only expose a real short share URL.
        parsed = urlparse(self.source_url or "")
        if parsed.scheme != "https" or parsed.hostname not in {
            "weixin.qq.com",
            "www.weixin.qq.com",
        }:
            return ""
        if not parsed.path.startswith("/sph/"):
            return ""
        return urlunparse((parsed.scheme, parsed.hostname, parsed.path, "", "", ""))

    @property
    def public_metadata(self) -> Dict[str, object]:
        """Fields safe to attach to an EFB message and persist in mappings."""
        return {
            "author": _safe_text(self.author, 120),
            "description": _safe_text(self.description),
            "duration_seconds": self.duration_seconds,
            "object_id": self.object_id,
            "share_url": self.share_url,
        }


def _first_text(xml: etree._Element, *paths: str) -> str:
    for path in paths:
        values = xml.xpath(path)
        if values and values[0]:
            return str(values[0]).strip()
    return ""


def _first_public_text(xml: etree._Element, *paths: str) -> str:
    return _safe_text(_first_text(xml, *paths))


def _find_share_url(xml: etree._Element) -> str:
    for value in xml.xpath("//text()"):
        match = SHARE_URL_PATTERN.search(str(value or ""))
        if match:
            return match.group(0)
    return ""


def parse_finder_feed(xml_text: str) -> Optional[FinderFeed]:
    parser = etree.XMLParser(
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
        recover=False,
    )
    try:
        xml = etree.fromstring(xml_text.encode("utf-8"), parser=parser)
    except (etree.XMLSyntaxError, UnicodeError, AttributeError):
        return None
    if _first_text(xml, "/msg/appmsg/type/text()") != "51":
        return None

    feeds = xml.xpath("/msg/appmsg/finderFeed | /msg/appmsg/finder_feed")
    if not feeds:
        return None
    feed = feeds[0]

    duration_text = _first_text(
        feed,
        "mediaList/media[1]/videoPlayDuration/text()",
        "media_list/media[1]/video_play_duration/text()",
    )
    try:
        duration_seconds = int(duration_text)
    except (TypeError, ValueError):
        duration_seconds = None

    return FinderFeed(
        author=_first_public_text(feed, "nickname/text()"),
        description=_first_public_text(feed, "desc/text()"),
        video_url=_first_text(
            feed,
            "mediaList/media[1]/url/text()",
            "media_list/media[1]/url/text()",
        ),
        cover_url=_first_text(
            feed,
            "mediaList/media[1]/coverUrl/text()",
            "mediaList/media[1]/thumbUrl/text()",
            "media_list/media[1]/cover_url/text()",
            "media_list/media[1]/thumb_url/text()",
        ),
        duration_seconds=duration_seconds,
        object_id=_first_text(feed, "objectId/text()", "object_id/text()"),
        object_nonce_id=_first_text(
            feed,
            "objectNonceId/text()",
            "object_nonce_id/text()",
        ),
        source_url=_find_share_url(xml),
    )
