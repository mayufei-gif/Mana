from __future__ import annotations

import json
import subprocess
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any

from ...config import settings
from .base import normalize_asr_segments

try:
    from dashscope.audio.asr import RecognitionCallback as _RecognitionCallbackBase
except ImportError:
    class _RecognitionCallbackBase:
        pass


SENTENCE_CONTAINER_KEYS = (
    "output",
    "data",
    "payload",
    "result",
    "sentences",
    "sentence",
    "segments",
    "results",
    "transcripts",
)
TEXT_KEYS = ("text", "sentence", "transcript", "transcription", "final_sentence", "begin_text")
NON_REALTIME_MODEL_HINTS = {"fun-asr", "paraformer-v2"}


class AliyunDashScopeTranscriptionProvider:
    name = "aliyun_dashscope"

    def transcribe_chunk(self, audio_path: Path, offset_seconds: float) -> list[dict]:
        api_key = settings.dashscope_api_key or settings.transcription_api_key
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY missing. 请在 .env 中配置 DASHSCOPE_API_KEY 或 TRANSCRIPTION_API_KEY。")
        try:
            import dashscope
            from dashscope.audio.asr import Recognition
        except ImportError as exc:
            raise RuntimeError("dashscope SDK missing. 请安装 backend/requirements.txt 中的 dashscope 依赖。") from exc

        dashscope.api_key = api_key
        if settings.dashscope_websocket_url:
            dashscope.base_websocket_api_url = settings.dashscope_websocket_url
        model = settings.transcription_model or "fun-asr-realtime"
        if model.strip().lower() in NON_REALTIME_MODEL_HINTS:
            raise RuntimeError(
                f"ASR_MODEL={model} 是非实时批量模型；当前 DashScope adapter 使用 WebSocket Recognition 本地文件调用，"
                "请先使用 fun-asr-realtime 或 paraformer-realtime-v2。fun-asr/paraformer-v2 批量版需要后续单独接入。"
            )
        dashscope_audio = _prepare_dashscope_audio(audio_path, settings.asr_sample_rate)
        kwargs: dict[str, Any] = {
            "model": model,
            "format": dashscope_audio.suffix.lower().lstrip(".") or "wav",
            "sample_rate": settings.asr_sample_rate,
        }
        call_kwargs: dict[str, Any] = {}
        if settings.asr_phrase_id:
            call_kwargs["phrase_id"] = settings.asr_phrase_id
        duration = _probe_audio_duration(dashscope_audio)
        if duration is not None and duration < 0.5:
            return []
        sentences, result, callback = _stream_dashscope_file(
            Recognition,
            dashscope_audio,
            kwargs,
            call_kwargs,
            audio_path,
        )
        if not sentences and model.strip().lower() != "paraformer-realtime-v2":
            fallback_kwargs = {**kwargs, "model": "paraformer-realtime-v2"}
            fallback_sentences, fallback_result, fallback_callback = _stream_dashscope_file(
                Recognition,
                dashscope_audio,
                fallback_kwargs,
                call_kwargs,
                audio_path,
            )
            if fallback_sentences:
                sentences, result, callback = fallback_sentences, fallback_result, fallback_callback
            else:
                result = {
                    "primary_result": result,
                    "primary_callback": callback.debug_payload(),
                    "fallback_model": "paraformer-realtime-v2",
                    "fallback_result": fallback_result,
                    "fallback_callback": fallback_callback.debug_payload(),
                }
                callback = fallback_callback
        segments = normalize_asr_segments(sentences, offset_seconds=offset_seconds)
        if not segments:
            _write_debug_payload(
                audio_path,
                {
                    "sentences": sentences,
                    "dashscope_audio": str(dashscope_audio),
                    "raw_result": result,
                    "callback": callback.debug_payload(),
                },
            )
            # A long course can contain silent chunks, intro gaps, or music-only spans.
            # Keep the whole video job alive; the worker rejects the video later only
            # if every chunk produces no usable subtitle text.
            return []
        return segments


class _CollectingRecognitionCallback(_RecognitionCallbackBase):
    def __init__(self) -> None:
        self.sentences: list[dict] = []
        self.events: list[Any] = []
        self.completed = threading.Event()
        self.error_payload: Any = None
        self.error_message = ""

    def on_complete(self) -> None:
        self.completed.set()

    def on_error(self, result: Any) -> None:
        self.error_payload = _safe_jsonable(result)
        self.error_message = getattr(result, "message", "") or str(result)
        self.completed.set()

    def on_close(self) -> None:
        self.completed.set()

    def on_event(self, result: Any) -> None:
        if len(self.events) < 20:
            self.events.append(_safe_jsonable(result))
        try:
            self.sentences.extend(_extract_sentences(result))
        except RuntimeError:
            return
        except Exception as exc:
            self.error_payload = _safe_jsonable({"exception": repr(exc), "result": result})
            self.error_message = repr(exc)
            self.completed.set()

    def debug_payload(self) -> dict[str, Any]:
        return {
            "completed": self.completed.is_set(),
            "sentence_count": len(self.sentences),
            "sentences": self.sentences[:20],
            "event_count": len(self.events),
            "events": self.events[:20],
            "error_payload": self.error_payload,
            "error_message": self.error_message,
        }


