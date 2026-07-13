import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "media_recovery.py"
)
SPEC = importlib.util.spec_from_file_location("media_recovery", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_recent_media_keeps_normal_timeout():
    assert not MODULE.is_historical_media(950, 1000)
    assert MODULE.media_wait_timeout(False) == 120


def test_old_media_gets_short_recovery_window():
    assert MODULE.is_historical_media(100, 1000)
    assert MODULE.media_wait_timeout(True) == 10


def test_missing_timestamp_is_not_treated_as_history():
    assert not MODULE.is_historical_media(0, 1000)
    assert not MODULE.is_historical_media(None, 1000)
