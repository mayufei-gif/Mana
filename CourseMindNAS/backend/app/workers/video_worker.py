from __future__ import annotations

from pathlib import Path

from .. import database
from ..config import settings
from ..services import chapter_service, ffmpeg_service, highlight_service, note_service, subtitle_service
from ..services.ai_client import ai_client


def _storage(*parts: str | int) -> Path:
    path = settings.storage_dir.joinpath(*(str(part) for part in parts))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _set_video_status(
    video_id: int,
    status: str,
    error: str | None = None,
    *,
    error_stage: str | None = None,
    subtitle_status: str | None = None,
    analysis_status: str | None = None,
    note_status: str | None = None,
    missing: int | None = None,
) -> None:
    database.execute(
        """
        UPDATE videos
        SET status = ?,
            subtitle_status = COALESCE(?, subtitle_status),
            analysis_status = COALESCE(?, analysis_status),
            note_status = COALESCE(?, note_status),
            missing = COALESCE(?, missing),
            error_stage = ?,
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, subtitle_status, analysis_status, note_status, missing, error_stage, error, video_id),
    )


def _update_job(
    job_id: int,
    status: str,
    progress: int,
    step: str,
    error: str | None = None,
    *,
    error_stage: str | None = None,
    finished: bool = False,
) -> None:
    database.execute(
        """
        UPDATE jobs
        SET status = ?,
            progress = ?,
            current_step = ?,
            error_stage = ?,
            error_message = ?,
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            finished_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE finished_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, progress, step, error_stage, error, 1 if finished else 0, job_id),
    )


