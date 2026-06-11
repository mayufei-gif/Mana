#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend import file_index


def insert_record(conn: sqlite3.Connection, rowid: int, title: str, published_at: str, body: str = "") -> None:
    payload = {
        "title": title,
        "published_at": published_at,
        "发布时间": published_at,
        "source": "测试源",
    }
    text = " ".join([title, body, "测试源"])
    tokens = file_index.search_tokens_for_text(text)
    conn.execute(
        """
        INSERT INTO records (
            rowid, id, kind, title, body, meta, url, folo_url,
            folo_matched, folo_label, timestamp, tokens, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rowid,
            f"test-{rowid}",
            "历史情报",
            title,
            body,
            "测试源",
            f"https://example.com/{rowid}",
            "",
            0,
            "",
            file_index.parse_search_datetime(published_at).timestamp(),
            tokens,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.execute("INSERT INTO records_fts(rowid, tokens) VALUES (?, ?)", (rowid, tokens))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "search_index.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE records (
                rowid INTEGER PRIMARY KEY,
                id TEXT,
                kind TEXT,
                title TEXT,
                body TEXT,
                meta TEXT,
                url TEXT,
                folo_url TEXT,
                folo_matched INTEGER,
                folo_label TEXT,
                timestamp REAL,
                tokens TEXT,
                payload_json TEXT
            )
            """
        )
        conn.execute("CREATE VIRTUAL TABLE records_fts USING fts5(tokens, content='')")
        insert_record(conn, 1, "国务院政策政策政策政策旧闻", "2026-06-01 08:00:00", "国务院 政策 政策 政策 政策")
        insert_record(conn, 2, "政策简讯新消息", "2026-06-10 08:00:00", "政策")
        insert_record(conn, 3, "政治观察中间消息", "2026-06-09 08:00:00", "政治")
        insert_record(conn, 4, "InfoRadar Folo 表格摘要", "2026-06-11 08:00:00", "政治 政策 自动生成摘要")
        conn.commit()
        conn.close()

        file_index.SEARCH_INDEX_DB = db
        file_index.SEARCH_RESULT_CACHE.clear()

        result = file_index.search_history_records("政治", limit=10, offset=0, mode="smart")
        titles = [item["title"] for item in result.get("results") or []]
        expected = ["政策简讯新消息", "政治观察中间消息", "国务院政策政策政策政策旧闻"]
        if titles[:3] != expected:
            raise AssertionError(f"搜索结果必须先按发布时间倒序，再按相关度排序；got={titles[:3]}")
        if not any(term in result.get("results", [{}])[0].get("title", "") for term in ["政策", "政治"]):
            raise AssertionError(f"政治必须能通过模糊扩展命中政策类内容：{titles}")

    print({"ok": True, "query": "政治", "order": "published_at_desc_then_score"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
