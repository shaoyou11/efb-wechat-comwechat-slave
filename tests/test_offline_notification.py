from pathlib import Path


LOGIN_GUIDANCE = "检测到微信未登录，请发送 /login 获取登录二维码，或发送 /wechat 打开微信管理"


def test_all_offline_prompts_use_simplified_commands():
    source = (
        Path(__file__).parents[1]
        / "efb_wechat_comwechat_slave"
        / "ComWechat.py"
    ).read_text(encoding="utf-8")

    assert source.count(LOGIN_GUIDANCE) == 2
    assert "请发送 /extra" not in source
