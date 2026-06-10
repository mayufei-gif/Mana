from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import database
from ..services.chapter_service import generate_chapters
from ..services.subtitle_service import is_mock_placeholder_segments

router = APIRouter(prefix="/api/videos", tags=["chapters"])


@router.get("/{video_id}/chapters")
def get_chapters(video_id: int) -> dict:
    rows = database.fetch_all("SELECT * FROM chapters WHERE video_id = ? ORDER BY start_time ASC", (video_id,))
    return {"ok": True, "data": rows}


@router.post("/{video_id}/chapters/generate")
def generate_chapters_endpoint(video_id: int) -> dict:
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    segments = database.fetch_all("SELECT * FROM transcript_segments WHERE video_id = ? ORDER BY start_time", (video_id,))
    if is_mock_placeholder_segments(segments):
        database.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
        return {"ok": True, "data": []}
    chapters = generate_chapters(segments, video["title"])
    with database.get_conn() as conn:
        conn.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
        for item in chapters:
            conn.execute(
                "INSERT INTO chapters (video_id, title, start_time, end_time, summary, importance) VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, item["title"], item["start_time"], item["end_time"], item["summary"], item["importance"]),
            )
    return {"ok": True, "data": chapters}
