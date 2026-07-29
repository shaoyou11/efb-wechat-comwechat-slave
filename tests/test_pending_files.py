import importlib.util
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
        vendor_specific={"telegram_delivery_status": "failed"}
    )
    missing = SimpleNamespace(vendor_specific={})

    assert MODULE.delivery_confirmed([delivered])
    assert MODULE.delivery_confirmed([persisted_failure])
    assert not MODULE.delivery_confirmed([missing])
    assert not MODULE.delivery_confirmed([None])
