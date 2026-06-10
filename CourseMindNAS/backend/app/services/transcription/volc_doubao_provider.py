from __future__ import annotations

from pathlib import Path


class VolcDoubaoTranscriptionProvider:
    name = "volc_doubao"

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        raise NotImplementedError(
            "volc_doubao adapter 已预留。后续可在这里接入火山引擎/豆包语音识别官方 SDK 或 HTTP 接口。"
        )