def _extract_sentences(result: Any) -> list[dict]:
    get_sentence = _safe_getattr(result, "get_sentence")
    if callable(get_sentence):
        try:
            sentence = get_sentence()
        except (KeyError, TypeError, AttributeError, ValueError):
            sentence = None
        if sentence is not None:
            sentences = _collect_sentence_dicts(sentence)
            if sentences:
                return sentences

    payload = _to_dict(result) if isinstance(result, dict) else _to_dict(_safe_getattr(result, "output"))
    sentences = _collect_sentence_dicts(payload)
    if sentences:
        return sentences
    if isinstance(payload, dict):
        for key in SENTENCE_CONTAINER_KEYS:
            value = payload.get(key)
            sentences = _collect_sentence_dicts(value)
            if sentences:
                return sentences
        sentence = _single_text_segment(payload)
        if sentence:
            return [sentence]

    text = _safe_getattr(result, "text")
    if text:
        return [{"start": 0.0, "end": 8.0, "text": str(text)}]
    return []


def _collect_sentence_dicts(value: Any) -> list[dict]:
    if isinstance(value, dict):
        sentence = _single_text_segment(value)
        if sentence:
            return [sentence]
        nested = []
        for key in SENTENCE_CONTAINER_KEYS:
            nested.extend(_collect_sentence_dicts(value.get(key)))
        if nested:
            return nested
        return []
    if isinstance(value, list):
        sentences: list[dict] = []
        for item in value:
            sentences.extend(_collect_sentence_dicts(_to_dict(item)))
        return sentences
    return []


def _single_text_segment(payload: dict[str, Any]) -> dict[str, Any] | None:
    text = ""
    for key in TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, (dict, list, tuple, set)):
            continue
        if value:
            text = str(value).strip()
            break
    if not text:
        return None
    segment = {**payload, "text": text}
    if "start" not in segment and "start_time" not in segment and "begin_time" not in segment and "begin" not in segment:
        segment["start"] = 0.0
    if "end" not in segment and "end_time" not in segment and "finish_time" not in segment and "finish" not in segment:
        segment["end"] = payload.get("stop_time")
    return segment


def _dedupe_sentences(sentences: list[dict]) -> list[dict]:
    deduped_by_key: dict[tuple[str, Any], dict] = {}
    order: list[tuple[str, Any]] = []
    for sentence in sentences:
        text = str(sentence.get("text") or sentence.get("sentence") or sentence.get("transcript") or "").strip()
        if not text:
            continue
        sentence_id = sentence.get("sentence_id") or sentence.get("id")
        start = sentence.get("begin_time") or sentence.get("start_time") or sentence.get("start") or sentence.get("begin")
        if sentence_id is not None:
            key = ("sentence_id", sentence_id)
        elif start is not None:
            key = ("start", start)
        else:
            key = ("text", text)
        current = {**sentence, "text": text}
        previous = deduped_by_key.get(key)
        if previous is None:
            order.append(key)
            deduped_by_key[key] = current
            continue
        if _is_better_sentence(current, previous):
            deduped_by_key[key] = current
    return [deduped_by_key[key] for key in order]


def _is_better_sentence(current: dict, previous: dict) -> bool:
    if current.get("sentence_end") is True and previous.get("sentence_end") is not True:
        return True
    if previous.get("sentence_end") is True and current.get("sentence_end") is not True:
        return False
    current_text = str(current.get("text") or "")
    previous_text = str(previous.get("text") or "")
    if len(current_text) != len(previous_text):
        return len(current_text) > len(previous_text)
    current_end = _time_sort_value(current.get("end_time") or current.get("finish_time") or current.get("end"))
    previous_end = _time_sort_value(previous.get("end_time") or previous.get("finish_time") or previous.get("end"))
    return current_end >= previous_end


