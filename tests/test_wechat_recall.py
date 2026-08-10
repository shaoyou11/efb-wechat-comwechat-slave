import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "wechat_recall.py"
SPEC = importlib.util.spec_from_file_location("wechat_recall", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_recall_metadata_identifies_self_by_flag_or_wxid():
    assert MODULE.build_wechat_recall_metadata({"isSendMsg": True}, "me") == {"actor": "self"}
    assert MODULE.build_wechat_recall_metadata({"wxid": "me"}, "me") == {"actor": "self"}


def test_recall_metadata_defaults_to_other_without_raw_payload():
    assert MODULE.build_wechat_recall_metadata({"wxid": "someone"}, "me") == {"actor": "other"}
