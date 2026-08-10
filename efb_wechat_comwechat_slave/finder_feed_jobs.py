"""Durable, metadata-only jobs for on-demand WeChat Channels downloads."""

import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional


ACTIVE_STATES = ("waiting", "requested", "processing")
TERMINAL_STATES = ("sent", "failed", "expired")


class FinderFeedJobStore:
    """Persist job identity and state without storing XML or media URLs."""

    def __init__(
        self,
        path: Path,
        expiry_seconds: int = 6 * 60 * 60,
        retention_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.expiry_seconds = max(60, int(expiry_seconds))
        self.retention_seconds = max(60, int(retention_seconds))
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS finder_feed_jobs (
                    job_id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    source_uid TEXT NOT NULL,
                    chat_uid TEXT NOT NULL,
                    chat_kind TEXT NOT NULL,
                    author_uid TEXT NOT NULL,
                    object_id TEXT,
                    object_nonce_id TEXT,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_finder_feed_jobs_state_time "
                "ON finder_feed_jobs(state, updated_at)"
            )

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[dict]:
        return dict(row) if row is not None else None

    def enqueue(
        self,
        *,
        source_uid: str,
        chat_uid: str,
        chat_kind: str,
        author_uid: str,
        object_id: str = "",
        object_nonce_id: str = "",
        now: Optional[int] = None,
    ) -> str:
        now = int(time.time() if now is None else now)
        job_id = secrets.token_urlsafe(9)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO finder_feed_jobs (
                    job_id, created_at, updated_at, state, attempts,
                    source_uid, chat_uid, chat_kind, author_uid,
                    object_id, object_nonce_id
                ) VALUES (?, ?, ?, 'waiting', 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    now,
                    now,
                    str(source_uid),
                    str(chat_uid),
                    str(chat_kind),
                    str(author_uid),
                    str(object_id or ""),
                    str(object_nonce_id or ""),
                ),
            )
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM finder_feed_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        return self._row(row)

    def request(self, job_id: str, now: Optional[int] = None) -> Optional[dict]:
        now = int(time.time() if now is None else now)
        cutoff = now - self.expiry_seconds
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE finder_feed_jobs
                SET state = 'requested', updated_at = ?
                WHERE job_id = ? AND state = 'waiting' AND created_at >= ?
                """,
                (now, str(job_id), cutoff),
            )
        return self.get(job_id)

    def claim(self, job_id: str, now: Optional[int] = None) -> Optional[dict]:
        now = int(time.time() if now is None else now)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE finder_feed_jobs
                SET state = 'processing', attempts = attempts + 1, updated_at = ?
                WHERE job_id = ? AND state = 'requested' AND attempts < 2
                """,
                (now, str(job_id)),
            )
        return self.get(job_id)

    def finish(self, job_id: str, state: str, error_code: str = "") -> None:
        if state not in TERMINAL_STATES:
            raise ValueError("invalid terminal state")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE finder_feed_jobs
                SET state = ?, updated_at = ?, last_error = ?
                WHERE job_id = ? AND state IN ('waiting', 'requested', 'processing')
                """,
                (state, int(time.time()), str(error_code or "")[:80], str(job_id)),
            )

    def expire_stale(self, now: Optional[int] = None) -> int:
        now = int(time.time() if now is None else now)
        cutoff = now - self.expiry_seconds
        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE finder_feed_jobs
                SET state = 'expired', updated_at = ?, last_error = 'expired'
                WHERE state IN ('waiting', 'requested', 'processing') AND updated_at < ?
                """,
                (now, cutoff),
            )
            return result.rowcount

    def purge_old(self, now: Optional[int] = None) -> int:
        now = int(time.time() if now is None else now)
        cutoff = now - self.retention_seconds
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM finder_feed_jobs WHERE state IN ('sent', 'failed', 'expired') "
                "AND updated_at < ?",
                (cutoff,),
            )
            return result.rowcount

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM finder_feed_jobs GROUP BY state"
            ).fetchall()
        result = {state: 0 for state in ACTIVE_STATES + TERMINAL_STATES}
        result.update({row["state"]: row["count"] for row in rows})
        return result
