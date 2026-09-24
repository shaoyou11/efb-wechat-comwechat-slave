import importlib
import pytest
from efb_wechat_comwechat_slave.file_attachment import file_attachment, attachment_path

@pytest.mark.parametrize("extension", ["docx", "pdf", "xlsx", "zip", "txt", "bin", ""])
@pytest.mark.parametrize("kind", [6, 74])
def test_file_formats(tmp_path, extension, kind):
    name = "sample" + ("." + extension if extension else "")
    xml = f"<msg><appmsg><type>{kind}</type><title>{name}</title><appattach><totallen>7</totallen><aeskey>private-secret</aeskey></appattach></appmsg></msg>"
    info = file_attachment(xml)
    assert info == {"name": name, "size": 7}
    path = tmp_path / "account" / "Files" / "date" / name
    path.parent.mkdir(parents=True)
    path.write_bytes(b"payload")
    native = chr(92) + str(path.relative_to(tmp_path)).replace("/", chr(92))
    assert attachment_path(native, str(tmp_path)) == str(path)
    processor = importlib.import_module("efb_wechat_comwechat_slave.MsgProcess").MsgProcess
    msg = {"type": "share", "message": xml, "filepath": str(path)}
    converted = processor(msg, None)
    assert converted.filename == name
    assert converted.file.read() == b"payload"
    converted.file.close()
    msg["filepath"] = ""
    fallback = processor(msg, None)
    assert name in fallback.text
    assert "private-secret" not in fallback.text and "<appmsg>" not in fallback.text

@pytest.mark.parametrize("path", ["../escape", "a/../../escape", "C:/outside", "", "a" + chr(0)])
def test_unsafe_paths(tmp_path, path):
    assert attachment_path(path, str(tmp_path)) is None

@pytest.mark.parametrize("xml", ["<msg><appmsg><type>5</type></appmsg></msg>", "broken", "<!DOCTYPE msg><msg/>"])
def test_non_files(xml):
    assert file_attachment(xml) is None

@pytest.mark.parametrize('layout', ['Files', 'FileStorage'])
@pytest.mark.parametrize('absolute', [True, False])
def test_queue_file_callbacks_once(tmp_path, layout, absolute):
    import ast
    import re
    import time
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock
    source = (Path(__file__).parents[1] / 'efb_wechat_comwechat_slave/ComWechat.py').read_text()
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'handle_msg')
    for arg in node.args.args:
        arg.annotation = None
    namespace = dict(re=re, time=time, file_attachment=file_attachment, attachment_path=attachment_path)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'callback', 'exec'), namespace)
    worker = SimpleNamespace(cache={}, dir=str(tmp_path), queue_file_message=Mock(), logger=Mock())
    relative = 'account/' + layout + '/file.zip'
    path = str(tmp_path / relative) if absolute else relative
    msg = {'type': 'share', 'message': '<msg><appmsg><type>6</type><title>file.zip</title><appattach><totallen>40000000</totallen></appattach></appmsg></msg>', 'filepath': path.replace('/', chr(92)), 'msgid': 'one'}
    namespace['handle_msg'](worker, msg, SimpleNamespace(uid='author'), SimpleNamespace(uid='chat'))
    worker.queue_file_message.assert_called_once()
    assert worker.queue_file_message.call_args[0][0] == str(tmp_path / relative)
    assert msg['_expected_file_size'] == 40000000
    assert msg['wait_for_stable_media'] is True
    namespace['handle_msg'](worker, msg, None, SimpleNamespace(uid='chat'))
    worker.queue_file_message.assert_called_once()
