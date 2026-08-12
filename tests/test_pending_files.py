import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "pending_files.py"
)
SPEC = importlib.util.spec_from_file_location("pending_files", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _channel_class():
    if "wechatrobot" not in sys.modules:
        sys.modules["wechatrobot"] = types.SimpleNamespace(WeChatRobot=object)
    if "yaml" not in sys.modules:
        sys.modules["yaml"] = types.SimpleNamespace(full_load=lambda _handle: {})
    if "pilk" not in sys.modules:
        sys.modules["pilk"] = types.SimpleNamespace(decode=lambda *_args: None)
    if "magic" not in sys.modules:
        sys.modules["magic"] = types.SimpleNamespace(from_file=lambda *_args: "")
    if "rich" not in sys.modules:
        rich = types.ModuleType("rich")
        rich.print = print
        rich_console = types.ModuleType("rich.console")
        rich_console.Console = object
        sys.modules["rich"] = rich
        sys.modules["rich.console"] = rich_console
    from efb_wechat_comwechat_slave.ComWechat import ComWeChatChannel

    return ComWeChatChannel


def test_pending_file_store_survives_reload(tmp_path):
    path = tmp_path / "pending-files.json"
    store = MODULE.PendingFileStore(path)
    store.put("/data/example.doc", {"msg": {"msgid": 1}})

    restored = MODULE.PendingFileStore(path)

    assert restored.items() == [
        ("/data/example.doc", {"msg": {"msgid": 1}})
    ]
    restored.remove("/data/example.doc")
    assert MODULE.PendingFileStore(path).items() == []


def test_delivery_confirmation_requires_explicit_master_status():
    delivered = SimpleNamespace(
        vendor_specific={"telegram_delivery_status": "delivered"}
    )
    persisted_failure = SimpleNamespace(
        vendor_specific={"telegram_delivery_status": "stored_for_retry"}
    )
    ordinary_failure = SimpleNamespace(
        vendor_specific={"telegram_delivery_status": "failed"}
    )
    missing = SimpleNamespace(vendor_specific={})

    assert MODULE.delivery_confirmed([delivered])
    assert MODULE.delivery_confirmed([persisted_failure])
    assert not MODULE.delivery_confirmed([ordinary_failure])
    assert not MODULE.delivery_confirmed([missing])
    assert not MODULE.delivery_confirmed([None])


def test_build_pending_record_accepts_non_share_attachment():
    author = SimpleNamespace(uid="wxid_author", name="Author", alias=None)
    chat = SimpleNamespace(uid="wxid_chat", name="Chat")
    msg = {
        "msgid": 2,
        "type": "image",
        "filepath": "/data/image.jpg",
        "_media_observed_size": 1024,
        "_media_stable_since": 99.0,
        "wait_for_stable_media": True,
    }

    record = MODULE.build_pending_file_record(
        msg=msg,
        author=author,
        chat=chat,
        chat_kind="private",
    )

    assert record["msg"]["type"] == "image"
    assert record["msg"]["wait_for_stable_media"] is True
    assert "_media_observed_size" not in record["msg"]
    assert "_media_stable_since" not in record["msg"]
    assert record["chat_uid"] == "wxid_chat"


def test_pending_store_serializes_unexpected_values_safely(tmp_path):
    path = tmp_path / "pending-files.json"
    store = MODULE.PendingFileStore(path)
    store.put(
        "/data/example.bin",
        {"msg": {"msgid": 3, "unexpected": b"bytes"}},
    )

    restored = MODULE.PendingFileStore(path).items()
    assert restored[0][1]["msg"]["unexpected"] == "bytes"


def test_pending_file_can_be_requested_for_immediate_delivery(tmp_path):
    ComWeChatChannel = _channel_class()
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"image")

    channel = ComWeChatChannel.__new__(ComWeChatChannel)
    channel.file_msg = {
        str(path): (
            {"type": "image", "wait_for_stable_media": True},
            object(),
            object(),
        )
    }
    channel.file_retry_at = {str(path): 100}

    assert channel.request_pending_file_delivery(str(path)) == "queued"
    assert channel.file_retry_at[str(path)] == 0
    assert channel.file_msg[str(path)][0]["wait_for_stable_media"] is False


def test_pending_file_can_be_removed_without_deleting_media():
    ComWeChatChannel = _channel_class()

    class Store:
        def __init__(self):
            self.removed = []

        def remove(self, path):
            self.removed.append(path)

    store = Store()
    channel = ComWeChatChannel.__new__(ComWeChatChannel)
    channel.file_msg = {"/data/photo.jpg": (object(), object(), object())}
    channel.file_retry_at = {"/data/photo.jpg": 100}
    channel.pending_file_store = store

    assert channel.remove_pending_file("/data/photo.jpg") == "removed"
    assert "/data/photo.jpg" not in channel.file_msg
    assert channel.file_retry_at == {}
    assert store.removed == ["/data/photo.jpg"]


def test_media_path_state_rejects_directory_and_empty_file(tmp_path):
    directory = tmp_path / "attachment-root"
    directory.mkdir()
    empty = tmp_path / "empty.jpg"
    empty.touch()
    ready = tmp_path / "ready.jpg"
    ready.write_bytes(b"image")

    assert MODULE.media_path_state(str(directory)) == "invalid"
    assert MODULE.media_path_state(str(empty)) == "empty"
    assert MODULE.media_path_state(str(ready)) == "ready"
    assert MODULE.media_path_state(str(tmp_path / "missing")) == "missing"


def test_pending_directory_cannot_be_forced_into_delivery(tmp_path):
    ComWeChatChannel = _channel_class()
    channel = ComWeChatChannel.__new__(ComWeChatChannel)
    channel.file_msg = {
        str(tmp_path): ({"type": "image"}, object(), object())
    }
    channel.file_retry_at = {}

    assert channel.request_pending_file_delivery(str(tmp_path)) == "not_ready"
