from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from lxml import etree


@dataclass(frozen=True)
class FinderFeed:
    author: str
    description: str
    video_url: str
    cover_url: str
    duration_seconds: Optional[int]
    object_id: str
    object_nonce_id: str

    @property
    def share_url(self) -> str:
        if not self.object_id or not self.object_nonce_id:
            return ""
        query = urlencode({"oid": self.object_id, "nid": self.object_nonce_id})
        return f"https://channels.weixin.qq.com/web/pages/feed?{query}"


def _first_text(xml: etree._Element, *paths: str) -> str:
    for path in paths:
        values = xml.xpath(path)
        if values and values[0]:
            return str(values[0]).strip()
    return ""


def parse_finder_feed(xml_text: str) -> Optional[FinderFeed]:
    xml = etree.fromstring(xml_text.encode("utf-8"))
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
        author=_first_text(feed, "nickname/text()"),
        description=_first_text(feed, "desc/text()"),
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
    )
