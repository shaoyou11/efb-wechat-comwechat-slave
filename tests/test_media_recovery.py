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


def test_thumbnail_is_only_used_after_full_image_timeout():
    assert not MODULE.should_use_thumbnail(True, True, 120, 120)
    assert not MODULE.should_use_thumbnail(False, True, 1, 120)
    assert MODULE.should_use_thumbnail(False, True, 120, 120)


def test_cdn_media_path_maps_windows_wechat_path_to_shared_mount():
    result = {
        "msg": 1,
        "path": (
            r"C:\Users\user\My Documents\WeChat Files"
            r"\shaoyou11\WeChatRobot\Image\123.png"
        ),
    }

    assert MODULE.cdn_media_path(result, "/comwechat/Files") == (
        "/comwechat/Files/shaoyou11/WeChatRobot/Image/123.png"
    )


def test_cdn_media_path_rejects_failed_or_unsafe_result():
    assert MODULE.cdn_media_path({"msg": 0}, "/comwechat/Files") is None
    assert MODULE.cdn_media_path(
        {"msg": 1, "path": r"C:\temp\123.png"},
        "/comwechat/Files",
    ) is None
    assert MODULE.cdn_media_path(
        {
            "msg": 1,
            "path": (
                r"C:\Users\user\My Documents\WeChat Files"
                r"\..\outside.png"
            ),
        },
        "/comwechat/Files",
    ) is None


def test_only_recent_images_and_videos_request_original_download():
    assert MODULE.should_request_original_media("image", 995, 1000)
    assert not MODULE.should_request_original_media("video", 995, 1000)
    assert not MODULE.should_request_original_media("voice", 995, 1000)
    assert not MODULE.should_request_original_media("image", 100, 1000)


def test_queued_historical_image_can_request_original_download():
    assert MODULE.should_request_original_media(
        "image",
        100,
        1000,
        allow_historical=True,
    )


def test_historical_image_does_not_use_short_fallback_when_retrying_original():
    assert not MODULE.should_use_historical_fallback(
        "image",
        100,
        1000,
        force_original_retry=True,
    )
    assert MODULE.should_use_historical_fallback(
        "image",
        100,
        1000,
        force_original_retry=False,
    )
    assert MODULE.should_use_historical_fallback(
        "voice",
        100,
        1000,
        force_original_retry=True,
    )


def test_downloaded_media_waits_until_size_is_stable():
    ready, size, since = MODULE.observe_media_file_size(
        current_size=1024,
        previous_size=None,
        stable_since=None,
        now=10.0,
    )
    assert not ready
    assert size == 1024
    assert since == 10.0

    ready, size, since = MODULE.observe_media_file_size(
        current_size=2048,
        previous_size=size,
        stable_since=since,
        now=11.0,
    )
    assert not ready
    assert size == 2048
    assert since == 11.0

    ready, size, since = MODULE.observe_media_file_size(
        current_size=2048,
        previous_size=size,
        stable_since=since,
        now=14.0,
    )
    assert ready
    assert size == 2048
    assert since == 11.0


def test_empty_media_file_is_never_ready():
    ready, size, since = MODULE.observe_media_file_size(
        current_size=0,
        previous_size=0,
        stable_since=1.0,
        now=20.0,
    )
    assert not ready
    assert size == 0
    assert since == 20.0
