import importlib.util
import sys
import types
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "efb_wechat_comwechat_slave"
    / "Utils.py"
)


def _load_utils(monkeypatch, response):
    for name in ("pilk", "pydub", "yaml"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    requests = types.ModuleType("requests")
    requests.get = lambda *args, **kwargs: response
    monkeypatch.setitem(sys.modules, "requests", requests)
    spec = importlib.util.spec_from_file_location("utils_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, chunks=(), error=None):
        self.chunks = chunks
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def iter_content(self, chunk_size):
        return iter(self.chunks)


def test_download_file_rejects_empty_response(monkeypatch):
    utils = _load_utils(monkeypatch, Response())

    with pytest.raises(ValueError, match="empty"):
        utils.download_file("https://example.test/video", retry=1)


def test_download_file_keeps_non_empty_response(monkeypatch):
    utils = _load_utils(monkeypatch, Response([b"video-data"]))

    downloaded = utils.download_file("https://example.test/video", retry=1)

    downloaded.seek(0)
    assert downloaded.read() == b"video-data"
