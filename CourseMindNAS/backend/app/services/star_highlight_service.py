from __future__ import annotations

import sqlite3


STAR_GROUP_GAP_SECONDS = 20
CONTEXT_BEFORE_COUNT = 1
CONTEXT_AFTER_COUNT = 2


def _segment_text(segment: dict) -> str:
    return str(segment.get("cleaned_text") or segment.get("text") or "").strip()


def _compact(text: str, max_length: int = 28) -> str:
    normalized = " ".join(text.split())
    return f"{normalized[:max_length]}..." if len(normalized) > max_length else normalized


def _format_time(seconds: float) -> str:
    value = max(0, int(seconds or 0))
    minute = value // 60
    second = value % 60
    return f"{minute:02d}:{second:02d}"


def _format_range(segment: dict) -> str:
    return f"{_format_time(float(segment['start_time']))}-{_format_time(float(segment['end_time']))}"


def _star_groups(stars: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for star in stars:
        previous_group = groups[-1] if groups else None
        previous_star = previous_group[-1] if previous_group else None
        if previous_group and previous_star and float(star["start_time"]) - float(previous_star["end_time"]) <= STAR_GROUP_GAP_SECONDS:
            previous_group.append(star)
        else:
            groups.append([star])
    return groups


def rebuild_star_anchor_highlights(conn: sqlite3.Connection, video_id: int) -> list[dict]:
    """Persist user-starred subtitle clusters as reviewable highlight cards."""
    segments = conn.execute(
        """
        SELECT id, start_time, end_time, text, cleaned_text, segment_index
        FROM transcript_segments
        WHERE video_id = ?
        ORDER BY start_time ASC, id ASC
        """,
        (video_id,),
    ).fetchall()
    stars = conn.execute(
        """
        SELECT
            ss.segment_id,
            ss.note,
            ts.id,
            ts.start_time,
            ts.end_time,
            ts.text,
            ts.cleaned_text,
            ts.segment_index
        FROM starred_segments ss
        JOIN transcript_segments ts ON ts.id = ss.segment_id
        WHERE ss.video_id = ?
        ORDER BY ts.start_time ASC, ts.id ASC
        """,
        (video_id,),
    ).fetchall()

    conn.execute("DELETE FROM highlights WHERE video_id = ? AND source_method = 'user_anchor'", (video_id,))
    if not segments or not stars:
        return []

    index_by_segment_id = {int(segment["id"]): index for index, segment in enumerate(segments)}
    created: list[dict] = []
    for group in _star_groups(stars):
        anchor_indexes = [index_by_segment_id[int(star["segment_id"])] for star in group if int(star["segment_id"]) in index_by_segment_id]
        if not anchor_indexes:
            continue

        start_index = max(0, min(anchor_indexes) - CONTEXT_BEFORE_COUNT)
        end_index = min(len(segments), max(anchor_indexes) + CONTEXT_AFTER_COUNT + 1)
        context_segments = segments[start_index:end_index]
        anchor_ids = {int(star["segment_id"]) for star in group}
        starred_text = " ".join(_segment_text(star) for star in group if _segment_text(star))
        source_lines = [f"{_format_range(segment)} {_segment_text(segment)}" for segment in context_segments if _segment_text(segment)]
        importance_reason = "用户手动星标了这一段，系统自动带入前后字幕，便于按完整语境回看和复习。"
        title = f"我的星标片段：{_compact(starred_text)}"
        content = "\n\n".join(
            [
                f"重点句：{starred_text}",
                f"为什么重要：{importance_reason}",
                "来源字幕：\n" + "\n".join(source_lines),
            ]
        )

        cursor = conn.execute(
            """
            INSERT INTO highlights (
                video_id, start_time, end_time, type, title, content, importance,
                source_method, status, importance_reason, source_segment_count,
                review_status, review_count, updated_at
            )
            VALUES (?, ?, ?, 'user_anchor', ?, ?, 5, 'user_anchor', 'confirmed', ?, ?, '未复习', 0, CURRENT_TIMESTAMP)
            """,
            (
                video_id,
                float(context_segments[0]["start_time"]),
                float(context_segments[-1]["end_time"]),
                title,
                content,
                importance_reason,
                len(context_segments),
            ),
        )
        highlight_id = int(cursor.lastrowid)
        for segment in context_segments:
            segment_id = int(segment["id"])
            if segment_id in anchor_ids:
                role = "anchor"
            elif index_by_segment_id[segment_id] < min(anchor_indexes):
                role = "context_before"
            else:
                role = "context_after"
            conn.execute(
                """
                INSERT OR IGNORE INTO highlight_sources (highlight_id, segment_id, source_role)
                VALUES (?, ?, ?)
                """,
                (highlight_id, segment_id, role),
            )
        created.append(
            {
                "id": highlight_id,
                "video_id": video_id,
                "start_time": float(context_segments[0]["start_time"]),
                "end_time": float(context_segments[-1]["end_time"]),
                "type": "user_anchor",
                "title": title,
                "content": content,
                "importance": 5,
                "source_method": "user_anchor",
                "status": "confirmed",
                "importance_reason": importance_reason,
                "source_segment_count": len(context_segments),
                "review_status": "未复习",
            }
        )
    return created
