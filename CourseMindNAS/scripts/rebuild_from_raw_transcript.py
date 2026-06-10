from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import database  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import chapter_service, highlight_service, note_service, subtitle_service  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reuse raw_transcript.json to rebuild subtitles, chapters, highlights, and notes.")
    parser.add_argument("--video-id", type=int, required=True, help="Video id in the CourseMind SQLite database.")
    parser.add_argument("--force-asr", action="store_true", help="Guard flag. This script refuses ASR calls even when set.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.force_asr:
        print("force-asr requested, but this offline rebuild script never calls ASR.")
        print("Use the API reprocess flow only when you intentionally want a new ASR call.")
        return 2

    database.init_db()
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (args.video_id,))
    if not video:
        print(f"video not found: {args.video_id}")
        return 1

    transcript_dir = settings.storage_dir / "transcripts" / str(args.video_id)
    subtitle_dir = settings.storage_dir / "subtitles" / str(args.video_id)
    raw_path = transcript_dir / "raw_transcript.json"
    if not raw_path.exists():
        print(f"raw_transcript not found: {raw_path}")
        return 1

    raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_segments = raw_payload.get("segments") or []
    if not raw_segments:
        print(f"raw_transcript has no segments: {raw_path}")
        return 1

    clean_segments = subtitle_service.normalize_segments(raw_segments)
    display_segments = subtitle_service.build_display_segments(clean_segments, video_duration=video.get("duration"))
    if not display_segments:
        print("display subtitle generation returned empty")
        return 1

    meta = {key: raw_payload.get(key) for key in ("video_id", "audio_path", "language", "provider", "model")}
    subtitle_service.write_transcript_json(raw_segments, raw_path, **meta)
    subtitle_service.write_transcript_json(clean_segments, transcript_dir / "clean_transcript.json", subtitle_segments=display_segments, **meta)
    subtitle_service.write_transcript_json(display_segments, transcript_dir / "transcript.json", **meta)
    subtitle_service.write_subtitle_files(clean_segments, subtitle_dir / "subtitle.srt", subtitle_dir / "subtitle.vtt")
    subtitle_service.write_subtitle_files(display_segments, subtitle_dir / "smart_subtitle.srt", subtitle_dir / "smart_subtitle.vtt")

    chapters = chapter_service.generate_chapters(display_segments, video["title"])
    highlights = highlight_service.extract_highlights(display_segments)
    note = note_service.generate_note(video["title"], chapters, highlights, display_segments)
    with database.get_conn() as conn:
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (args.video_id,))
        for idx, segment in enumerate(display_segments):
            conn.execute(
                """
                INSERT INTO transcript_segments (video_id, start_time, end_time, text, cleaned_text, segment_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (args.video_id, segment["start_time"], segment["end_time"], segment["text"], segment["cleaned_text"], idx),
            )
        conn.execute("DELETE FROM chapters WHERE video_id = ?", (args.video_id,))
        for chapter in chapters:
            conn.execute(
                """
                INSERT INTO chapters (video_id, title, start_time, end_time, summary, importance)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (args.video_id, chapter["title"], chapter["start_time"], chapter["end_time"], chapter["summary"], chapter["importance"]),
            )
        conn.execute("DELETE FROM highlights WHERE video_id = ?", (args.video_id,))
        for item in highlights:
            conn.execute(
                """
                INSERT INTO highlights (video_id, start_time, end_time, type, title, content, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (args.video_id, item["start_time"], item["end_time"], item["type"], item["title"], item["content"], item["importance"]),
            )
        conn.execute("DELETE FROM notes WHERE video_id = ?", (args.video_id,))
        conn.execute("INSERT INTO notes (video_id, markdown_content) VALUES (?, ?)", (args.video_id, note))
        conn.execute(
            """
            UPDATE videos
            SET status = 'ready',
                subtitle_status = 'ready',
                analysis_status = 'ready',
                note_status = 'ready',
                error_stage = NULL,
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (args.video_id,),
        )

    notes_dir = settings.storage_dir / "notes" / str(args.video_id)
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "note.md").write_text(note, encoding="utf-8")

    print("reused raw_transcript")
    print("skipped real ASR")
    print("regenerated subtitle files")
    print(f"clean_stats={subtitle_service.subtitle_statistics(clean_segments)}")
    print(f"display_stats={subtitle_service.subtitle_statistics(display_segments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
