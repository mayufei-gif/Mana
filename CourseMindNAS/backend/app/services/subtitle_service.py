from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..config import settings
from ..utils.time_utils import format_srt_time, format_vtt_time


FILLER_PATTERNS = [
    (re.compile(r"(嗯|呃|额|啊)\1+"), r"\1"),
    (re.compile(r"(这个|那个)(\s+\1)+"), r"\1"),
]
SENTENCE_SPLIT_PATTERN = re.compile(r"[^。！？；]+[。！？；]?")
CLAUSE_SPLIT_PATTERN = re.compile(r"[^，]+，?")
SEMANTIC_MARKERS = ("那么", "首先", "第二个", "第三部分", "接下来", "我们来看")
DEFAULT_MAX_SUBTITLE_SECONDS = 12.0
DEFAULT_MAX_SUBTITLE_CHARS = 64
HARD_MAX_SUBTITLE_CHARS = 64
MOCK_PLACEHOLDER_MARKERS = (
    "待转录片段：chunk_",
    "当前使用 mock provider",
)


def _clean_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    for pattern, replacement in FILLER_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    normalized = normalized.replace(" ,", "，").replace(",", "，")
    normalized = normalized.replace(" .", "。").replace(".", "。")
    normalized = normalized.replace(" ?", "？").replace("?", "？")
    normalized = normalized.replace(" !", "！").replace("!", "！")
    normalized = _apply_corrections(normalized)
    if normalized and normalized[-1] not in "。！？；：":
        normalized = f"{normalized}。"
    return normalized


