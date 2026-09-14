import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("client_recovery", Path(__file__).parents[1] / "efb_wechat_comwechat_slave/client_recovery.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def response(data):
    return io.BytesIO(json.dumps(data).encode())


class ManualRecoveryTests(unittest.TestCase):
    def test_success_after_pending_paused_state_requests_once(self):
        op = Mock(side_effect=[response({"accepted": True}), response({"state": "paused", "request_pending": True}), response({"ok": True, "state": "running"})])
        self.assertIsNone(recovery.recover_for_login("http://localhost/healthz", {"recovery_protocol": 1}, op, Mock()))
        self.assertEqual(json.loads(op.call_args_list[0].args[0].data)["source"], "manual")
        self.assertEqual(sum(not isinstance(c.args[0], str) for c in op.call_args_list), 1)

    def test_failed_replacement_does_not_retry(self):
        op = Mock(side_effect=[response({"accepted": True}), response({"state": "paused", "request_pending": False})])
        text = recovery.recover_for_login("http://localhost/healthz", {"recovery_protocol": 1}, op, Mock())
        self.assertIn("本次重建失败", text)
        self.assertEqual(op.call_count, 2)

    def test_unknown_request_result_never_reposts(self):
        op = Mock(side_effect=TimeoutError)
        self.assertIn("没有自动重发", recovery.recover_for_login("http://localhost/healthz", {"recovery_protocol": 1}, op, Mock()))
        self.assertEqual(op.call_count, 1)

    def test_old_supervisor_is_not_restarted(self):
        op = Mock()
        self.assertIn("不支持安全重试", recovery.recover_for_login("http://localhost/healthz", {}, op, Mock()))
        op.assert_not_called()

    def test_startup_wait_is_bounded_and_does_not_repost(self):
        count = []
        def op(req, **kwargs):
            count.append(req)
            return response({"state": "recovering"}) if isinstance(req, str) else response({"accepted": True})
        self.assertIn("启动尚未完成", recovery.recover_for_login("http://localhost/healthz", {"recovery_protocol": 1}, op, Mock()))
        self.assertEqual(sum(not isinstance(v, str) for v in count), 1)
        self.assertEqual(len(count), 39)
