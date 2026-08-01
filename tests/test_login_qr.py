import json
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "login_qr.py"
SPEC = importlib.util.spec_from_file_location("login_qr", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LoginQrStore = MODULE.LoginQrStore
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


if __name__ == "__main__":
    unittest.main()
