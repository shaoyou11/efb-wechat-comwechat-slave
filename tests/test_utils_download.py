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


def test_wait_for_local_file_allows_delayed_attachment(monkeypatch, tmp_path):
    utils = _load_utils(monkeypatch, Response())
    attachment = tmp_path / "delayed.dat"
    ticks = iter((0.0, 0.0, 0.5, 0.5))

    def release_file(_seconds):
        attachment.write_bytes(b"ready")

    utils.wait_for_local_file(
        str(attachment),
        timeout_seconds=1,
        poll_interval=0.1,
        sleep_fn=release_file,
        monotonic_fn=lambda: next(ticks),
    )


def test_wait_for_local_file_raises_for_missing_attachment(monkeypatch, tmp_path):
    utils = _load_utils(monkeypatch, Response())
    ticks = iter((0.0, 0.0, 1.0))

    with pytest.raises(FileNotFoundError, match="not ready"):
        utils.wait_for_local_file(
            str(tmp_path / "missing.dat"),
            timeout_seconds=1,
            poll_interval=0.1,
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: next(ticks),
        )
