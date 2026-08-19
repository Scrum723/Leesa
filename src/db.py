"""SQLite persistence for jobs, accounts, settings overlay, analytics, alerts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import DATA
from .models import utcnow

DB_PATH = DATA / "liaison.db"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS video_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    discovered_at TEXT NOT NULL,
    scheduled_for TEXT,
    posted_at TEXT,
    content_json TEXT DEFAULT '{}',
    results_json TEXT DEFAULT '[]',
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    handle TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    settings_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(platform, handle)
);

CREATE TABLE IF NOT EXISTS platform_settings (
    platform TEXT PRIMARY KEY,
    settings_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    platform TEXT NOT NULL,
    external_id TEXT,
    url TEXT,
    title TEXT,
    description TEXT,
    hashtags TEXT,
    status TEXT,
    posted_at TEXT,
    raw_json TEXT DEFAULT '{}',
    FOREIGN KEY(job_id) REFERENCES video_jobs(id)
);

CREATE TABLE IF NOT EXISTS comments_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    post_external_id TEXT,
    author TEXT,
    text TEXT,
    seen_at TEXT NOT NULL,
    replied INTEGER DEFAULT 0,
    reply_text TEXT DEFAULT '',
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_external_id TEXT NOT NULL,
    job_id INTEGER,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    severity TEXT NOT NULL DEFAULT 'info',
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    platform TEXT DEFAULT '',
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    title_hint TEXT DEFAULT '',
    body TEXT DEFAULT '',
    video_path TEXT DEFAULT '',
    article_path TEXT DEFAULT '',
    status_folder TEXT DEFAULT 'ready',
    job_status TEXT DEFAULT 'discovered',
    platforms_json TEXT DEFAULT '[]',
    tags_json TEXT DEFAULT '[]',
    meta_json TEXT DEFAULT '{}',
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    platform TEXT DEFAULT 'x',
    external_id TEXT DEFAULT '',
    url TEXT DEFAULT '',
    posted_at TEXT,
    results_due_at TEXT,
    results_json TEXT DEFAULT '{}',
    results_collected_at TEXT,
    report_path TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db(path: Path | None = None) -> None:
    with get_db(path) as conn:
        conn.executescript(SCHEMA)


def enqueue_video(path: str, filename: str, scheduled_for: str | None = None) -> int | None:
    """Insert job if path is new. Returns job id or None if already known."""
    with get_db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO video_jobs (path, filename, status, discovered_at, scheduled_for)
                VALUES (?, ?, 'queued', ?, ?)
                """,
                (path, filename, utcnow(), scheduled_for),
            )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None


