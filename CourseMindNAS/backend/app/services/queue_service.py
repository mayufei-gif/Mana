from __future__ import annotations

import threading
import time

from .. import database
from ..config import settings
from ..workers.video_worker import process_video
from .scanner_service import scan_video_dirs
from .settings_service import (
    effective_auto_process_max_per_round,
    effective_auto_process_new_videos,
    effective_auto_scan,
    effective_scan_interval_seconds,
    effective_scan_recursive,
    effective_video_dirs,
)


def enqueue_video(video_id: int, *, priority: int = 0, force: bool = False, job_type: str = "process_video") -> dict:
    video = database.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    if not video:
        raise ValueError(f"视频不存在: {video_id}")
    if video.get("missing"):
        raise ValueError("原视频文件不存在，无法加入处理队列。")

    active_job = database.fetch_one(
        """
        SELECT * FROM jobs
        WHERE video_id = ? AND status IN ('queued', 'processing')
        ORDER BY priority DESC, id DESC
        LIMIT 1
        """,
        (video_id,),
    )
    if active_job and not force:
        if active_job["status"] == "queued" and int(active_job.get("priority") or 0) < priority:
            database.execute(
                """
                UPDATE jobs
                SET priority = ?, current_step = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (priority, "queued", active_job["id"]),
            )
        database.execute(
            "UPDATE videos SET status = 'queued', error_stage = NULL, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (video_id,),
        )
        return {"job_id": active_job["id"], "video_id": video_id, "status": active_job["status"]}

    job_id = database.execute(
        """
        INSERT INTO jobs (
            video_id, job_type, status, progress, priority, current_step, total_steps, error_stage, error_message
        ) VALUES (?, ?, 'queued', 0, ?, 'queued', 9, NULL, NULL)
        """,
        (video_id, job_type, priority),
    )
    database.execute(
        """
        UPDATE videos
        SET status = 'queued',
            subtitle_status = CASE WHEN subtitle_status = 'ready' THEN 'pending' ELSE subtitle_status END,
            analysis_status = CASE WHEN analysis_status = 'ready' THEN 'pending' ELSE analysis_status END,
            note_status = CASE WHEN note_status = 'ready' THEN 'pending' ELSE note_status END,
            error_stage = NULL,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (video_id,),
    )
    return {"job_id": job_id, "video_id": video_id, "status": "queued"}


def enqueue_pending_videos(limit: int, *, priority: int = 0, job_type: str = "auto_process_video") -> int:
    rows = database.fetch_all(
        """
        SELECT v.id
        FROM videos v
        WHERE v.missing = 0
          AND v.status = 'pending'
          AND NOT EXISTS (
              SELECT 1 FROM jobs j
              WHERE j.video_id = v.id AND j.status IN ('queued', 'processing')
          )
        ORDER BY v.created_at DESC, v.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    for row in rows:
        enqueue_video(int(row["id"]), priority=priority, job_type=job_type)
    return len(rows)


def process_next_job() -> bool:
    job = database.fetch_one(
        """
        SELECT * FROM jobs
        WHERE status = 'queued'
        ORDER BY priority DESC, id ASC
        LIMIT 1
        """
    )
    if not job:
        return False
    process_video(video_id=int(job["video_id"]), job_id=int(job["id"]))
    return True


class CourseMindRuntime:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_scan_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="coursemind-runtime", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            processed = False
            try:
                processed = process_next_job()
            except Exception:
                processed = False
            try:
                self._auto_scan_if_needed()
                self._auto_enqueue_if_needed()
            except Exception as exc:
                database.execute(
                    """
                    INSERT INTO scan_logs (scan_dir, found_count, new_count, missing_count, error_message)
                    VALUES (?, 0, 0, 0, ?)
                    """,
                    (";".join(str(path) for path in effective_video_dirs()), str(exc)),
                )
            wait_seconds = 1 if processed else 3
            self._stop_event.wait(wait_seconds)

    def _auto_scan_if_needed(self) -> None:
        if not effective_auto_scan():
            return
        now = time.time()
        interval = effective_scan_interval_seconds()
        if now - self._last_scan_at < interval:
            return
        scan_video_dirs(effective_video_dirs(), recursive=effective_scan_recursive())
        self._last_scan_at = now

    def _auto_enqueue_if_needed(self) -> None:
        if not effective_auto_process_new_videos():
            return
        enqueue_pending_videos(effective_auto_process_max_per_round(), priority=0)


runtime = CourseMindRuntime()