def _time_sort_value(value: Any) -> float:
    try:
        if value is None or value == "":
            return -1.0
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _call_dashscope_file(
    recognition_cls: Any,
    dashscope_audio: Path,
    recognition_kwargs: dict[str, Any],
    call_kwargs: dict[str, Any],
    original_audio_path: Path,
) -> tuple[list[dict], Any, _CollectingRecognitionCallback]:
    callback = _CollectingRecognitionCallback()
    try:
        recognition = recognition_cls(callback=callback, **recognition_kwargs)
        result = recognition.call(str(dashscope_audio), **call_kwargs)
    except Exception as exc:
        _write_debug_payload(
            original_audio_path,
            {
                "exception": repr(exc),
                "dashscope_audio": str(dashscope_audio),
                "recognition_kwargs": recognition_kwargs,
                "callback": callback.debug_payload(),
            },
        )
        raise
    if callback.error_payload:
        _write_debug_payload(
            original_audio_path,
            {
                "dashscope_audio": str(dashscope_audio),
                "recognition_kwargs": recognition_kwargs,
                "result": result,
                "callback": callback.debug_payload(),
            },
        )
        raise RuntimeError(f"DashScope ASR callback failed: {callback.error_message}")
    callback.completed.wait(timeout=10)
    status_code = _safe_getattr(result, "status_code")
    if status_code not in (None, HTTPStatus.OK, int(HTTPStatus.OK)):
        _write_debug_payload(
            original_audio_path,
            {
                "dashscope_audio": str(dashscope_audio),
                "recognition_kwargs": recognition_kwargs,
                "result": result,
                "callback": callback.debug_payload(),
            },
        )
        message = _safe_getattr(result, "message") or _safe_getattr(result, "code") or "unknown error"
        raise RuntimeError(f"DashScope ASR failed: status_code={status_code} message={message}")
    sentences = _dedupe_sentences([*_extract_sentences(result), *callback.sentences])
    return sentences, result, callback


def _stream_dashscope_file(
    recognition_cls: Any,
    dashscope_audio: Path,
    recognition_kwargs: dict[str, Any],
    call_kwargs: dict[str, Any],
    original_audio_path: Path,
) -> tuple[list[dict], Any, _CollectingRecognitionCallback]:
    callback = _CollectingRecognitionCallback()
    result: Any = None
    try:
        recognition = recognition_cls(callback=callback, **recognition_kwargs)
        result = recognition.start(**call_kwargs)
        with dashscope_audio.open("rb") as file_obj:
            header = file_obj.read(44)
            if not header.startswith(b"RIFF"):
                file_obj.seek(0)
            frame_bytes = max(1, int(_safe_int(recognition_kwargs.get("sample_rate"), 16000) * 2 * 0.1))
            while True:
                frame = file_obj.read(frame_bytes)
                if not frame:
                    break
                recognition.send_audio_frame(frame)
                time.sleep(0.1)
        stop_result = recognition.stop()
        callback.completed.wait(timeout=10)
        result = stop_result if stop_result is not None else result
    except Exception as exc:
        _write_debug_payload(
            original_audio_path,
            {
                "exception": repr(exc),
                "dashscope_audio": str(dashscope_audio),
                "recognition_kwargs": recognition_kwargs,
                "callback": callback.debug_payload(),
            },
        )
        raise
    if callback.error_payload:
        _write_debug_payload(
            original_audio_path,
            {
                "dashscope_audio": str(dashscope_audio),
                "recognition_kwargs": recognition_kwargs,
                "result": result,
                "callback": callback.debug_payload(),
            },
        )
        raise RuntimeError(f"DashScope ASR callback failed: {callback.error_message}")
    sentences = _dedupe_sentences([*_extract_sentences(result), *callback.sentences])
    return sentences, result, callback


def _prepare_dashscope_audio(audio_path: Path, sample_rate: int) -> Path:
    """DashScope realtime SDK documents wav/pcm/aac/amr/opus/speex, so normalize mp3 chunks to wav."""
    supported_direct = {".wav", ".pcm", ".aac", ".amr", ".opus", ".speex"}
    if audio_path.suffix.lower() in supported_direct:
        return audio_path
    output_path = audio_path.with_suffix(".dashscope.wav")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        str(output_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "ffmpeg failed to prepare DashScope audio")
    return output_path


def _probe_audio_duration(audio_path: Path) -> float | None:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_dict(value: Any) -> Any:
    if isinstance(value, dict) or value is None:
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except (KeyError, TypeError, AttributeError, ValueError):
        return default


def _safe_jsonable(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return repr(value)[:300]
    value = _to_dict(value)
    if isinstance(value, dict):
        return {str(key): _safe_jsonable(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_jsonable(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)[:300]


def _write_debug_payload(audio_path: Path, result: Any) -> None:
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        debug_path = settings.log_dir / f"dashscope_asr_debug_{audio_path.stem}.json"
        payload = {
            "audio_path": str(audio_path),
            "model": settings.transcription_model,
            "result_type": type(result).__name__,
            "status_code": _safe_getattr(result, "status_code"),
            "message": _safe_getattr(result, "message"),
            "output": _safe_jsonable(_safe_getattr(result, "output")),
            "result": _safe_jsonable(result),
        }
        debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return
