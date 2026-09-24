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
