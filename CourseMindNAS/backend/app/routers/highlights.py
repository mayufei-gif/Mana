from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import database
from ..services.highlight_service import extract_highlights
from ..services.subtitle_service import is_mock_placeholder_segments

router = APIRouter(prefix="/api/videos", tags=["highlights"])


class ManualRangeRequest(BaseModel):
    start_segment_id: int
    end_segment_id: int
    title: str | None = None
    highlight_type: str | None = None
    summary: str | None = None


class HighlightUpdateRequest(BaseModel):
    title: str | None = None
    highlight_type: str | None = None
    summary: str | None = None
    status: str | None = None


def _segment_text(segment: dict) -> str:
    return str(segment.get("cleaned_text") or segment.get("text") or "").strip()


def _compact(text: str, max_length: int = 32) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return f"{normalized[:max_length]}..." if len(normalized) > max_length else normalized


def _format_time(seconds: float) -> str:
    value = max(0, int(seconds or 0))
    hour = value // 3600
    minute = (value % 3600) // 60
    second = value % 60
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def _format_range(start: float, end: float) -> str:
    return f"{_format_time(start)} - {_format_time(end)}"


def _fold_source_star_rows(rows: list[dict]) -> list[dict]:
    folded: list[dict] = []
    by_key: dict[tuple[str, int | None], dict] = {}
    for row in rows:
        key = (str(row.get("source_role") or ""), row.get("segment_id"))
        item = by_key.get(key)
        if item is None:
            item = {
                "source_role": row.get("source_role"),
                "segment_id": row.get("segment_id"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "text": row.get("text"),
                "cleaned_text": row.get("cleaned_text"),
                "segment_index": row.get("segment_index"),
                "star_id": row.get("star_id"),
                "star_color": row.get("star_color"),
                "tag_label": row.get("tag_label"),
                "star_tags": [],
            }
            by_key[key] = item
            folded.append(item)
        star_id = row.get("star_id")
        if star_id is not None:
            tag = {
                "star_id": star_id,
                "star_color": row.get("star_color") or "gold",
                "tag_label": row.get("tag_label"),
            }
            if tag not in item["star_tags"]:
                item["star_tags"].append(tag)
            if item.get("star_id") is None:
                item["star_id"] = tag["star_id"]
                item["star_color"] = tag["star_color"]
                item["tag_label"] = tag["tag_label"]
    return folded


def _highlight_sources(highlight_id: int) -> list[dict]:
    rows = database.fetch_all(
        """
        SELECT
            hs.source_role,
            ts.id AS segment_id,
            ts.start_time,
            ts.end_time,
            ts.text,
            ts.cleaned_text,
            ts.segment_index,
            ss.id AS star_id,
            COALESCE(ss.star_color, 'gold') AS star_color,
            COALESCE(NULLIF(TRIM(ss.tag_label), ''), ss.tag_key) AS tag_label
        FROM highlight_sources hs
        JOIN transcript_segments ts ON ts.id = hs.segment_id
        LEFT JOIN starred_segments ss ON ss.segment_id = ts.id
        WHERE hs.highlight_id = ?
        ORDER BY ts.start_time ASC, ts.id ASC
        """,
        (highlight_id,),
    )
    return _fold_source_star_rows(rows)


def _row_with_sources(row: dict) -> dict:
    row["sources"] = _highlight_sources(int(row["id"]))
    return row


@router.get("/{video_id}/highlights")
def get_highlights(video_id: int) -> dict:
    rows = database.fetch_all(
        """
        SELECT *
        FROM highlights
        WHERE video_id = ?
          AND COALESCE(status, 'candidate') != 'disabled'
        ORDER BY start_time ASC
        """,
        (video_id,),
    )
    for row in rows:
        _row_with_sources(row)
    return {"ok": True, "data": rows}


@router.get("/{video_id}/highlights/{highlight_id}/sources")
def get_highlight_sources(video_id: int, highlight_id: int) -> dict:
    highlight = database.fetch_one("SELECT id FROM highlights WHERE id = ? AND video_id = ?", (highlight_id, video_id))
    if not highlight:
        raise HTTPException(status_code=404, detail="highlight not found")
    rows = database.fetch_all(
        """
        SELECT
            hs.source_role,
            ts.id AS segment_id,
            ts.start_time,
            ts.end_time,
            ts.text,
            ts.cleaned_text,
            ts.segment_index,
            ss.id AS star_id,
            COALESCE(ss.star_color, 'gold') AS star_color,
            COALESCE(NULLIF(TRIM(ss.tag_label), ''), ss.tag_key) AS tag_label
        FROM highlight_sources hs
        JOIN transcript_segments ts ON ts.id = hs.segment_id
        LEFT JOIN starred_segments ss ON ss.segment_id = ts.id
        WHERE hs.highlight_id = ?
        ORDER BY ts.start_time ASC, ts.id ASC
        """,
        (highlight_id,),
    )
    return {"ok": True, "data": _fold_source_star_rows(rows)}


@router.post("/{video_id}/highlights/manual-range")
def create_manual_range_highlight(video_id: int, payload: ManualRangeRequest) -> dict:
    start_segment = database.fetch_one(
        "SELECT * FROM transcript_segments WHERE id = ? AND video_id = ?",
        (payload.start_segment_id, video_id),
    )
    end_segment = database.fetch_one(
        "SELECT * FROM transcript_segments WHERE id = ? AND video_id = ?",
        (payload.end_segment_id, video_id),
    )
    if not start_segment or not end_segment:
        raise HTTPException(status_code=404, detail="segment not found")

    start_time = float(start_segment["start_time"])
    end_time = float(end_segment["end_time"])
    if float(end_segment["start_time"]) < float(start_segment["start_time"]):
        start_segment, end_segment = end_segment, start_segment
        start_time = float(start_segment["start_time"])
        end_time = float(end_segment["end_time"])
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="invalid highlight time range")

    segments = database.fetch_all(
        """
        SELECT *
        FROM transcript_segments
        WHERE video_id = ?
          AND start_time >= ?
          AND end_time <= ?
        ORDER BY start_time ASC, id ASC
        """,
        (video_id, float(start_segment["start_time"]), float(end_segment["end_time"])),
    )
    if not segments:
        raise HTTPException(status_code=400, detail="no subtitle segments in selected range")

    joined_text = " ".join(_segment_text(segment) for segment in segments if _segment_text(segment))
    title = (payload.title or "").strip() or _compact(joined_text, 30) or "我的重点区间"
    highlight_type = (payload.highlight_type or "").strip() or "自定义"
    summary = (payload.summary or "").strip() or _compact(joined_text, 120) or "用户手动划定的重点区间。"

    with database.get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO highlights (
                video_id, start_time, end_time, type, title, content, importance,
                source_method, status, source_segment_count, review_status, review_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 5, 'manual_range', 'confirmed', ?, '未复习', 0, CURRENT_TIMESTAMP)
            """,
            (video_id, start_time, end_time, highlight_type, title, summary, len(segments)),
        )
        highlight_id = int(cursor.lastrowid)
        for index, segment in enumerate(segments):
            if len(segments) == 1:
                role = "start_segment"
            elif index == 0:
                role = "start_segment"
            elif index == len(segments) - 1:
                role = "end_segment"
            else:
                role = "middle_segment"
            conn.execute(
                """
                INSERT OR IGNORE INTO highlight_sources (highlight_id, segment_id, source_role)
                VALUES (?, ?, ?)
                """,
                (highlight_id, int(segment["id"]), role),
            )

    row = database.fetch_one("SELECT * FROM highlights WHERE id = ? AND video_id = ?", (highlight_id, video_id))
    if not row:
        raise HTTPException(status_code=500, detail="highlight creation failed")
    return {"ok": True, "data": _row_with_sources(row)}


@router.patch("/{video_id}/highlights/{highlight_id}")
def update_highlight(video_id: int, highlight_id: int, payload: HighlightUpdateRequest) -> dict:
    highlight = database.fetch_one("SELECT * FROM highlights WHERE id = ? AND video_id = ?", (highlight_id, video_id))
    if not highlight:
        raise HTTPException(status_code=404, detail="highlight not found")
    values = {
        "title": payload.title.strip() if payload.title is not None else highlight["title"],
        "type": payload.highlight_type.strip() if payload.highlight_type is not None else highlight["type"],
        "content": payload.summary.strip() if payload.summary is not None else highlight["content"],
        "status": payload.status.strip() if payload.status is not None else highlight.get("status"),
    }
    if not values["title"]:
        raise HTTPException(status_code=400, detail="title cannot be empty")
    if not values["content"]:
        raise HTTPException(status_code=400, detail="summary cannot be empty")
    database.execute(
        """
        UPDATE highlights
        SET title = ?, type = ?, content = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND video_id = ?
        """,
        (values["title"], values["type"] or "自定义", values["content"], values["status"] or "confirmed", highlight_id, video_id),
    )
    row = database.fetch_one("SELECT * FROM highlights WHERE id = ? AND video_id = ?", (highlight_id, video_id))
    return {"ok": True, "data": _row_with_sources(row)}


@router.delete("/{video_id}/highlights/{highlight_id}")
def delete_highlight(video_id: int, highlight_id: int) -> dict:
    highlight = database.fetch_one("SELECT id FROM highlights WHERE id = ? AND video_id = ?", (highlight_id, video_id))
    if not highlight:
        raise HTTPException(status_code=404, detail="highlight not found")
    database.execute(
        """
        UPDATE highlights
        SET status = 'disabled', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND video_id = ?
        """,
        (highlight_id, video_id),
    )
    return {"ok": True, "data": {"id": highlight_id, "status": "disabled"}}


@router.get("/{video_id}/highlights/export-markdown")
def export_highlights_markdown(
    video_id: int,
    scope: str = Query("my_highlights"),
    mode: str = Query("clean"),
) -> dict:
    video = database.fetch_one("SELECT id, title FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    if scope != "my_highlights":
        raise HTTPException(status_code=400, detail="only scope=my_highlights is supported")

    highlights = database.fetch_all(
        """
        SELECT *
        FROM highlights
        WHERE video_id = ?
          AND COALESCE(status, 'candidate') = 'confirmed'
          AND source_method IN ('manual_range', 'user_confirmed')
        ORDER BY start_time ASC, id ASC
        """,
        (video_id,),
    )

    parts: list[str] = []
    for highlight in highlights:
        sources = _highlight_sources(int(highlight["id"]))
        if not sources:
            sources = database.fetch_all(
                """
                SELECT id AS segment_id, start_time, end_time, text, cleaned_text, segment_index
                FROM transcript_segments
                WHERE video_id = ?
                  AND start_time >= ?
                  AND end_time <= ?
                ORDER BY start_time ASC, id ASC
                """,
                (video_id, float(highlight["start_time"]), float(highlight["end_time"])),
            )
        texts: list[str] = []
        seen: set[str] = set()
        for source in sources:
            text = _segment_text(source)
            if not text or text in seen:
                continue
            seen.add(text)
            texts.append(text)
        if not texts:
            continue
        content = re.sub(r"\s+", " ", " ".join(texts)).strip()
        parts.append(f"## {_format_range(float(highlight['start_time']), float(highlight['end_time']))}\n\n{content}")

    filename_base = re.sub(r'[\\/:*?"<>|]+', "_", str(video["title"])).strip() or f"video_{video_id}"
    return {
        "ok": True,
        "data": {
            "filename": f"{filename_base}_重点区间.md",
            "content": "\n\n".join(parts),
            "count": len(parts),
            "mode": mode,
        },
    }


@router.post("/{video_id}/highlights/generate")
def generate_highlights_endpoint(video_id: int) -> dict:
    video = database.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    segments = database.fetch_all("SELECT * FROM transcript_segments WHERE video_id = ? ORDER BY start_time", (video_id,))
    if is_mock_placeholder_segments(segments):
        database.execute("DELETE FROM highlights WHERE video_id = ? AND COALESCE(source_method, 'auto') != 'user_anchor'", (video_id,))
        return {"ok": True, "data": []}
    highlights = extract_highlights(segments)
    with database.get_conn() as conn:
        conn.execute("DELETE FROM highlights WHERE video_id = ? AND COALESCE(source_method, 'auto') != 'user_anchor'", (video_id,))
        for item in highlights:
            conn.execute(
                """
                INSERT INTO highlights (
                    video_id, start_time, end_time, type, title, content, importance,
                    source_method, status, source_segment_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'auto', 'candidate', 1, CURRENT_TIMESTAMP)
                """,
                (
                    video_id,
                    item["start_time"],
                    item["end_time"],
                    item["type"],
                    item["title"],
                    item["content"],
                    item["importance"],
                ),
            )
    return {"ok": True, "data": highlights}
