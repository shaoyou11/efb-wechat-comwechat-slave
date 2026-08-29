import logging
import tempfile
import threading
import requests as requests
import re
import json
import yaml
import time
from typing import Dict , Any, Iterable, Optional
import pilk
import pydub
import os
from urllib.parse import urlparse

#从本地读取配置
def load_config(path : str) -> Dict[str, None]:
    """
    Load configuration from path specified by the framework.
    Configuration file is in YAML format.
    """
    if not os.path.exists(path):
        return
    with open( path , "rb") as f:
        d = yaml.full_load(f)
        if not d:
            return
        config: Dict[str, Any] = d
    return config

def redact_url(url: str) -> str:
    """Return a log-safe URL without query tokens or fragments."""
    try:
        parsed = urlparse(str(url))
        host = parsed.hostname or "unknown-host"
        path = parsed.path or "/"
        return f"{parsed.scheme}://{host}{path}"
    except (TypeError, ValueError):
        return "<invalid-url>"


def _host_allowed(host: Optional[str], allowed_hosts: Optional[Iterable[str]]) -> bool:
    if not allowed_hosts:
        return True
    host = (host or "").lower().rstrip(".")
    for allowed in allowed_hosts:
        suffix = str(allowed).lower().lstrip(".").rstrip(".")
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def _looks_like_media(path: str, expected_kind: Optional[str]) -> bool:
    if not expected_kind:
        return True
    with open(path, "rb") as handle:
        header = handle.read(512)
    if expected_kind == "video":
        return (
            b"ftyp" in header[:128]
            or header.startswith(b"\x1a\x45\xdf\xa3")
            or header.startswith(b"RIFF")
            or header.startswith(b"\x00\x00\x01\xba")
            or header.startswith(b"\x00\x00\x01\xb3")
        )
    if expected_kind == "image":
        return (
            header.startswith(b"\xff\xd8\xff")
            or header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"GIF8")
            or header.startswith(b"RIFF") and b"WEBP" in header[:16]
        )
    return True


def download_file(
    url: str,
    retry: int = 3,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    max_bytes: Optional[int] = None,
    timeout=(5, 20),
    expected_kind: Optional[str] = None,
    require_https: bool = False,
) -> tempfile:
    """
    A function that downloads files from given URL
    Remember to close the file once you are done with the file!
    :param retry: The max retries before giving up
    :param url: The URL that points to the file
    """
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported media URL scheme")
    if require_https and parsed.scheme != "https":
        raise ValueError("media URL must use HTTPS")
    if not _host_allowed(parsed.hostname, allowed_hosts):
        raise ValueError("media URL host is not allowed")

    if max_bytes is None:
        max_bytes = int(os.getenv("EFB_MEDIA_DOWNLOAD_MAX_BYTES", 512 * 1024 * 1024))
    max_bytes = max(1, int(max_bytes))
    attempts = max(1, int(retry))
    last_error = None
    for count in range(1, attempts + 1):
        file = None
        response = None
        try:
            file = tempfile.NamedTemporaryFile(prefix="efb-media-", mode="w+b")
            os.fchmod(file.fileno(), 0o600)
            response = requests.get(
                url,
                stream=True,
                timeout=timeout,
                allow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36 "
                        "MicroMessenger/3.9.12"
                    ),
                    "Referer": "https://weixin.qq.com/",
                },
            )
            response.raise_for_status()
            response_url = getattr(response, "url", url)
            response_parsed = urlparse(str(response_url))
            if require_https and response_parsed.scheme != "https":
                raise ValueError("media redirect is not HTTPS")
            if not _host_allowed(response_parsed.hostname, allowed_hosts):
                raise ValueError("media redirect host is not allowed")
            headers = getattr(response, "headers", {}) or {}
            content_length = headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError("media response exceeds size limit")
            content_type = str(headers.get("Content-Type", "")).lower()
            if expected_kind and content_type.startswith("text/"):
                raise ValueError("media response is text, not media")
            total = 0
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("media response exceeds size limit")
                    file.write(chunk)
            if file.tell() == 0:
                raise ValueError("Downloaded file is empty")
            file.flush()
            os.fsync(file.fileno())
            file.seek(0)
            if not _looks_like_media(file.name, expected_kind):
                raise ValueError("media content signature is invalid")
            close_response = getattr(response, "close", None)
            if callable(close_response):
                close_response()
            response = None
            file.seek(0)
            return file
        except Exception as e:
            last_error = e
            if file is not None:
                file.close()
            logging.getLogger(__name__).warning(
                "媒体下载失败 url=%s attempt=%s/%s reason=%s",
                redact_url(url),
                count,
                attempts,
                type(e).__name__,
            )
            if count < attempts:
                time.sleep(min(2, count))
        finally:
            close_response = getattr(response, "close", None)
            if callable(close_response):
                close_response()
    raise last_error

