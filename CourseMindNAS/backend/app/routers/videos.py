from __future__ import annotations

import json
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import database
from ..config import settings
from ..services.scanner_service import scan_video_dir, scan_video_dirs
from ..services.queue_service import enqueue_video
from ..services.settings_service import effective_scan_recursive, effective_video_dirs
from ..utils.file_utils import ensure_child_path

router = APIRouter(prefix="/api/videos", tags=["videos"])


class ScanRequest(BaseModel):
    video_dir: str | None = None


class PlaybackPositionUpdate(BaseModel):
    current_time: float


BROWSER_MP4_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}
BROWSER_H264_CODECS = {"h264"}
BROWSER_MP4_AUDIO_CODECS = {"aac", "mp3"}
_PLAYABLE_LOCKS: dict[int, threading.Lock] = {}
_PLAYABLE_LOCKS_GUARD = threading.Lock()


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _playable_lock(video_id: int) -> threading.Lock:
    with _PLAYABLE_LOCKS_GUARD:
        lock = _PLAYABLE_LOCKS.get(video_id)
        if lock is None:
            lock = threading.Lock()
            _PLAYABLE_LOCKS[video_id] = lock
        return lock


def _is_valid_mp4(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    command = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _probe_media(path: Path) -> dict | None:
    command = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None


def _is_browser_playable_mp4(path: Path) -> bool:
    probe = _probe_media(path)
    if not probe:
        return False

    format_names = {
        item.strip().lower()
        for item in str(probe.get("format", {}).get("format_name", "")).split(",")
        if item.strip()
    }
    if not format_names.intersection(BROWSER_MP4_FORMATS):
        return False

    streams = probe.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not video_streams:
        return False

    video = video_streams[0]
    video_codec = str(video.get("codec_name", "")).lower()
    pix_fmt = str(video.get("pix_fmt", "")).lower()
    if video_codec not in BROWSER_H264_CODECS:
        return False
    if pix_fmt and pix_fmt not in {"yuv420p", "yuvj420p"}:
        return False

    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    for audio in audio_streams:
        audio_codec = str(audio.get("codec_name", "")).lower()
        if audio_codec and audio_codec not in BROWSER_MP4_AUDIO_CODECS:
            return False

    return True


LIST_SQL = """
SELECT
    v.*,
    COALESCE(ch.chapter_count, 0) AS chapter_count,
    COALESCE(hi.highlight_count, 0) AS highlight_count,
    CASE WHEN n.video_id IS NULL THEN 0 ELSE 1 END AS has_note,
    CASE WHEN EXISTS (
        SELECT 1
        FROM transcript_segments ts
        WHERE ts.video_id = v.id
          AND (
            ts.text LIKE '待转录片段：chunk_%'
            OR ts.cleaned_text LIKE '待转录片段：chunk_%'
            OR ts.text LIKE '%当前使用 mock provider%'
            OR ts.cleaned_text LIKE '%当前使用 mock provider%'
            OR ts.text = 'mp3。'
            OR ts.cleaned_text = 'mp3。'
          )
    ) THEN 1 ELSE 0 END AS has_mock_transcript,
    j.id AS job_id,
    j.status AS job_status,
    j.progress AS job_progress,
    j.current_step AS job_current_step,
    j.priority AS job_priority
FROM videos v
LEFT JOIN (
    SELECT video_id, COUNT(*) AS chapter_count
    FROM chapters
    GROUP BY video_id
) ch ON ch.video_id = v.id
LEFT JOIN (
    SELECT video_id, COUNT(*) AS highlight_count
    FROM highlights
    GROUP BY video_id
) hi ON hi.video_id = v.id
LEFT JOIN notes n ON n.video_id = v.id
LEFT JOIN jobs j ON j.id = (
    SELECT j2.id
    FROM jobs j2
    WHERE j2.video_id = v.id
    ORDER BY j2.id DESC
    LIMIT 1
)
"""


def _browser_playable_path(video_id: int, source_path: Path) -> Path:
    if _is_browser_playable_mp4(source_path):
        return source_path

    target_dir = settings.storage_dir / "playable"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{video_id}.browser.mp4"
    with _playable_lock(video_id):
        source_stat = source_path.stat()
        if target_path.exists() and target_path.stat().st_size > 0 and target_path.stat().st_mtime >= source_stat.st_mtime:
            if _is_valid_mp4(target_path):
                return target_path
            _remove_file(target_path)

        temp_path = target_dir / f"{video_id}.{uuid.uuid4().hex}.tmp.mp4"

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            "-level:v",
            "4.0",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(temp_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=3600)
            if not _is_valid_mp4(temp_path):
                raise HTTPException(status_code=500, detail="generated browser-playable MP4 proxy is invalid")
        except FileNotFoundError as exc:
            _remove_file(temp_path)
            raise HTTPException(status_code=500, detail="ffmpeg not found; cannot create browser-playable MP4 proxy") from exc
        except subprocess.TimeoutExpired as exc:
            _remove_file(temp_path)
            raise HTTPException(status_code=504, detail="creating browser-playable MP4 proxy timed out") from exc
        except subprocess.CalledProcessError as exc:
            _remove_file(temp_path)
            error = (exc.stderr or exc.stdout or str(exc)).strip()
            raise HTTPException(status_code=500, detail=f"failed to create browser-playable MP4 proxy: {error}") from exc
        except HTTPException:
            _remove_file(temp_path)
            raise

        temp_path.replace(target_path)
        if not _is_valid_mp4(target_path):
            _remove_file(target_path)
            raise HTTPException(status_code=500, detail="browser-playable MP4 proxy failed validation after replacement")
        return target_path


def _poster_path(video_id: int, source_path: Path) -> Path:
    target_dir = settings.storage_dir / "posters"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{video_id}.jpg"
    source_stat = source_path.stat()
    if target_path.exists() and target_path.stat().st_size > 0 and target_path.stat().st_mtime >= source_stat.st_mtime:
        return target_path

    temp_path = target_dir / f"{video_id}.{uuid.uuid4().hex}.tmp.jpg"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        "2",
        "-i",
        str(source_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=960:-2",
        "-q:v",
        "3",
        str(temp_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        _remove_file(temp_path)
        raise HTTPException(status_code=500, detail="ffmpeg not found; cannot create video poster") from exc
    except subprocess.TimeoutExpired as exc:
        _remove_file(temp_path)
        raise HTTPException(status_code=504, detail="creating video poster timed out") from exc
    except subprocess.CalledProcessError as exc:
        _remove_file(temp_path)
        error = (exc.stderr or exc.stdout or str(exc)).strip()
        raise HTTPException(status_code=500, detail=f"failed to create video poster: {error}") from exc
    except HTTPException:
        _remove_file(temp_path)
        raise
    temp_path.replace(target_path)
    return target_path


def _video_source_path(video_id: int) -> Path:
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    if video["status"] == "missing" or video["missing"] == 1:
        raise HTTPException(status_code=409, detail="video source file is missing")
    path = ensure_child_path(Path(video["file_path"]).parent, Path(video["file_path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="video file not found")
    return path


@router.get("")
def list_videos() -> dict:
    videos = database.fetch_all(f"{LIST_SQL} ORDER BY v.updated_at DESC, v.id DESC")
    return {"ok": True, "data": videos}


@router.post("/scan")
def scan_videos(payload: ScanRequest | None = None) -> dict:
    if payload and payload.video_dir:
        target = Path(payload.video_dir).resolve()
        scan_func = lambda: scan_video_dir(target, recursive=effective_scan_recursive())
    else:
        targets = effective_video_dirs()
        scan_func = lambda: scan_video_dirs(targets, recursive=effective_scan_recursive())
    try:
        result = scan_func()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.get("/{video_id}")
def get_video(video_id: int) -> dict:
    video = database.fetch_one(f"{LIST_SQL} WHERE v.id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    database.execute("UPDATE videos SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?", (video_id,))
    return {"ok": True, "data": video}


@router.delete("/{video_id}")
def delete_video(video_id: int) -> dict:
    database.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    return {"ok": True}


@router.post("/{video_id}/process")
def process_video_endpoint(video_id: int) -> dict:
    try:
        result = enqueue_video(video_id, priority=10, job_type="manual_process_video")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.post("/{video_id}/priority-process")
def priority_process_video(video_id: int) -> dict:
    try:
        result = enqueue_video(video_id, priority=100, job_type="priority_process_video")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.post("/{video_id}/reprocess")
def reprocess_video(video_id: int) -> dict:
    try:
        result = enqueue_video(video_id, priority=50, force=True, job_type="reprocess_video")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.get("/{video_id}/status")
def get_video_status(video_id: int) -> dict:
    video = database.fetch_one(f"{LIST_SQL} WHERE v.id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    job = database.fetch_one(
        "SELECT * FROM jobs WHERE video_id = ? ORDER BY id DESC LIMIT 1",
        (video_id,),
    )
    return {"ok": True, "data": {"video": video, "job": job}}


@router.get("/{video_id}/stream")
def stream_video(video_id: int) -> FileResponse:
    path = _video_source_path(video_id)
    playable_path = _browser_playable_path(video_id, path)
    if playable_path.suffix.lower() == ".mp4":
        return FileResponse(playable_path, media_type="video/mp4")
    return FileResponse(playable_path)


@router.get("/{video_id}/poster")
def video_poster(video_id: int) -> FileResponse:
    path = _video_source_path(video_id)
    poster_path = _poster_path(video_id, path)
    return FileResponse(poster_path, media_type="image/jpeg")


@router.post("/{video_id}/playback-position")
def save_playback_position(video_id: int, payload: PlaybackPositionUpdate) -> dict:
    video = database.fetch_one("SELECT id FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    current_time = max(0.0, float(payload.current_time))
    with database.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO playback_positions (video_id, current_time, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET
                current_time = excluded.current_time,
                updated_at = CURRENT_TIMESTAMP
            """,
            (video_id, current_time),
        )
        conn.execute(
            """
            UPDATE videos
            SET last_play_position = ?, last_opened_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (current_time, video_id),
        )
    return {"ok": True, "data": {"video_id": video_id, "current_time": current_time}}
