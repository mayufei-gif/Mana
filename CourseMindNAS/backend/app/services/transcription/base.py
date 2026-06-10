from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BaseTranscriptionProvider(Protocol):
    name: str

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        ...


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _segment_time_seconds(segment: dict, *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        value = _float_or_none(segment.get(key))
        if value is None:
            continue
        if _is_millisecond_time(segment, key, value):
            return value / 1000.0
        return value
    return default


def _is_millisecond_time(segment: dict, key: str, value: float) -> bool:
    if key in {"begin_time", "finish_time"}:
        return True
    if key == "end_time" and "begin_time" in segment:
        return True
    if key == "end_time" and "start_time" in segment and value > 1000:
        return True
    if key == "start_time" and "end_time" in segment and value > 1000:
        return True
    return key.endswith("_time") and value > 10000


def normalize_asr_segments(raw_segments: list[dict], *, offset_seconds: float = 0.0, id_start: int = 1) -> list[dict]:
    """Return the project-wide ASR segment shape and keep legacy aliases for downstream code."""
    normalized: list[dict] = []
    for raw in raw_segments:
        text = str(raw.get("text") or raw.get("sentence") or raw.get("transcript") or "").strip()
        if not text:
            continue
        start = _segment_time_seconds(raw, "start", "start_time", "begin_time", "begin", default=0.0)
        end = _segment_time_seconds(raw, "end", "end_time", "finish_time", "finish", default=None)
        start = max(0.0, float(start or 0.0))
        if end is None:
            end = start + max(2.0, min(8.0, len(text) / 6.0))
        end = max(start + 0.1, float(end))
        start += offset_seconds
        end += offset_seconds
        confidence = _float_or_none(raw.get("confidence") or raw.get("score"))
        segment_id = raw.get("id") or raw.get("sentence_id") or raw.get("segment_index") or (id_start + len(normalized))
        normalized.append({
            "id": int(segment_id) if str(segment_id).isdigit() else id_start + len(normalized),
            "start": start,
            "end": end,
            "text": text,
            "confidence": confidence,
            "start_time": start,
            "end_time": end,
        })
    return normalized
