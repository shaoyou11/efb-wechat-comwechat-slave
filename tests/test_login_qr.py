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
has_active_qr = MODULE.has_active_qr
has_recent_qr = MODULE.has_recent_qr
select_revoke_uids = MODULE.select_revoke_uids


class LoginQrStoreTests(unittest.TestCase):
    def test_persists_and_removes_qr_message_ids(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "login-qrcodes.json"
            store = LoginQrStore(path)
            store.add("qr-1", created_at=100)

            restored = LoginQrStore(path)
            self.assertEqual(restored.records(), [{"uid": "qr-1", "created_at": 100}])

            restored.remove("qr-1")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

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

    def test_recent_qr_defers_transient_login_state(self):
        records = [{"uid": "qr", "created_at": 100}]

        self.assertTrue(has_recent_qr(records, now=120, grace_seconds=30))
        self.assertFalse(has_recent_qr(records, now=130, grace_seconds=30))

    def test_reauth_reuses_active_qr_without_calling_wechat_api(self):
        with TemporaryDirectory() as directory:
            channel = ComWeChatChannel.__new__(ComWeChatChannel)
            channel.login_qr_store = LoginQrStore(
                Path(directory) / "login-qrcodes.json"
            )
            channel.login_qr_store.add("existing", created_at=100)
            channel.login_qr_ttl_seconds = 180
            channel.login_qr_lock = threading.RLock()
            channel.login_qr_in_progress = threading.Event()
            channel.get_qrcode = mock.Mock()

            with mock.patch(
                "efb_wechat_comwechat_slave.ComWechat.time.time",
                return_value=200,
            ):
                result = channel.reauth()

            self.assertIn("上一张", result)
            channel.get_qrcode.assert_not_called()

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
            channel.logger = mock.Mock()
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


if __name__ == "__main__":
    unittest.main()
