from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .. import database
from ..services.note_service import generate_note
from ..services.subtitle_service import is_mock_placeholder_segments

router = APIRouter(prefix="/api/videos", tags=["notes"])


@router.get("/{video_id}/note")
def get_note(video_id: int) -> dict:
    note = database.fetch_one("SELECT * FROM notes WHERE video_id = ?", (video_id,))
    return {"ok": True, "data": note}


@router.post("/{video_id}/note/generate")
def generate_note_endpoint(video_id: int) -> dict:
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    segments = database.fetch_all("SELECT * FROM transcript_segments WHERE video_id = ? ORDER BY start_time", (video_id,))
    if is_mock_placeholder_segments(segments):
        database.execute("DELETE FROM notes WHERE video_id = ?", (video_id,))
        return {"ok": True, "data": None}
    chapters = database.fetch_all("SELECT * FROM chapters WHERE video_id = ? ORDER BY start_time", (video_id,))
    highlights = database.fetch_all("SELECT * FROM highlights WHERE video_id = ? ORDER BY start_time", (video_id,))
    content = generate_note(video["title"], chapters, highlights, segments)
    with database.get_conn() as conn:
        conn.execute("DELETE FROM notes WHERE video_id = ?", (video_id,))
        conn.execute("INSERT INTO notes (video_id, markdown_content) VALUES (?, ?)", (video_id, content))
    return {"ok": True, "data": {"markdown_content": content}}


@router.get("/{video_id}/export/markdown")
def export_markdown(video_id: int):
    note = database.fetch_one("SELECT markdown_content FROM notes WHERE video_id = ?", (video_id,))
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    return PlainTextResponse(note["markdown_content"], media_type="text/markdown")
