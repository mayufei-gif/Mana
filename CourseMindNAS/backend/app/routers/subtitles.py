from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .. import database
from ..config import settings
from ..services.subtitle_service import to_srt, to_vtt

router = APIRouter(prefix="/api/videos", tags=["subtitles"])


class StarSegmentRequest(BaseModel):
    note: str | None = None
    star_color: str | None = None
    tag_label: str | None = None


def _default_star_label(star_color: str) -> str:
    return {
        "gold": "重点",
        "red": "易错",
        "green": "方法",
        "blue": "疑问",
        "purple": "例题",
    }.get(star_color, "自定义")


def _normalize_star_tag(star_color: str | None, tag_label: str | None) -> tuple[str, str, str]:
    color = (star_color or "gold").strip() or "gold"
    label = (tag_label or "").strip() or _default_star_label(color)
    return color, label, label


def _segments(video_id: int) -> list[dict]:
    return database.fetch_all(
        """
        SELECT id, start_time, end_time, text, cleaned_text, segment_index
        FROM transcript_segments
        WHERE video_id = ?
        ORDER BY start_time ASC
        """,
        (video_id,),
    )


@router.get("/{video_id}/transcript")
def get_transcript(video_id: int) -> dict:
    return {"ok": True, "data": _segments(video_id)}


@router.get("/{video_id}/starred-segments")
def get_starred_segments(video_id: int) -> dict:
    rows = database.fetch_all(
        """
        SELECT
            ss.id AS star_id,
            ss.segment_id,
            ss.note,
            COALESCE(ss.star_color, 'gold') AS star_color,
            COALESCE(NULLIF(TRIM(ss.tag_label), ''), ss.tag_key) AS tag_label,
            ss.created_at,
            ss.updated_at,
            ts.start_time,
            ts.end_time,
            ts.text,
            ts.cleaned_text,
            ts.segment_index
        FROM starred_segments ss
        JOIN transcript_segments ts ON ts.id = ss.segment_id
        WHERE ss.video_id = ?
        ORDER BY ts.start_time ASC
        """,
        (video_id,),
    )
    return {"ok": True, "data": rows}


@router.post("/{video_id}/segments/{segment_id}/star")
def star_segment(video_id: int, segment_id: int, payload: StarSegmentRequest | None = None) -> dict:
    segment = database.fetch_one(
        "SELECT id FROM transcript_segments WHERE id = ? AND video_id = ?",
        (segment_id, video_id),
    )
    if not segment:
        raise HTTPException(status_code=404, detail="segment not found")

    note = (payload.note if payload else None) or None
    star_color, tag_label, tag_key = _normalize_star_tag(
        payload.star_color if payload else None,
        payload.tag_label if payload else None,
    )
    with database.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO starred_segments (video_id, segment_id, note, star_color, tag_label, tag_key)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id, segment_id, star_color, tag_key) DO UPDATE SET
                note = excluded.note,
                tag_label = excluded.tag_label,
                updated_at = CURRENT_TIMESTAMP
            """,
            (video_id, segment_id, note, star_color, tag_label, tag_key),
        )
    return {
        "ok": True,
        "data": {
            "video_id": video_id,
            "segment_id": segment_id,
            "starred": True,
            "star_color": star_color,
            "tag_label": tag_label,
        },
    }


@router.delete("/{video_id}/segments/{segment_id}/star")
def unstar_segment(
    video_id: int,
    segment_id: int,
    star_color: str | None = Query(default=None),
    tag_label: str | None = Query(default=None),
) -> dict:
    with database.get_conn() as conn:
        if star_color is None and tag_label is None:
            conn.execute(
                "DELETE FROM starred_segments WHERE video_id = ? AND segment_id = ?",
                (video_id, segment_id),
            )
            removed = "all"
        else:
            color, label, tag_key = _normalize_star_tag(star_color, tag_label)
            conn.execute(
                """
                DELETE FROM starred_segments
                WHERE video_id = ?
                  AND segment_id = ?
                  AND COALESCE(star_color, 'gold') = ?
                  AND COALESCE(NULLIF(TRIM(tag_key), ''), NULLIF(TRIM(tag_label), ''), '') = ?
                """,
                (video_id, segment_id, color, tag_key),
            )
            removed = label
    return {"ok": True, "data": {"video_id": video_id, "segment_id": segment_id, "starred": False, "removed": removed}}


@router.get("/{video_id}/subtitles/srt")
def get_srt(video_id: int):
    path = settings.storage_dir / "subtitles" / str(video_id) / "subtitle.srt"
    if path.exists():
        return FileResponse(path, media_type="application/x-subrip", filename="subtitle.srt")
    return PlainTextResponse(to_srt(_segments(video_id)), media_type="application/x-subrip")


@router.get("/{video_id}/subtitles/vtt")
def get_vtt(video_id: int):
    path = settings.storage_dir / "subtitles" / str(video_id) / "subtitle.vtt"
    if path.exists():
        return FileResponse(path, media_type="text/vtt", filename="subtitle.vtt")
    return PlainTextResponse(to_vtt(_segments(video_id)), media_type="text/vtt")


@router.get("/{video_id}/smart-subtitle/vtt")
def get_smart_vtt(video_id: int):
    smart_path = settings.storage_dir / "subtitles" / str(video_id) / "smart_subtitle.vtt"
    if smart_path.exists():
        return FileResponse(smart_path, media_type="text/vtt", filename="smart_subtitle.vtt")
    return get_vtt(video_id)


@router.get("/{video_id}/smart-subtitle/srt")
def get_smart_srt(video_id: int):
    smart_path = settings.storage_dir / "subtitles" / str(video_id) / "smart_subtitle.srt"
    if smart_path.exists():
        return FileResponse(smart_path, media_type="application/x-subrip", filename="smart_subtitle.srt")
    return get_srt(video_id)


@router.post("/{video_id}/transcribe")
def transcribe_alias(video_id: int) -> dict:
    video = database.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    return {"ok": False, "error": "请调用 /api/videos/{video_id}/process 统一处理视频。"}