def process_video(video_id: int, job_id: int) -> dict:
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise ValueError(f"视频不存在: {video_id}")

    current_stage = "preparing"
    try:
        video_path = Path(video["file_path"])
        if not video_path.exists():
            current_stage = "missing"
            raise FileNotFoundError(f"原视频文件不存在: {video_path}")

        current_stage = "extracting_audio"
        _set_video_status(video_id, "extracting_audio", subtitle_status="pending", analysis_status="pending", note_status="pending", missing=0)
        _update_job(job_id, "processing", 5, "extracting_audio")
        duration = ffmpeg_service.probe_duration(video_path)
        if duration and duration / 60 > settings.max_single_video_minutes:
            raise ValueError(f"视频时长 {duration / 60:.1f} 分钟，超过 MAX_SINGLE_VIDEO_MINUTES={settings.max_single_video_minutes}")
        database.execute("UPDATE videos SET duration = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (duration, video_id))

        audio_path = _storage("audio", video_id) / "audio.mp3"
        ffmpeg_service.extract_audio(video_path, audio_path)
        _update_job(job_id, "processing", 18, "extracting_audio")

        current_stage = "splitting_audio"
        _set_video_status(video_id, "splitting_audio")
        _update_job(job_id, "processing", 28, "splitting_audio")
        chunk_dir = _storage("chunks", video_id)
        chunks = ffmpeg_service.split_audio(audio_path, chunk_dir, settings.chunk_seconds)
        _update_job(job_id, "processing", 38, "splitting_audio")

        current_stage = "transcribing"
        _set_video_status(video_id, "transcribing", subtitle_status="processing")
        _update_job(job_id, "processing", 48, "transcribing")
        raw_segments: list[dict] = []
        for idx, chunk in enumerate(chunks or [audio_path]):
            offset = idx * settings.chunk_seconds
            raw_segments.extend(ai_client.transcribe_audio(chunk, offset))
        raw_transcript_path = _storage("transcripts", video_id) / "raw_transcript.json"
        transcript_meta = {
            "video_id": video_id,
            "audio_path": str(audio_path),
            "language": settings.asr_language,
            "provider": settings.transcription_provider,
            "model": settings.transcription_model,
        }
        subtitle_service.write_transcript_json(raw_segments, raw_transcript_path, **transcript_meta)

        clean_segments = subtitle_service.normalize_segments(raw_segments)
        clean_transcript_path = _storage("transcripts", video_id) / "clean_transcript.json"
        subtitle_service.write_transcript_json(clean_segments, clean_transcript_path, **transcript_meta)
        _update_job(job_id, "processing", 60, "transcribing")

        current_stage = "optimizing_subtitle"
        _set_video_status(video_id, "optimizing_subtitle", subtitle_status="processing")
        _update_job(job_id, "processing", 68, "optimizing_subtitle")
        smart_segments = subtitle_service.build_display_segments(clean_segments, video_duration=duration)
        if not smart_segments:
            raise ValueError("未生成有效字幕，视频不会开放播放。请检查音轨或 ASR provider 配置。")
        is_mock_placeholder = subtitle_service.is_mock_placeholder_segments(smart_segments)

        if is_mock_placeholder:
            with database.get_conn() as conn:
                conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
                conn.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
                conn.execute("DELETE FROM highlights WHERE video_id = ?", (video_id,))
                conn.execute("DELETE FROM notes WHERE video_id = ?", (video_id,))
            for stale_path in [
                _storage("transcripts", video_id) / "transcript.json",
                _storage("subtitles", video_id) / "subtitle.srt",
                _storage("subtitles", video_id) / "subtitle.vtt",
                _storage("subtitles", video_id) / "smart_subtitle.srt",
                _storage("subtitles", video_id) / "smart_subtitle.vtt",
            ]:
                if stale_path.exists():
                    stale_path.unlink()
            _update_job(job_id, "completed", 100, "ready", finished=True)
            _set_video_status(video_id, "ready", subtitle_status="none", analysis_status="none", note_status="none")
            return {"video_id": video_id, "status": "ready", "segments": 0, "mock_placeholder": True}

        with database.get_conn() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
            for idx, segment in enumerate(smart_segments):
                conn.execute(
                    """
                    INSERT INTO transcript_segments (video_id, start_time, end_time, text, cleaned_text, segment_index)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (video_id, segment["start_time"], segment["end_time"], segment["text"], segment["cleaned_text"], idx),
                )

        transcript_path = _storage("transcripts", video_id) / "transcript.json"
        subtitle_service.write_transcript_json(smart_segments, transcript_path, **transcript_meta)
        subtitle_service.write_transcript_json(clean_segments, clean_transcript_path, subtitle_segments=smart_segments, **transcript_meta)
        subtitle_service.write_subtitle_files(
            clean_segments,
            _storage("subtitles", video_id) / "subtitle.srt",
            _storage("subtitles", video_id) / "subtitle.vtt",
        )
        subtitle_service.write_subtitle_files(
            smart_segments,
            _storage("subtitles", video_id) / "smart_subtitle.srt",
            _storage("subtitles", video_id) / "smart_subtitle.vtt",
        )
        _update_job(job_id, "processing", 74, "optimizing_subtitle")

        current_stage = "generating_chapters"
        _set_video_status(video_id, "generating_chapters", analysis_status="processing")
        _update_job(job_id, "processing", 80, "generating_chapters")
        chapters = chapter_service.generate_chapters(smart_segments, video["title"])

        current_stage = "generating_highlights"
        _set_video_status(video_id, "generating_highlights", analysis_status="processing")
        _update_job(job_id, "processing", 86, "generating_highlights")
        highlights = highlight_service.extract_highlights(smart_segments)
        current_stage = "generating_note"
        _set_video_status(video_id, "generating_note", note_status="processing")
        _update_job(job_id, "processing", 92, "generating_note")
        note = note_service.generate_note(video["title"], chapters, highlights, smart_segments)
        with database.get_conn() as conn:
            conn.execute("DELETE FROM chapters WHERE video_id = ?", (video_id,))
            conn.execute("DELETE FROM highlights WHERE video_id = ?", (video_id,))
            conn.execute("DELETE FROM notes WHERE video_id = ?", (video_id,))
            for chapter in chapters:
                conn.execute(
                    """
                    INSERT INTO chapters (video_id, title, start_time, end_time, summary, importance)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (video_id, chapter["title"], chapter["start_time"], chapter["end_time"], chapter["summary"], chapter["importance"]),
                )
            for item in highlights:
                conn.execute(
                    """
                    INSERT INTO highlights (video_id, start_time, end_time, type, title, content, importance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (video_id, item["start_time"], item["end_time"], item["type"], item["title"], item["content"], item["importance"]),
                )
            conn.execute(
                "INSERT INTO notes (video_id, markdown_content) VALUES (?, ?)",
                (video_id, note),
            )
        notes_dir = _storage("notes", video_id)
        (notes_dir / "note.md").write_text(note, encoding="utf-8")
        current_stage = "indexing"
        _set_video_status(video_id, "indexing", analysis_status="ready", note_status="ready")
        _update_job(job_id, "processing", 97, "indexing")

        _update_job(job_id, "completed", 100, "ready", finished=True)
        _set_video_status(video_id, "ready", subtitle_status="ready", analysis_status="ready", note_status="ready")
        return {"video_id": video_id, "status": "ready", "segments": len(smart_segments)}
    except Exception as exc:
        message = str(exc)
        missing = 1 if isinstance(exc, FileNotFoundError) else None
        final_status = "missing" if missing else "failed"
        error_stage = "missing" if missing else current_stage
        _update_job(job_id, "failed", 0, final_status, message, error_stage=error_stage, finished=True)
        _set_video_status(
            video_id,
            final_status,
            message,
            error_stage=error_stage,
            subtitle_status="failed" if error_stage in {"transcribing", "optimizing_subtitle"} else None,
            analysis_status="failed" if error_stage in {"generating_chapters", "generating_highlights", "indexing"} else None,
            note_status="failed" if error_stage == "generating_note" else None,
            missing=missing,
        )
        raise
