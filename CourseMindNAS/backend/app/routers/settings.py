from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..services.settings_service import load_custom_settings, save_custom_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    video_dir: str | None = None
    video_dirs: list[str] | None = None
    auto_scan: bool | None = None
    scan_interval_seconds: int | None = None
    scan_recursive: bool | None = None
    auto_process_new_videos: bool | None = None
    auto_process_max_per_round: int | None = None


@router.get("")
def get_settings() -> dict:
    custom = load_custom_settings()
    return {
        "ok": True,
        "data": {
            "video_dir": custom.get("video_dir", str(settings.video_dir)),
            "video_dirs": custom.get("video_dirs", [str(path) for path in settings.video_dirs]),
            "storage_dir": str(settings.storage_dir),
            "database_path": str(settings.database_path),
            "transcription_provider": settings.transcription_provider,
            "transcription_model": settings.transcription_model,
            "transcription_base_url": settings.transcription_base_url,
            "analysis_model": settings.analysis_model,
            "has_openai_api_key": bool(settings.openai_api_key),
            "has_transcription_api_key": bool(settings.transcription_api_key),
            "chunk_seconds": settings.chunk_seconds,
            "auto_scan": custom.get("auto_scan", settings.auto_scan),
            "scan_interval_seconds": custom.get("scan_interval_seconds", settings.scan_interval_seconds),
            "scan_recursive": custom.get("scan_recursive", settings.scan_recursive),
            "auto_process_new_videos": custom.get("auto_process_new_videos", settings.auto_process_new_videos),
            "auto_process_max_per_round": custom.get("auto_process_max_per_round", settings.auto_process_max_per_round),
            "process_concurrency": settings.process_concurrency,
            "max_auto_process_minutes_per_day": settings.max_auto_process_minutes_per_day,
            "max_single_video_minutes": settings.max_single_video_minutes,
            "video_extensions": list(settings.video_extensions),
            **custom,
        },
    }


@router.post("")
def update_settings(payload: SettingsUpdate) -> dict:
    current = save_custom_settings(payload.model_dump(exclude_none=True))
    return {"ok": True, "data": current}
