from __future__ import annotations

from .aliyun_dashscope_provider import AliyunDashScopeTranscriptionProvider
from .aliyun_paraformer_provider import AliyunParaformerTranscriptionProvider
from .base import BaseTranscriptionProvider
from .funasr_provider import FunASRTranscriptionProvider
from .mock_provider import MockTranscriptionProvider
from .openai_provider import OpenAITranscriptionProvider
from .volc_doubao_provider import VolcDoubaoTranscriptionProvider


PROVIDERS: dict[str, type[BaseTranscriptionProvider]] = {
    "mock": MockTranscriptionProvider,
    "openai": OpenAITranscriptionProvider,
    "funasr": FunASRTranscriptionProvider,
    "local_funasr": FunASRTranscriptionProvider,
    "aliyun_dashscope": AliyunDashScopeTranscriptionProvider,
    "aliyun_paraformer": AliyunParaformerTranscriptionProvider,
    "volc_doubao": VolcDoubaoTranscriptionProvider,
}


def get_transcription_provider(name: str) -> BaseTranscriptionProvider:
    normalized_name = name.strip().lower()
    provider_cls = PROVIDERS.get(normalized_name)
    if provider_cls is None:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unsupported ASR_PROVIDER '{name}'. Supported providers: {supported}")
    return provider_cls()
