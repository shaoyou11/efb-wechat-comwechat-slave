import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "finder_feed_jobs.py"
SPEC = importlib.util.spec_from_file_location("finder_feed_jobs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FinderFeedJobStore = MODULE.FinderFeedJobStore


def test_job_store_does_not_persist_media_urls(tmp_path: Path):
    store = FinderFeedJobStore(tmp_path / "jobs.db", expiry_seconds=60)
    job_id = store.enqueue(
        source_uid="100",
        chat_uid="room@chatroom",
        chat_kind="group",
        author_uid="wxid-user",
        object_id="object-id",
        object_nonce_id="nonce-id",
    )

    record = store.get(job_id)
    assert record["state"] == "waiting"
    database_bytes = (tmp_path / "jobs.db").read_bytes()
    assert b"video.mp4" not in database_bytes
    assert b"https://" not in database_bytes
    assert store.request(job_id)["state"] == "requested"
    assert store.claim(job_id)["state"] == "processing"
    store.finish(job_id, "sent")
    assert store.get(job_id)["state"] == "sent"


def test_job_store_rejects_duplicate_claim_and_expires(tmp_path: Path):
    store = FinderFeedJobStore(tmp_path / "jobs.db", expiry_seconds=60)
    job_id = store.enqueue(
        source_uid="100",
        chat_uid="user",
        chat_kind="private",
        author_uid="wxid-user",
        now=100,
    )
    assert store.expire_stale(now=159) == 0
    assert store.request(job_id, now=101)["state"] == "requested"
    assert store.claim(job_id, now=102)["state"] == "processing"
    assert store.claim(job_id, now=103)["state"] == "processing"
