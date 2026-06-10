from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import settings


def settings_json_path() -> Path:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings.storage_dir / "settings.json"


def load_custom_settings() -> dict[str, Any]:
    path = settings_json_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_custom_settings(values: dict[str, Any]) -> dict[str, Any]:
    current = load_custom_settings()
    current.update({key: value for key, value in values.items() if value is not None})
    settings_json_path().write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def effective_video_dir() -> Path:
    custom = load_custom_settings()
    raw = custom.get("video_dir") or str(settings.video_dir)
    return Path(raw).resolve()


def effective_video_dirs() -> list[Path]:
    custom = load_custom_settings()
    custom_dirs = custom.get("video_dirs")
    if isinstance(custom_dirs, list):
        paths = [Path(str(item)).resolve() for item in custom_dirs if str(item).strip()]
        if paths:
            return paths
    if custom.get("video_dir"):
        paths = [Path(str(custom["video_dir"])).resolve()]
        for path in settings.video_dirs:
            if path not in paths:
                paths.append(path)
        return paths
    return settings.video_dirs


def effective_auto_scan() -> bool:
    custom = load_custom_settings()
    value = custom.get("auto_scan")
    return bool(settings.auto_scan if value is None else value)


def effective_scan_interval_seconds() -> int:
    custom = load_custom_settings()
    value = custom.get("scan_interval_seconds")
    if value is None:
        return settings.scan_interval_seconds
    try:
        return max(30, int(value))
    except (TypeError, ValueError):
        return settings.scan_interval_seconds


def effective_auto_process_new_videos() -> bool:
    custom = load_custom_settings()
    value = custom.get("auto_process_new_videos")
    return bool(settings.auto_process_new_videos if value is None else value)


def effective_auto_process_max_per_round() -> int:
    custom = load_custom_settings()
    value = custom.get("auto_process_max_per_round")
    if value is None:
        return settings.auto_process_max_per_round
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return settings.auto_process_max_per_round


def effective_scan_recursive() -> bool:
    custom = load_custom_settings()
    value = custom.get("scan_recursive")
    return bool(settings.scan_recursive if value is None else value)
