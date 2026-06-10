from __future__ import annotations

from pathlib import Path

from ...config import settings
from .http_openai_compatible import transcribe_via_openai_compatible


class FunASRTranscriptionProvider:
    name = "funasr"

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        return transcribe_via_openai_compatible(
            audio_path=audio_path,
            offset_seconds=offset_seconds,
            base_url=settings.transcription_base_url,
            model=settings.transcription_model or "funasr",
            api_key=settings.transcription_api_key,
        )
