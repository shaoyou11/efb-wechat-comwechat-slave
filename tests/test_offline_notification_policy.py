import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "offline_notification.py"
)
SPEC = importlib.util.spec_from_file_location("offline_notification", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
OfflineNotificationPolicy = MODULE.OfflineNotificationPolicy


def test_first_offline_observation_notifies():
    policy = OfflineNotificationPolicy(interval_seconds=8 * 60 * 60)

    assert policy.observe(logged_in=False, now=100.0) is True


def test_repeated_offline_observation_before_interval_does_not_notify():
    policy = OfflineNotificationPolicy(interval_seconds=8 * 60 * 60)
    policy.observe(logged_in=False, now=100.0)

    assert policy.observe(logged_in=False, now=100.0 + 8 * 60 * 60 - 1) is False


def test_offline_observation_at_interval_notifies_again():
    policy = OfflineNotificationPolicy(interval_seconds=8 * 60 * 60)
    policy.observe(logged_in=False, now=100.0)

    assert policy.observe(logged_in=False, now=100.0 + 8 * 60 * 60) is True


def test_login_resets_offline_notification_cycle():
    policy = OfflineNotificationPolicy(interval_seconds=8 * 60 * 60)
    policy.observe(logged_in=False, now=100.0)
    assert policy.observe(logged_in=True, now=200.0) is False

    assert policy.observe(logged_in=False, now=201.0) is True
