from __future__ import annotations

from pathlib import Path

from .base import normalize_asr_segments


class MockTranscriptionProvider:
    name = "mock"

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        return normalize_asr_segments([{
            "id": 1,
            "start": 0.0,
            "end": 8.0,
            "text": f"待转录片段：{audio_path.name}。当前使用 mock provider，可先验证自动扫描、队列和播放器流程。",
            "confidence": 1.0,
        }], offset_seconds=offset_seconds)
