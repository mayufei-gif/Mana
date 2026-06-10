from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def _dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with get_conn() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _run_migrations(conn)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _default_star_label_sql(color_expr: str = "COALESCE(star_color, 'gold')") -> str:
    return f"""
        CASE {color_expr}
            WHEN 'gold' THEN '重点'
            WHEN 'red' THEN '易错'
            WHEN 'green' THEN '方法'
            WHEN 'blue' THEN '疑问'
            WHEN 'purple' THEN '例题'
            ELSE ''
        END
    """


def _has_unique_index(conn: sqlite3.Connection, table: str, columns: list[str]) -> bool:
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        index_name = str(index["name"]).replace('"', '""')
        index_columns = [row["name"] for row in conn.execute(f'PRAGMA index_info("{index_name}")').fetchall()]
        if index_columns == columns:
            return True
    return False


def _migrate_starred_segments_multi_label(conn: sqlite3.Connection) -> None:
    if _has_unique_index(conn, "starred_segments", ["video_id", "segment_id", "star_color", "tag_key"]):
        return

    conn.execute("ALTER TABLE starred_segments RENAME TO starred_segments_legacy")
    conn.execute(
        """
        CREATE TABLE starred_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            note TEXT,
            star_color TEXT DEFAULT 'gold',
            tag_label TEXT,
            tag_key TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
            UNIQUE(video_id, segment_id, star_color, tag_key)
        )
        """
    )
    default_label = _default_star_label_sql("COALESCE(star_color, 'gold')")
    conn.execute(
        f"""
        INSERT INTO starred_segments (
            id, video_id, segment_id, note, star_color, tag_label, tag_key, created_at, updated_at
        )
        SELECT
            MIN(id),
            video_id,
            segment_id,
            MAX(note),
            COALESCE(star_color, 'gold') AS normalized_color,
            COALESCE(NULLIF(TRIM(tag_label), ''), {default_label}) AS normalized_label,
            COALESCE(NULLIF(TRIM(tag_label), ''), {default_label}, '') AS normalized_key,
            MIN(created_at),
            MAX(updated_at)
        FROM starred_segments_legacy
        GROUP BY video_id, segment_id, COALESCE(star_color, 'gold'), COALESCE(NULLIF(TRIM(tag_label), ''), {default_label}, '')
        """
    )
    conn.execute("DROP TABLE starred_segments_legacy")


def _run_migrations(conn: sqlite3.Connection) -> None:
    video_columns = {
        "folder": "TEXT",
        "extension": "TEXT",
        "modified_time": "REAL",
        "quick_hash": "TEXT",
        "subtitle_status": "TEXT DEFAULT 'none'",
        "analysis_status": "TEXT DEFAULT 'none'",
        "note_status": "TEXT DEFAULT 'none'",
        "last_play_position": "REAL DEFAULT 0",
        "last_opened_at": "DATETIME",
        "missing": "INTEGER DEFAULT 0",
        "error_stage": "TEXT",
    }
    job_columns = {
        "priority": "INTEGER DEFAULT 0",
        "current_step": "TEXT",
        "total_steps": "INTEGER DEFAULT 0",
        "started_at": "DATETIME",
        "finished_at": "DATETIME",
        "error_stage": "TEXT",
    }
    for column, definition in video_columns.items():
        _ensure_column(conn, "videos", column, definition)
    for column, definition in job_columns.items():
        _ensure_column(conn, "jobs", column, definition)
    highlight_columns = {
        "source_method": "TEXT DEFAULT 'auto'",
        "status": "TEXT DEFAULT 'candidate'",
        "importance_reason": "TEXT",
        "source_segment_count": "INTEGER DEFAULT 0",
        "review_status": "TEXT DEFAULT '未复习'",
        "review_count": "INTEGER DEFAULT 0",
        "last_reviewed_at": "DATETIME",
        "user_edited_fields": "TEXT",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    }
    for column, definition in highlight_columns.items():
        _ensure_column(conn, "highlights", column, definition)
    starred_columns = {
        "star_color": "TEXT DEFAULT 'gold'",
        "tag_label": "TEXT",
        "tag_key": "TEXT DEFAULT ''",
    }
    for column, definition in starred_columns.items():
        _ensure_column(conn, "starred_segments", column, definition)
    default_label = _default_star_label_sql()
    conn.execute(
        f"""
        UPDATE starred_segments
        SET tag_label = COALESCE(NULLIF(TRIM(tag_label), ''), {default_label}),
            tag_key = COALESCE(NULLIF(TRIM(tag_key), ''), NULLIF(TRIM(tag_label), ''), {default_label}, '')
        """
    )
    _migrate_starred_segments_multi_label(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_dir TEXT NOT NULL,
            found_count INTEGER DEFAULT 0,
            new_count INTEGER DEFAULT 0,
            missing_count INTEGER DEFAULT 0,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS starred_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            note TEXT,
            star_color TEXT DEFAULT 'gold',
            tag_label TEXT,
            tag_key TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
            UNIQUE(video_id, segment_id, star_color, tag_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS highlight_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            highlight_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            source_role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(highlight_id) REFERENCES highlights(id) ON DELETE CASCADE,
            FOREIGN KEY(segment_id) REFERENCES transcript_segments(id) ON DELETE CASCADE,
            UNIQUE(highlight_id, segment_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority DESC, id ASC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_folder ON videos(folder)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_starred_segments_video_time ON starred_segments(video_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_highlight_sources_highlight ON highlight_sources(highlight_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_highlight_sources_segment ON highlight_sources(segment_id)")


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return list(conn.execute(sql, params).fetchall())


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as conn:
        cursor = conn.execute(sql, params)
        return int(cursor.lastrowid or 0)
