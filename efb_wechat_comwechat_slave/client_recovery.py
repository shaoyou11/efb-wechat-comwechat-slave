"""Explicit user-requested recovery for a stopped WeChat supervisor."""
import json
import time
import uuid
from urllib import request


class ClientRecoveryPaused(RuntimeError):
    def __init__(self, state):
        super().__init__("微信客户端已停止恢复")
        self.state = state


def recover_for_login(health_url, state, opener=None, sleep=None):
    opener = opener or request.urlopen
    sleep = sleep or time.sleep
    if state.get("recovery_protocol") != 1:
        return "微信客户端已停止恢复，当前服务不支持安全重试，需要检查微信服务。"
    payload = {"source": "manual", "request_id": "login-" + uuid.uuid4().hex}
    req = request.Request(health_url.rsplit("/", 1)[0] + "/recover",
                          data=json.dumps(payload).encode(), method="POST",
                          headers={"Content-Type": "application/json"})
    try:
        with opener(req, timeout=5) as response:
            result = json.load(response)
        if result.get("accepted") is not True:
            return "微信重建请求未被接受，请查看微信服务状态；没有重复发起重建。"
    except Exception:
        return "微信重建请求未确认，没有自动重发；请稍后查看微信状态。"
    deadline = time.monotonic() + 75
    for _ in range(38):
        if time.monotonic() >= deadline:
            break
        sleep(2)
        try:
            with opener(health_url, timeout=3) as response:
                current = json.load(response)
        except Exception:
            continue
        if current.get("ok") and current.get("state") == "running":
            return None
        if current.get("state") == "paused" and not current.get("request_pending"):
            return "微信客户端本次重建失败，已停止重试；暂时无法生成二维码，请检查微信启动日志。"
    return "微信启动尚未完成，暂时不能生成二维码；本次只请求了一次重建，请稍后查看状态。"
