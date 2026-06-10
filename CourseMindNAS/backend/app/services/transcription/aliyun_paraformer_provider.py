from __future__ import annotations

from pathlib import Path

from .aliyun_dashscope_provider import AliyunDashScopeTranscriptionProvider


class AliyunParaformerTranscriptionProvider:
    name = "aliyun_paraformer"

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        return AliyunDashScopeTranscriptionProvider().transcribe_chunk(audio_path, offset_seconds)
