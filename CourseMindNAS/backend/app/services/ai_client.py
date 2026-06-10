from __future__ import annotations

from pathlib import Path

from ..config import settings
from .transcription import get_transcription_provider


class AIClient:
    def transcribe_audio(self, audio_path: Path, offset_seconds: float = 0.0) -> list[dict]:
        provider = get_transcription_provider(settings.transcription_provider)
        return provider.transcribe_chunk(audio_path, offset_seconds)


ai_client = AIClient()
