from __future__ import annotations

from fastapi import APIRouter, Query

from .. import database

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(q: str = Query(..., min_length=1)) -> dict:
    like = f"%{q}%"
    transcript_hits = database.fetch_all(
        """
        SELECT v.id AS video_id, v.title AS video_title, t.start_time, 'subtitle' AS hit_type,
               COALESCE(t.cleaned_text, t.text) AS content
        FROM transcript_segments t
        JOIN videos v ON v.id = t.video_id
        WHERE t.text LIKE ? OR t.cleaned_text LIKE ?
        ORDER BY t.start_time ASC
        LIMIT 50
        """,
        (like, like),
    )
    highlight_hits = database.fetch_all(
        """
        SELECT v.id AS video_id, v.title AS video_title, h.start_time, 'highlight' AS hit_type,
               h.content AS content
        FROM highlights h
        JOIN videos v ON v.id = h.video_id
        WHERE h.title LIKE ? OR h.content LIKE ?
        ORDER BY h.importance DESC, h.start_time ASC
        LIMIT 50
        """,
        (like, like),
    )
    note_hits = database.fetch_all(
        """
        SELECT v.id AS video_id, v.title AS video_title, 0 AS start_time, 'note' AS hit_type,
               n.markdown_content AS content
        FROM notes n
        JOIN videos v ON v.id = n.video_id
        WHERE n.markdown_content LIKE ?
        LIMIT 20
        """,
        (like,),
    )
    video_hits = database.fetch_all(
        """
        SELECT id AS video_id, title AS video_title, 0 AS start_time, 'video' AS hit_type,
               COALESCE(folder || ' / ', '') || title AS content
        FROM videos
        WHERE title LIKE ? OR folder LIKE ?
        LIMIT 20
        """,
        (like, like),
    )
    return {"ok": True, "data": video_hits + highlight_hits + note_hits + transcript_hits}


@router.post("/qa")
def qa_placeholder() -> dict:
    return {
        "ok": False,
        "error": "AI 问答接口已预留。完成字幕和搜索闭环后，再接入 RAG/向量检索。",
    }