def wait_for_local_file(
    file: str,
    timeout_seconds: float = 10,
    poll_interval: float = 0.5,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> None:
    deadline = monotonic_fn() + max(0, timeout_seconds)
    while True:
        try:
            if os.path.getsize(file) > 0:
                return
        except OSError:
            pass
        if monotonic_fn() >= deadline:
            raise FileNotFoundError(
                f"WeChat attachment is not ready after {timeout_seconds:g}s: {file}"
            )
        sleep_fn(max(0.01, poll_interval))


def wechatimagedecode( file : str) -> tempfile:
    """
    代码来源 https://github.com/zhangxiaoyang/WechatImageDecoder
    """
    def do_magic(header_code, buf):
        return header_code ^ list(buf)[0] if buf else 0x00
    
    def decode(magic, buf):
        return bytearray([b ^ magic for b in list(buf)])

    def guess_encoding(buf):
        headers = {
            'jpg': (0xff, 0xd8),
            'png': (0x89, 0x50),
            'gif': (0x47, 0x49),
        }
        for encoding in headers:
            header_code, check_code = headers[encoding] 
            magic = do_magic(header_code, buf)
            _, code = decode(magic, buf[:2])
            if check_code == code:
                return (encoding, magic)
        return None

    wait_for_local_file(file)
    with open(file , 'rb') as f:
        buf = bytearray(f.read())
    file_type, magic = guess_encoding(buf)

    ret_file = tempfile.NamedTemporaryFile()
    with open(ret_file.name , 'wb') as f:
        f.write(decode(magic, buf))
    f.close()
    return ret_file

def load_local_file_to_temp(file : str) -> tempfile:
    """
    从本地文件读取文件到临时文件
    """
    ret_file = tempfile.NamedTemporaryFile()
    with open(file , 'rb') as f:
        ret_file.write(f.read())
    f.close()
    return ret_file

def load_temp_file_to_local(file : tempfile , path : str) -> None:
    """
    从临时文件写到本地
    """
    with open(path , 'wb') as f:
        f.write(file.read())
    f.close()

def convert_silk_to_mp3(file : tempfile) -> tempfile:
    """
    将silk文件转换为mp3文件
    """
    f = tempfile.NamedTemporaryFile()
    file.seek(0)
    silk_header = file.read(10)
    file.seek(0)
    if b"#!SILK_V3" in silk_header:
        pilk.decode(file.name, f.name)
        file.close()
        pydub.AudioSegment.from_raw(file= f , sample_width=2, frame_rate=24000, channels=1) \
            .export( f , format="ogg", codec="libopus",
                    parameters=['-vbr', 'on'])
    return f


WC_EMOTICON_CONVERSION = {
    '[微笑]': '😃', '[Smile]': '😃',
    '[撇嘴]': '😖', '[Grimace]': '😖',
    '[色]': '😍', '[Drool]': '😍',
    '[发呆]': '😳', '[Scowl]': '😳',
    '[得意]': '😎', '[Chill]': '😎',
    '[流泪]': '😭', '[Sob]': '😭',
    '[害羞]': '☺️', '[Shy]': '☺️','[Blush]': '☺️',
    '[闭嘴]': '🤐', '[Shutup]': '🤐',
    '[睡]': '😴', '[Sleep]': '😴',
    '[大哭]': '😣', '[Cry]': '😣',
    '[尴尬]': '😰', '[Awkward]': '😰',
    '[发怒]': '😡', '[Pout]': '😡',
    '[调皮]': '😜', '[Wink]': '😜',
    '[呲牙]': '😁', '[Grin]': '😁',
    '[惊讶]': '😱', '[Surprised]': '😱',
    '[难过]': '🙁', '[Frown]': '🙁',
    '[囧]': '☺️', '[Tension]': '☺️',
    '[抓狂]': '😫', '[Scream]': '😫',
    '[吐]': '🤢', '[Puke]': '🤢',
    '[偷笑]': '🙈', '[Chuckle]': '🙈',
    '[愉快]': '☺️', '[Joyful]': '☺️',
    '[白眼]': '🙄', '[Slight]': '🙄',
    '[傲慢]': '😕', '[Smug]': '😕',
    '[困]': '😪', '[Drowsy]': '😪',
    '[惊恐]': '😱', '[Panic]': '😱',
    '[流汗]': '😓', '[Sweat]': '😓',
    '[憨笑]': '😄', '[Laugh]': '😄',
    '[悠闲]': '😏', '[Loafer]': '😏',
    '[奋斗]': '💪', '[Strive]': '💪',
    '[咒骂]': '😤', '[Scold]': '😤',
    '[疑问]': '❓', '[Doubt]': '❓',
    '[嘘]': '🤐', '[Shhh]': '🤐',
    '[晕]': '😲', '[Dizzy]': '😲',
    '[衰]': '😳', '[BadLuck]': '😳',
    '[骷髅]': '💀', '[Skull]': '💀',
    '[敲打]': '👊', '[Hammer]': '👊',
    '[再见]': '🙋\u200d♂', '[Bye]': '🙋\u200d♂',
    '[擦汗]': '😥', '[Relief]': '😥',
    '[抠鼻]': '🤷\u200d♂', '[DigNose]': '🤷\u200d♂',
    '[鼓掌]': '👏', '[Clap]': '👏',
    '[坏笑]': '👻','[壞笑]': '👻', '[Trick]': '👻',
    '[左哼哼]': '😾', '[Bah！L]': '😾', 
    '[右哼哼]': '😾', '[Bah！R]': '😾',
    '[哈欠]': '😪', '[Yawn]': '😪',
    '[鄙视]': '😒', '[Lookdown]': '😒',
    '[委屈]': '😣', '[Wronged]': '😣',
    '[快哭了]': '😔', '[Puling]': '😔',
    '[阴险]': '😈', '[Sly]': '😈',
    '[亲亲]': '😘', '[Kiss]': '😘',
    '[可怜]': '😻', '[Whimper]': '😻',
    '[菜刀]': '🔪', '[Cleaver]': '🔪',
    '[西瓜]': '🍉', '[Melon]': '🍉',
    '[啤酒]': '🍺', '[Beer]': '🍺',
    '[咖啡]': '☕', '[Coffee]': '☕',
    '[猪头]': '🐷', '[Pig]': '🐷',
    '[玫瑰]': '🌹', '[Rose]': '🌹',
    '[凋谢]': '🥀', '[Wilt]': '🥀',
    '[嘴唇]': '💋', '[Lip]': '💋',
    '[爱心]': '❤️', '[Heart]': '❤️',
    '[心碎]': '💔', '[BrokenHeart]': '💔',
    '[蛋糕]': '🎂', '[Cake]': '🎂',
    '[炸弹]': '💣', '[Bomb]': '💣',
    '[便便]': '💩', '[Poop]': '💩',
    '[月亮]': '🌃', '[Moon]': '🌃',
    '[太阳]': '🌞', '[Sun]': '🌞',
    '[拥抱]': '🤗', '[Hug]': '🤗',
    '[强]': '👍', '[Strong]': '👍', '[ThumbsUp]': '👍',
    '[弱]': '👎', '[Weak]': '👎', '[ThumbsDown]': '👎',
    '[握手]': '🤝', '[Shake]': '🤝',
    '[胜利]': '✌️', '[Victory]': '✌️',
    '[抱拳]': '🙏', '[Salute]': '🙏',
    '[勾引]': '💁\u200d♂', '[Beckon]': '💁\u200d♂',
    '[拳头]': '👊', '[Fist]': '👊',
    '[OK]': '👌',
    '[跳跳]': '💃', '[Waddle]': '💃',
    '[发抖]': '🙇', '[Tremble]': '🙇',
    '[怄火]': '😡', '[Aaagh!]': '😡',
    '[转圈]': '🕺', '[Twirl]': '🕺',
    '[嘿哈]': '🤣', '[Hey]': '🤣',
    '[捂脸]': '🤦\u200d♂', '[Facepalm]': '🤦\u200d♂',
    '[奸笑]': '😜', '[Smirk]': '😜',
    '[机智]': '🤓', '[Smart]': '🤓',
    '[皱眉]': '😟', '[Concerned]': '😟',
    '[耶]': '✌️', '[Yeah!]': '✌️',
    '[红包]': '🧧', '[Packet]': '🧧',
    '[鸡]': '🐥', '[Chick]': '🐥',
    '[蜡烛]': '🕯️', '[Candle]': '🕯️',
    '[糗大了]': '😥',
    '[Thumbs Up]': '👍', '[Pleased]': '😊',
    '[Rich]': '🀅',
    '[Pup]': '🐶',
    '[吃瓜]': '🙄\u200d🍉','[Onlooker]': '🙄\u200d🍉',
    '[加油]': '💪\u200d😁', '[GoForIt]':  '💪\u200d😁',
    '[加油加油]': '💪\u200d😷',
    '[汗]': '😓', '[Sweats]' : '😓', 
    '[天啊]': '😱', '[OMG]' :'😱', 
    '[一言難盡]': '🤔', '[Emm]': '🤔',
    '[社会社会]': '😏', '[Respect]': '😏', 
    '[旺柴]': '🐶', '[Doge]': '🐶', 
    '[Awesome]': '🐶\u200d😏', 
    '[好的]': '😏\u200d👌', '[NoProb]': '😏\u200d👌', 
    '[哇]': '🤩','[Wow]': '🤩',
    '[打脸]': '😟\u200d🤚', '[MyBad]': '😟\u200d🤚', 
    '[破涕为笑]': '😂', '[破涕為笑]': '😂','[Lol]': '😂',
    '[苦涩]': '😭', '[Hurt]': '😭', 
    '[翻白眼]': '🙄', '[Boring]': '🙄', 
    '[爆竹]': '🧨', '[Firecracker]': '🧨',  
    '[烟花]': '🎆', '[Fireworks]': '🎆', 
    '[裂开]': '💔', '[Broken]' : '💔',
    '[福]': '🧧', '[Blessing]': '🧧', 
    '[發]': '🀅',
    '[礼物]': '🎁', '[Gift]': '🎁', 
    '[庆祝]': '🎉', '[Party]': '🎉',
    '[合十]': '🙏', '[Worship]' : '🙏',
    '[叹气]': '😮‍💨','[Sigh]': '😮‍💨',
    '[让我看看]': '👀', '[LetMeSee]': '👀', 
    '[666]': '6️⃣6️⃣6️⃣',
    '[无语]': '😑', '[Duh]': '😑', 
    '[失望]': '😞', '[Let Down]': '😞', 
    '[恐惧]': '😨', '[Terror]': '😨', 
    '[脸红]': '😳', '[Flushed]': '😳', 
    '[生病]': '😷', '[Sick]': '😷',
    '[笑脸]': '😁', '[Happy]': '😁',
}
