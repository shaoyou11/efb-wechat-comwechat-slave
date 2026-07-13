import importlib.util
import sys
import tempfile
import types
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "finder_feed.py"
)
SPEC = importlib.util.spec_from_file_location("finder_feed", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
parse_finder_feed = MODULE.parse_finder_feed


FINDER_XML = """<?xml version="1.0"?>
<msg>
  <appmsg>
    <title>当前微信版本不支持展示该内容，请升级至最新版本。</title>
    <type>51</type>
    <url>https://support.weixin.qq.com/update/</url>
    <finderFeed>
      <objectId><![CDATA[14964026784220842528]]></objectId>
      <feedType><![CDATA[4]]></feedType>
      <nickname><![CDATA[小小电影课代表]]></nickname>
      <desc><![CDATA[关于三个老婆都给自己戴绿帽这件事]]></desc>
      <mediaCount>1</mediaCount>
      <objectNonceId><![CDATA[nonce-value]]></objectNonceId>
      <mediaList>
        <media>
          <thumbUrl><![CDATA[https://example.test/thumb.jpg]]></thumbUrl>
          <videoPlayDuration>29</videoPlayDuration>
          <url><![CDATA[https://example.test/video.mp4]]></url>
          <coverUrl><![CDATA[https://example.test/cover.jpg]]></coverUrl>
          <mediaType>4</mediaType>
        </media>
      </mediaList>
    </finderFeed>
  </appmsg>
</msg>
"""


def test_parse_finder_feed_extracts_video_metadata():
    feed = parse_finder_feed(FINDER_XML)

    assert feed.author == "小小电影课代表"
    assert feed.description == "关于三个老婆都给自己戴绿帽这件事"
    assert feed.video_url == "https://example.test/video.mp4"
    assert feed.cover_url == "https://example.test/cover.jpg"
    assert feed.duration_seconds == 29
    assert feed.object_id == "14964026784220842528"
    assert feed.object_nonce_id == "nonce-value"
    assert feed.share_url == (
        "https://channels.weixin.qq.com/web/pages/feed?"
        "oid=14964026784220842528&nid=nonce-value"
    )


def test_parse_finder_feed_ignores_normal_link():
    assert parse_finder_feed("<msg><appmsg><type>5</type></appmsg></msg>") is None


def _load_msg_deco(monkeypatch):
    package = types.ModuleType("efb_wechat_comwechat_slave")
    package.__path__ = [str(MODULE_PATH.parent)]
    monkeypatch.setitem(sys.modules, "efb_wechat_comwechat_slave", package)
    monkeypatch.setitem(
        sys.modules,
        "efb_wechat_comwechat_slave.finder_feed",
        MODULE,
    )

    class MsgType:
        Text = "text"
        Image = "image"
        Animation = "animation"
        Video = "video"
        File = "file"
        Link = "link"
        Unsupported = "unsupported"

    class Message:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Placeholder:
        def __init__(self, *args, **kwargs):
            self.__dict__.update(kwargs)

    ehforwarderbot = types.ModuleType("ehforwarderbot")
    ehforwarderbot.MsgType = MsgType
    ehforwarderbot.Chat = Placeholder
    ehforwarderbot.coordinator = Placeholder()
    monkeypatch.setitem(sys.modules, "ehforwarderbot", ehforwarderbot)

    chat_module = types.ModuleType("ehforwarderbot.chat")
    chat_module.ChatMember = Placeholder
    monkeypatch.setitem(sys.modules, "ehforwarderbot.chat", chat_module)

    message_module = types.ModuleType("ehforwarderbot.message")
    message_module.Substitutions = Placeholder
    message_module.Message = Message
    message_module.LinkAttribute = Placeholder
    message_module.LocationAttribute = Placeholder
    monkeypatch.setitem(sys.modules, "ehforwarderbot.message", message_module)

    types_module = types.ModuleType("ehforwarderbot.types")
    types_module.MessageID = str
    monkeypatch.setitem(sys.modules, "ehforwarderbot.types", types_module)

    magic_module = types.ModuleType("magic")
    magic_module.from_file = lambda path, mime=True: (
        "video/mp4" if path.endswith(".mp4") else "image/jpeg"
    )
    monkeypatch.setitem(sys.modules, "magic", magic_module)

    for name in ("ChatMgr", "CustomTypes"):
        stub = types.ModuleType(f"efb_wechat_comwechat_slave.{name}")
        stub.ChatMgr = Placeholder
        stub.EFBGroupChat = Placeholder
        stub.EFBPrivateChat = Placeholder
        monkeypatch.setitem(
            sys.modules,
            f"efb_wechat_comwechat_slave.{name}",
            stub,
        )

    utils_module = types.ModuleType("efb_wechat_comwechat_slave.Utils")
    utils_module.download_file = lambda url: None
    monkeypatch.setitem(
        sys.modules,
        "efb_wechat_comwechat_slave.Utils",
        utils_module,
    )

    path = MODULE_PATH.parent / "MsgDeco.py"
    spec = importlib.util.spec_from_file_location(
        "efb_wechat_comwechat_slave.MsgDeco",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _temp_media(suffix):
    file = tempfile.NamedTemporaryFile(suffix=suffix)
    file.write(b"media")
    file.flush()
    return file


def test_finder_feed_wrapper_returns_video(monkeypatch):
    msg_deco = _load_msg_deco(monkeypatch)

    message = msg_deco.efb_finder_feed_wrapper(
        FINDER_XML,
        downloader=lambda url: _temp_media(".mp4"),
    )

    assert message.type == "video"
    assert message.filename == "wechat-channel.mp4"
    assert "小小电影课代表" in message.text
    assert "29 秒" in message.text
    assert "当前微信版本不支持" not in message.text


def test_finder_feed_wrapper_falls_back_to_link(monkeypatch):
    msg_deco = _load_msg_deco(monkeypatch)
    requested = []

    def downloader(url):
        requested.append(url)
        if url.endswith("video.mp4"):
            raise OSError("video expired")
        return _temp_media(".jpg")

    message = msg_deco.efb_finder_feed_wrapper(FINDER_XML, downloader=downloader)

    assert requested == ["https://example.test/video.mp4"]
    assert message.type == "text"
    assert "关于三个老婆" in message.text
    assert "https://channels.weixin.qq.com/web/pages/feed?" in message.text


def test_finder_feed_wrapper_falls_back_to_text(monkeypatch):
    msg_deco = _load_msg_deco(monkeypatch)

    def unavailable(url):
        raise OSError("expired")

    message = msg_deco.efb_finder_feed_wrapper(
        FINDER_XML,
        downloader=unavailable,
    )

    assert message.type == "text"
    assert "小小电影课代表" in message.text
    assert "关于三个老婆" in message.text
