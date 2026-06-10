from __future__ import annotations

from pathlib import Path

import httpx

from .base import normalize_asr_segments


def transcribe_via_openai_compatible(
    *,
    audio_path: Path,
    offset_seconds: float,
    base_url: str,
    model: str,
    api_key: str = "",
    timeout: int = 180,
) -> list[dict]:
    url = f"{base_url.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    with audio_path.open("rb") as file_obj:
        files = {"file": (audio_path.name, file_obj, "audio/mpeg")}
        data = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        response = httpx.post(url, headers=headers, files=files, data=data, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    raw_segments = payload.get("segments") or []
    if not raw_segments and payload.get("text"):
        raw_segments = [{"start": 0, "end": 8, "text": payload["text"]}]
    return normalize_asr_segments(raw_segments, offset_seconds=offset_seconds)
