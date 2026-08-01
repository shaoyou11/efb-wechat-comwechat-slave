import ast
from pathlib import Path


SOURCE = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "ComWechat.py"
)


def test_comwechat_imports_group_chat_for_attachment_queueing():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "ehforwarderbot.chat"
        and any(alias.name == "GroupChat" for alias in node.names)
        for node in tree.body
    )
