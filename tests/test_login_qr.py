import json
import importlib.util
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from efb_wechat_comwechat_slave.ComWechat import ComWeChatChannel


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "login_qr.py"
SPEC = importlib.util.spec_from_file_location("login_qr", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LoginQrStore = MODULE.LoginQrStore
ManualLoginSessionStore = MODULE.ManualLoginSessionStore
active_qr_expiry = MODULE.active_qr_expiry
has_active_qr = MODULE.has_active_qr
has_recent_qr = MODULE.has_recent_qr
select_revoke_uids = MODULE.select_revoke_uids


class LoginQrStoreTests(unittest.TestCase):
    def test_cancel_qr_preserves_login_protection_and_does_not_logout(self):
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.login_qr_lock = threading.RLock()
        channel.login_qr_store = mock.Mock()
        channel.login_qr_store.records.return_value = []
        channel.revoke_login_qrcodes = mock.Mock()
        channel.manual_login_session = mock.Mock()
        channel.force_logout = mock.Mock()
        result = channel.cancel_login_qr()
        self.assertIn("不会退出微信", result)
        channel.revoke_login_qrcodes.assert_called_once_with(completed=True)
        channel.force_logout.assert_not_called()
        channel.manual_login_session.clear.assert_not_called()

    def test_cancel_qr_reports_partial_failure(self):
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.login_qr_lock = threading.RLock()
        channel.login_qr_store = mock.Mock()
        channel.login_qr_store.records.return_value = [{"uid": "qr"}]
        channel.revoke_login_qrcodes = mock.Mock()
        self.assertIn("暂未能撤回", channel.cancel_login_qr())

    def test_active_qr_expiry_does_not_extend_when_reused(self):
        records = [{"uid": "qr", "created_at": 100, "stack_generation": "a"}]

        self.assertEqual(
            active_qr_expiry(
                records,
                now=150,
                ttl_seconds=180,
                grace_seconds=60,
                stack_generation="a",
            ),
            340,
        )

    def test_manual_login_session_persists_and_expires(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manual-login-session.json"
            store = ManualLoginSessionStore(path)
            store.start(200, stack_generation="stack-a", now=100)

            restored = ManualLoginSessionStore(path)
            self.assertTrue(restored.active(now=199))
            self.assertEqual(restored.snapshot(now=199)["stack_generation"], "stack-a")
            self.assertFalse(restored.active(now=200))
            self.assertFalse(path.exists())

    def test_persists_and_removes_qr_message_ids(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "login-qrcodes.json"
            store = LoginQrStore(path)
            store.add("qr-1", created_at=100)

            restored = LoginQrStore(path)
            self.assertEqual(restored.records(), [{"uid": "qr-1", "created_at": 100}])

            restored.remove("qr-1")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_persists_stack_generation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "login-qrcodes.json"
            store = LoginQrStore(path)
            store.add("qr-1", created_at=100, stack_generation="stack-a")

            self.assertEqual(
                store.records(),
                [{
                    "uid": "qr-1",
                    "created_at": 100,
                    "stack_generation": "stack-a",
                }],
            )

    def test_success_or_failure_revokes_all_qr_codes(self):
        records = [
            {"uid": "old", "created_at": 100},
            {"uid": "new", "created_at": 190},
        ]

        self.assertEqual(
            select_revoke_uids(records, now=200, ttl_seconds=180, completed=True),
            ["old", "new"],
        )

    def test_pending_login_only_revokes_expired_qr_codes(self):
        records = [
            {"uid": "old", "created_at": 10},
            {"uid": "new", "created_at": 190},
        ]

        self.assertEqual(
            select_revoke_uids(records, now=200, ttl_seconds=180, completed=False),
            ["old"],
        )

    def test_active_qr_blocks_duplicate_generation(self):
        records = [{"uid": "qr", "created_at": 100}]

        self.assertTrue(has_active_qr(records, now=200, ttl_seconds=180))
        self.assertFalse(has_active_qr(records, now=280, ttl_seconds=180))

    def test_active_qr_only_matches_same_stack_generation(self):
        records = [{
            "uid": "qr",
            "created_at": 100,
            "stack_generation": "stack-a",
        }]

        self.assertTrue(has_active_qr(
            records,
            now=200,
            ttl_seconds=180,
            stack_generation="stack-a",
        ))
        self.assertFalse(has_active_qr(
            records,
            now=200,
            ttl_seconds=180,
            stack_generation="stack-b",
        ))

    def test_recent_qr_defers_transient_login_state(self):
        records = [{"uid": "qr", "created_at": 100}]

        self.assertTrue(has_recent_qr(records, now=120, grace_seconds=30))
        self.assertFalse(has_recent_qr(records, now=130, grace_seconds=30))

    def test_explicit_refresh_replaces_active_qr_only_after_delivery(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as directory:
            channel = ComWeChatChannel.__new__(ComWeChatChannel)
            channel.login_qr_store = LoginQrStore(Path(directory) / "qr.json")
            channel.login_qr_store.add("old", created_at=100, stack_generation="a")
            channel.login_qr_ttl_seconds = 180
            channel.login_qr_lock = threading.RLock()
            channel.login_qr_in_progress = threading.Event()
            channel.login_qr_session_grace_seconds = 60
            channel.manual_login_session = ManualLoginSessionStore(Path(directory) / "session.json")
            channel.session_events = mock.Mock()
            channel.logger = mock.Mock()
            channel.get_bridge_stack_generation = mock.Mock(return_value="a")
            channel.is_login_stable = mock.Mock(return_value=False)
            channel.get_qrcode = mock.Mock(return_value=SimpleNamespace(name="qr.png"))
            channel.user_auth_chat = SimpleNamespace(other=object())
            channel.revoke_login_qrcodes = mock.Mock()
            def delivered(*args, **kwargs):
                channel.revoke_login_qrcodes.assert_not_called()
            channel.send_efb_msgs = mock.Mock(side_effect=delivered)
            with mock.patch("efb_wechat_comwechat_slave.ComWechat.time.time", return_value=200):
                result = channel.refresh_login_qr()
            self.assertIn("请扫描二维码", result)
            channel.get_qrcode.assert_called_once()
            channel.send_efb_msgs.assert_called_once()
            channel.revoke_login_qrcodes.assert_any_call(target_uids=["old"])
            self.assertFalse(channel.login_qr_in_progress.is_set())

    def test_paused_login_reports_one_failed_recovery(self):
        from efb_wechat_comwechat_slave.client_recovery import ClientRecoveryPaused
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.supervisor_health_url = "http://localhost/healthz"
        channel.get_bridge_stack_generation = mock.Mock(
            side_effect=ClientRecoveryPaused({"state": "paused", "recovery_protocol": 1}))
        channel.get_qrcode = mock.Mock()
        with mock.patch("efb_wechat_comwechat_slave.ComWechat.recover_for_login",
                        return_value="本次重建失败") as recover:
            self.assertEqual(channel.reauth(), "本次重建失败")
        recover.assert_called_once()
        channel.get_qrcode.assert_not_called()

    def test_paused_login_does_not_retry_if_bridge_not_ready(self):
        from efb_wechat_comwechat_slave.client_recovery import ClientRecoveryPaused
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.supervisor_health_url = "http://localhost/healthz"
        channel.get_bridge_stack_generation = mock.Mock(side_effect=[
            ClientRecoveryPaused({"state": "paused", "recovery_protocol": 1}), RuntimeError()])
        with mock.patch("efb_wechat_comwechat_slave.ComWechat.recover_for_login",
                        return_value=None) as recover:
            self.assertIn("未再次发起重建", channel.reauth())
        recover.assert_called_once()

    def test_explicit_refresh_does_not_generate_when_already_logged_in(self):
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.get_bridge_stack_generation = mock.Mock(return_value="a")
        channel.login_qr_store = mock.Mock()
        channel.login_qr_lock = threading.RLock()
        channel.login_qr_in_progress = threading.Event()
        channel.is_login_stable = mock.Mock(return_value=True)
        channel.after_login = mock.Mock()
        channel.get_qrcode = mock.Mock()
        result = channel.refresh_login_qr()
        self.assertIn("当前已登录", result)
        channel.get_qrcode.assert_not_called()

    def test_reauth_reuses_active_qr_without_calling_wechat_api(self):
        with TemporaryDirectory() as directory:
            channel = ComWeChatChannel.__new__(ComWeChatChannel)
            channel.login_qr_store = LoginQrStore(
                Path(directory) / "login-qrcodes.json"
            )
            channel.login_qr_store.add(
                "existing",
                created_at=100,
                stack_generation="stack-a",
            )
            channel.login_qr_ttl_seconds = 180
            channel.login_qr_lock = threading.RLock()
            channel.login_qr_in_progress = threading.Event()
            channel.login_qr_session_grace_seconds = 60
            channel.login_qr_failure_grace_seconds = 45
            channel.manual_login_session = ManualLoginSessionStore(
                Path(directory) / "manual-login-session.json"
            )
            channel.session_events = mock.Mock()
            channel.get_bridge_stack_generation = mock.Mock(return_value="stack-a")
            channel.get_qrcode = mock.Mock()

            with mock.patch(
                "efb_wechat_comwechat_slave.ComWechat.time.time",
                return_value=200,
            ):
                result = channel.reauth()

            self.assertIn("上一张", result)
            channel.get_qrcode.assert_not_called()
            self.assertTrue(channel.manual_login_session.active(now=200))

    def test_reauth_failure_keeps_existing_expired_qr_record(self):
        with TemporaryDirectory() as directory:
            channel = ComWeChatChannel.__new__(ComWeChatChannel)
            channel.login_qr_store = LoginQrStore(
                Path(directory) / "login-qrcodes.json"
            )
            channel.login_qr_store.add("existing", created_at=10)
            channel.login_qr_ttl_seconds = 180
            channel.login_qr_lock = threading.RLock()
            channel.login_qr_in_progress = threading.Event()
            channel.login_qr_session_grace_seconds = 60
            channel.manual_login_session = ManualLoginSessionStore(
                Path(directory) / "manual-login-session.json"
            )
            channel.session_events = mock.Mock()
            channel.logger = mock.Mock()
            channel.get_bridge_stack_generation = mock.Mock(return_value="stack-a")
            channel.is_login = mock.Mock(return_value=False)
            channel.get_qrcode = mock.Mock(side_effect=ConnectionError("restarting"))

            with mock.patch(
                "efb_wechat_comwechat_slave.ComWechat.time.time",
                return_value=200,
            ):
                result = channel.reauth()

            self.assertIn("原二维码未删除", result)
            self.assertEqual(
                channel.login_qr_store.records(),
                [{"uid": "existing", "created_at": 10}],
            )
            self.assertTrue(channel.manual_login_session.active(now=244))
            self.assertFalse(channel.manual_login_session.active(now=245))

    def test_reauth_reports_bridge_recovery_before_reusing_qr(self):
        channel = ComWeChatChannel.__new__(ComWeChatChannel)
        channel.logger = mock.Mock()
        channel.get_bridge_stack_generation = mock.Mock(
            side_effect=ConnectionError("bridge restarting")
        )

        result = channel.reauth()

        self.assertIn("正在恢复", result)
        self.assertIn("已经失效", result)

    def test_reauth_rejects_qr_if_stack_changes_during_generation(self):
        with TemporaryDirectory() as directory:
            channel = ComWeChatChannel.__new__(ComWeChatChannel)
            channel.login_qr_store = LoginQrStore(
                Path(directory) / "login-qrcodes.json"
            )
            channel.login_qr_ttl_seconds = 180
            channel.login_qr_lock = threading.RLock()
            channel.login_qr_in_progress = threading.Event()
            channel.login_qr_session_grace_seconds = 60
            channel.manual_login_session = ManualLoginSessionStore(
                Path(directory) / "manual-login-session.json"
            )
            channel.session_events = mock.Mock()
            channel.logger = mock.Mock()
            channel.get_bridge_stack_generation = mock.Mock(
                side_effect=["stack-a", "stack-a", "stack-b"]
            )
            channel.is_login = mock.Mock(return_value=False)
            channel.get_qrcode = mock.Mock(return_value=mock.Mock())

            result = channel.reauth()

            self.assertIn("已经重启", result)


if __name__ == "__main__":
    unittest.main()