def normalize_segments(segments: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for idx, segment in enumerate(sorted(segments, key=lambda item: float(item.get("start_time", item.get("start", 0))))):
        raw_text = str(segment.get("text") or "").strip()
        text = str(segment.get("cleaned_text") or raw_text).strip()
        if not text:
            continue
        start = max(0.0, float(segment.get("start_time", segment.get("start", 0))))
        end = max(start + 0.1, float(segment.get("end_time", segment.get("end", start + 3))))
        confidence = segment.get("confidence")
        try:
            segment_id = int(segment.get("id") or idx + 1)
        except (TypeError, ValueError):
            segment_id = idx + 1
        normalized.append({
            "id": segment_id,
            "segment_index": idx,
            "start": start,
            "end": end,
            "start_time": start,
            "end_time": end,
            "text": raw_text or text,
            "cleaned_text": _clean_text(text),
            "confidence": confidence,
        })
    return normalized


def is_mock_placeholder_text(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return (
        any(marker in normalized for marker in MOCK_PLACEHOLDER_MARKERS)
        or normalized == "mp3。"
        or normalized == "mp3"
    )


def is_mock_placeholder_segments(segments: list[dict]) -> bool:
    if not segments:
        return False
    texts = [
        str(segment.get("cleaned_text") or segment.get("text") or "").strip()
        for segment in segments
    ]
    meaningful = [text for text in texts if text]
    return bool(meaningful) and all(is_mock_placeholder_text(text) for text in meaningful)


def write_transcript_json(segments: list[dict], output_path: Path, subtitle_segments: list[dict] | None = None, **metadata: object) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in metadata.items() if value is not None}
    payload.setdefault("subtitle_processing", subtitle_processing_info())
    payload["segments"] = segments
    if subtitle_segments is not None:
        payload["subtitle_segments"] = subtitle_segments
        payload["subtitle_statistics"] = subtitle_statistics(subtitle_segments)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def subtitle_processing_info() -> dict:
    domain_terms = _load_domain_terms()
    correction_terms = _load_correction_terms() if settings.subtitle_correction_enabled else {}
    return {
        "correction_enabled": settings.subtitle_correction_enabled,
        "correction_terms_count": len(correction_terms),
        "domain_terms_count": len(domain_terms),
        "config_dir": str(settings.config_dir),
    }


def to_srt(segments: list[dict]) -> str:
    blocks: list[str] = []
    for idx, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join([
                str(idx),
                f"{format_srt_time(segment['start_time'])} --> {format_srt_time(segment['end_time'])}",
                segment["cleaned_text"],
            ])
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: list[dict]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        blocks.append(f"{format_vtt_time(segment['start_time'])} --> {format_vtt_time(segment['end_time'])}")
        blocks.append(segment["cleaned_text"])
        blocks.append("")
    return "\n".join(blocks)


def write_subtitle_files(segments: list[dict], srt_path: Path, vtt_path: Path) -> tuple[Path, Path]:
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    vtt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(to_srt(segments), encoding="utf-8")
    vtt_path.write_text(to_vtt(segments), encoding="utf-8")
    return srt_path, vtt_path


def build_smart_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        return []
    smart_segments: list[dict] = []
    buffer: dict | None = None
    for segment in normalize_segments(segments):
        text = segment["cleaned_text"]
        if buffer is None:
            buffer = dict(segment)
            buffer["cleaned_text"] = text
            continue
        should_merge = len(buffer["cleaned_text"]) < 18 and len(text) < 26 and segment["start_time"] - buffer["end_time"] < 1.2
        if should_merge:
            buffer["end_time"] = segment["end_time"]
            buffer["text"] = f"{buffer['text'].rstrip('。')}，{segment['text'].lstrip('，。')}"
            buffer["cleaned_text"] = f"{buffer['cleaned_text'].rstrip('。')}，{text.lstrip('，。')}"
            continue
        smart_segments.append(buffer)
        buffer = dict(segment)
    if buffer:
        smart_segments.append(buffer)
    for idx, item in enumerate(smart_segments):
        item["segment_index"] = idx
    return smart_segments


def build_display_segments(
    segments: list[dict],
    *,
    video_duration: float | None = None,
    max_seconds: float = DEFAULT_MAX_SUBTITLE_SECONDS,
    max_chars: int = DEFAULT_MAX_SUBTITLE_CHARS,
) -> list[dict]:
    display_segments: list[dict] = []
    for source_index, segment in enumerate(normalize_segments(segments)):
        start = float(segment["start_time"])
        end = float(segment["end_time"])
        if video_duration:
            end = min(end, float(video_duration))
        if end <= start:
            continue
        text = segment["cleaned_text"]
        pieces = _split_for_display(text, duration=end - start, max_seconds=max_seconds, max_chars=max_chars)
        if not pieces:
            continue
        piece_times = _allocate_piece_times(start, end, pieces)
        for piece_index, (piece, (piece_start, piece_end)) in enumerate(zip(pieces, piece_times)):
            if display_segments and piece_start <= display_segments[-1]["end_time"]:
                piece_start = display_segments[-1]["end_time"] + 0.001
            if video_duration:
                piece_end = min(piece_end, float(video_duration))
            if piece_end <= piece_start:
                continue
            display_segments.append({
                "subtitle_index": len(display_segments),
                "segment_index": len(display_segments),
                "source_segment_index": int(segment.get("segment_index", source_index)),
                "source_piece_index": piece_index,
                "asr_segment_id": segment.get("id"),
                "start": piece_start,
                "end": piece_end,
                "start_time": piece_start,
                "end_time": piece_end,
                "text": piece,
                "cleaned_text": piece,
                "confidence": segment.get("confidence"),
            })
    return _merge_short_continuations(display_segments)


def subtitle_statistics(segments: list[dict]) -> dict:
    if not segments:
        return {"count": 0, "max_duration": 0, "max_chars": 0}
    durations = [max(0.0, float(item["end_time"]) - float(item["start_time"])) for item in segments]
    text_lengths = [len(str(item.get("cleaned_text") or item.get("text") or "")) for item in segments]
    return {
        "count": len(segments),
        "max_duration": round(max(durations), 3),
        "max_chars": max(text_lengths),
    }


def _split_for_display(text: str, *, duration: float, max_seconds: float, max_chars: int) -> list[str]:
    clean_text = text.strip()
    if not clean_text:
        return []
    sentences = _split_by_sentence_boundaries(clean_text)
    pieces: list[str] = []
    for sentence in sentences:
        if _can_keep_complete_sentence(sentence, duration=duration, max_seconds=max_seconds):
            pieces.append(sentence)
        else:
            pieces.extend(_split_by_natural_boundaries(sentence, max_chars))
    while pieces and any(len(piece) > HARD_MAX_SUBTITLE_CHARS for piece in pieces):
        next_pieces: list[str] = []
        changed = False
        for piece in pieces:
            if len(piece) <= HARD_MAX_SUBTITLE_CHARS:
                next_pieces.append(piece)
                continue
            split_at = _best_split_index(piece, max_chars)
            if split_at <= 0 or split_at >= len(piece):
                split_at = min(max_chars, len(piece))
            next_pieces.extend([piece[:split_at].strip(), piece[split_at:].strip()])
            changed = True
        pieces = [piece for piece in next_pieces if piece]
        if not changed:
            break
    return pieces


def _split_by_sentence_boundaries(text: str) -> list[str]:
    sentences = [match.group(0).strip() for match in SENTENCE_SPLIT_PATTERN.finditer(text) if match.group(0).strip()]
    return sentences or [text]


def _can_keep_complete_sentence(text: str, *, duration: float, max_seconds: float) -> bool:
    if len(text) <= HARD_MAX_SUBTITLE_CHARS:
        return True
    if text[-1:] in "。！？；" and duration <= max_seconds * 2:
        return True
    return False


def _split_by_natural_boundaries(text: str, target_chars: int) -> list[str]:
    clause_chunks = [match.group(0).strip() for match in CLAUSE_SPLIT_PATTERN.finditer(text) if match.group(0).strip()]
    chunks = clause_chunks or [text]
    pieces: list[str] = []
    buffer = ""
    for chunk in chunks:
        semantic_chunks = _split_by_semantic_markers(chunk)
        for semantic_chunk in semantic_chunks:
            candidate = f"{buffer}{semantic_chunk}" if buffer else semantic_chunk
            starts_new_thought = semantic_chunk.startswith(SEMANTIC_MARKERS) and len(buffer) >= 10
            if buffer and (starts_new_thought or len(candidate) > target_chars):
                pieces.append(_finalize_display_piece(buffer))
                buffer = semantic_chunk
            else:
                buffer = candidate
    if buffer:
        pieces.append(_finalize_display_piece(buffer))
    return pieces


def _split_by_semantic_markers(text: str) -> list[str]:
    chunks = [text]
    for marker in SEMANTIC_MARKERS:
        next_chunks: list[str] = []
        for chunk in chunks:
            if marker not in chunk or chunk.startswith(marker):
                next_chunks.append(chunk)
                continue
            parts = re.split(f"({re.escape(marker)})", chunk, maxsplit=1)
            if len(parts) == 3:
                head, matched_marker, tail = parts
                if head.strip():
                    next_chunks.append(head.strip())
                if f"{matched_marker}{tail}".strip():
                    next_chunks.append(f"{matched_marker}{tail}".strip())
            else:
                next_chunks.append(chunk)
        chunks = next_chunks
    return [chunk for chunk in chunks if chunk]


def _best_split_index(text: str, target_chars: int) -> int:
    search_limit = min(len(text), max(target_chars + 8, 1))
    for index in range(search_limit - 1, 0, -1):
        if text[index - 1] in "。！？；，":
            return index
    for marker in SEMANTIC_MARKERS:
        marker_index = text.find(marker, 1, search_limit)
        if marker_index > 0:
            return marker_index
    return min(target_chars, len(text))


def _allocate_piece_times(start: float, end: float, pieces: list[str]) -> list[tuple[float, float]]:
    duration = max(0.1, end - start)
    weights = [max(1, len(piece)) for piece in pieces]
    total_weight = sum(weights)
    times: list[tuple[float, float]] = []
    cursor = start
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            piece_end = end
        else:
            piece_end = start + duration * (sum(weights[: index + 1]) / total_weight)
        times.append((round(cursor, 3), round(max(cursor + 0.1, piece_end), 3)))
        cursor = piece_end
    return times


def _merge_short_continuations(segments: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for segment in segments:
        text = str(segment.get("cleaned_text") or segment.get("text") or "")
        if merged and _should_merge_with_previous(merged[-1], segment, text):
            previous = merged[-1]
            previous_text = str(previous.get("cleaned_text") or previous.get("text") or "").rstrip("。！？；，")
            merged_text = f"{previous_text}{text}"
            previous["text"] = merged_text
            previous["cleaned_text"] = merged_text
            previous["end"] = segment["end"]
            previous["end_time"] = segment["end_time"]
            continue
        merged.append(dict(segment))
    for index, item in enumerate(merged):
        item["subtitle_index"] = index
        item["segment_index"] = index
    return merged


def _should_merge_with_previous(previous: dict, current: dict, current_text: str) -> bool:
    gap = float(current["start_time"]) - float(previous["end_time"])
    if gap > 0.6:
        return False
    previous_text = str(previous.get("cleaned_text") or previous.get("text") or "")
    merged_len = len(previous_text.rstrip("。！？；，")) + len(current_text)
    if _looks_like_sentence_continuation(previous_text, current_text) and merged_len <= HARD_MAX_SUBTITLE_CHARS:
        return True
    if len(current_text) > 8:
        return False
    if current_text.startswith(("进行", "来", "给", "把", "对", "与", "和", "以及")):
        return True
    return previous_text.endswith(("来。", "给。", "和。", "与。", "把。", "对。"))


def _looks_like_sentence_continuation(previous_text: str, current_text: str) -> bool:
    previous_stem = previous_text.rstrip("。！？；，")
    if previous_stem.endswith(("给大家", "先给大家", "和大家来", "让大家", "给", "来", "和")):
        return current_text.startswith(("做", "进行", "介绍", "讲", "看", "学习", "分享", "首先", "了解"))
    return False


def _finalize_display_piece(text: str) -> str:
    piece = text.strip()
    if piece.endswith("，"):
        return f"{piece[:-1]}。"
    return piece


def _apply_corrections(text: str) -> str:
    if not settings.subtitle_correction_enabled:
        return text
    corrected = text
    for wrong, right in _load_correction_terms().items():
        if wrong:
            corrected = corrected.replace(wrong, right)
    return corrected


@lru_cache(maxsize=1)
def _load_correction_terms() -> dict[str, str]:
    path = settings.config_dir / "correction_terms.json"
    payload = _load_json_file(path, default={})
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(key)}


@lru_cache(maxsize=1)
def _load_domain_terms() -> list[str]:
    path = settings.config_dir / "domain_terms.json"
    payload = _load_json_file(path, default=[])
    if isinstance(payload, list):
        return [str(item) for item in payload if str(item).strip()]
    if isinstance(payload, dict):
        terms = payload.get("terms", [])
        if isinstance(terms, list):
            return [str(item) for item in terms if str(item).strip()]
    return []


def _load_json_file(path: Path, *, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
