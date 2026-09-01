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


def test_scheduler_serializes_post_login_confirmation():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    comwechat = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ComWeChatChannel"
    )
    methods = {
        node.name: node
        for node in comwechat.body
        if isinstance(node, ast.FunctionDef)
    }

    scheduler_calls = [
        node
        for node in ast.walk(methods["scheduled_job"])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "confirm_login"
    ]
    assert len(scheduler_calls) == 1


def test_periodic_full_contact_refresh_is_six_hour_fallback():
    source = SOURCE.read_text(encoding="utf-8")

    assert "count % (6 * 60 * 60) == 0" in source
    assert "count % 1800 == 0" not in source


def test_manual_contact_refresh_rechecks_unresolved_ids_and_forces_sync():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    comwechat = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ComWeChatChannel"
    )
    method = next(
        node
        for node in comwechat.body
        if isinstance(node, ast.FunctionDef) and node.name == "refresh_contact_center"
    )
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert any(call.func.attr == "GetContactBySql" for call in calls)
    publish = next(call for call in calls if call.func.attr == "_publish_resolved_contact_name")
    assert any(
        keyword.arg == "force" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for keyword in publish.keywords
    )