def list_jobs(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM video_jobs WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM video_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM video_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def next_queued_job() -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM video_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [job_id]
    with get_db() as conn:
        conn.execute(f"UPDATE video_jobs SET {cols} WHERE id = ?", vals)


def insert_post(
    job_id: int | None,
    platform: str,
    external_id: str,
    url: str,
    title: str,
    description: str,
    hashtags: list[str],
    status: str,
    raw: dict[str, Any] | None = None,
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO posts
            (job_id, platform, external_id, url, title, description, hashtags, status, posted_at, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                platform,
                external_id,
                url,
                title,
                description,
                json.dumps(hashtags),
                status,
                utcnow(),
                json.dumps(raw or {}),
            ),
        )
        return int(cur.lastrowid)


def list_posts(limit: int = 100, platform: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if platform:
            rows = conn.execute(
                "SELECT * FROM posts WHERE platform = ? ORDER BY id DESC LIMIT ?",
                (platform, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def upsert_account(
    platform: str,
    handle: str,
    display_name: str = "",
    external_id: str = "",
    enabled: bool = True,
    settings: dict[str, Any] | None = None,
) -> None:
    now = utcnow()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO accounts (platform, handle, display_name, external_id, enabled, settings_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, handle) DO UPDATE SET
                display_name = excluded.display_name,
                external_id = excluded.external_id,
                enabled = excluded.enabled,
                settings_json = excluded.settings_json,
                updated_at = excluded.updated_at
            """,
            (
                platform,
                handle,
                display_name,
                external_id,
                1 if enabled else 0,
                json.dumps(settings or {}),
                now,
                now,
            ),
        )


def list_accounts() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY platform, handle").fetchall()
        return [dict(r) for r in rows]


def delete_account(account_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cur.rowcount > 0


def set_platform_settings(platform: str, settings: dict[str, Any]) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO platform_settings (platform, settings_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at = excluded.updated_at
            """,
            (platform, json.dumps(settings), utcnow()),
        )


def get_platform_settings(platform: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT settings_json FROM platform_settings WHERE platform = ?", (platform,)
        ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["settings_json"] or "{}")
        except json.JSONDecodeError:
            return {}


def get_all_platform_settings() -> dict[str, dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT platform, settings_json FROM platform_settings").fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                out[r["platform"]] = json.loads(r["settings_json"] or "{}")
            except json.JSONDecodeError:
                out[r["platform"]] = {}
        return out


def mark_comment_seen(
    platform: str,
    external_id: str,
    post_external_id: str,
    author: str,
    text: str,
    replied: bool = False,
    reply_text: str = "",
) -> bool:
    """Return True if this is a new comment."""
    with get_db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO comments_seen
                (platform, external_id, post_external_id, author, text, seen_at, replied, reply_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    platform,
                    external_id,
                    post_external_id,
                    author,
                    text,
                    utcnow(),
                    1 if replied else 0,
                    reply_text,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def insert_metrics(
    platform: str,
    post_external_id: str,
    job_id: int | None,
    views: int,
    likes: int,
    comments: int,
    shares: int,
    saves: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO metrics
            (platform, post_external_id, job_id, views, likes, comments, shares, saves, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (platform, post_external_id, job_id, views, likes, comments, shares, saves, utcnow()),
        )


def recent_metrics(days: int = 7) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM metrics
            WHERE fetched_at >= datetime('now', ?)
            ORDER BY fetched_at ASC
            """,
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]


def create_alert(
    severity: str,
    category: str,
    title: str,
    body: str = "",
    platform: str = "",
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO alerts (severity, category, title, body, platform, acknowledged, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (severity, category, title, body, platform, utcnow()),
        )
        return int(cur.lastrowid)


def list_alerts(limit: int = 50, unacked_only: bool = False) -> list[dict[str, Any]]:
    with get_db() as conn:
        if unacked_only:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE acknowledged = 0 ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def ack_alert(alert_id: int) -> None:
    with get_db() as conn:
        conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))


def set_state(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO agent_state (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, utcnow()),
        )


def get_state(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM agent_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def posts_today_count() -> int:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM video_jobs
            WHERE status IN ('posted', 'partial')
              AND date(posted_at) = date('now', 'localtime')
            """
        ).fetchone()
        return int(row["c"] if row else 0)


def upsert_content_item(item: dict[str, Any]) -> int:
    now = utcnow()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO content_items
            (kind, path, title_hint, body, video_path, article_path, status_folder, job_status,
             platforms_json, tags_json, meta_json, discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                kind=excluded.kind,
                title_hint=excluded.title_hint,
                body=excluded.body,
                video_path=excluded.video_path,
                article_path=excluded.article_path,
                status_folder=excluded.status_folder,
                platforms_json=excluded.platforms_json,
                tags_json=excluded.tags_json,
                meta_json=excluded.meta_json,
                updated_at=excluded.updated_at
            """,
            (
                item.get("kind"),
                item.get("path"),
                item.get("title_hint", ""),
                item.get("body", ""),
                item.get("video_path", ""),
                item.get("article_path", ""),
                item.get("status_folder", "ready"),
                item.get("job_status", "discovered"),
                json.dumps(item.get("platforms") or []),
                json.dumps(item.get("tags") or []),
                json.dumps(item.get("meta") or {}),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT id FROM content_items WHERE path = ?", (item.get("path"),)).fetchone()
        return int(row["id"]) if row else 0


def list_content_items(limit: int = 100, status_folder: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if status_folder:
            rows = conn.execute(
                "SELECT * FROM content_items WHERE status_folder = ? ORDER BY id DESC LIMIT ?",
                (status_folder, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM content_items ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def update_content_item(path: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [path]
    with get_db() as conn:
        conn.execute(f"UPDATE content_items SET {cols} WHERE path = ?", vals)


def create_poll(
    run_date: str,
    question: str,
    options: list[str],
    platform: str = "x",
    status: str = "prepared",
) -> int:
    now = utcnow()
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO polls
            (run_date, question, options_json, status, platform, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_date, question, json.dumps(options), status, platform, now, now),
        )
        return int(cur.lastrowid)


def update_poll(poll_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [poll_id]
    with get_db() as conn:
        conn.execute(f"UPDATE polls SET {cols} WHERE id = ?", vals)


def get_poll(poll_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
        return dict(row) if row else None


def list_polls(limit: int = 50) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM polls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def polls_due_for_results() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM polls
            WHERE status = 'posted'
              AND results_due_at IS NOT NULL
              AND results_due_at <= ?
              AND (results_collected_at IS NULL OR results_collected_at = '')
            ORDER BY id ASC
            """,
            (utcnow(),),
        ).fetchall()
        return [dict(r) for r in rows]


def poll_for_date(run_date: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM polls WHERE run_date = ? ORDER BY id DESC LIMIT 1",
            (run_date,),
        ).fetchone()
        return dict(row) if row else None
