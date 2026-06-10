from __future__ import annotations

import re

from .subtitle_service import is_mock_placeholder_segments


TRANSITION_MARKERS = (
    "接下来",
    "下面",
    "然后",
    "再来看",
    "我们来看",
    "我们讲",
    "第二",
    "第三",
    "最后",
    "总结",
    "回顾",
)
EXAMPLE_MARKERS = ("例题", "例子", "案例", "做题", "题目", "来看题", "练习")
CONCEPT_MARKERS = ("定义", "概念", "公式", "方法", "规则", "原理", "知识点", "二级", "分类")
WARNING_MARKERS = ("注意", "易错", "陷阱", "重点", "必须", "不要")
MIN_CHAPTER_SECONDS = 180.0
MAX_CHAPTER_SECONDS = 720.0
TITLE_MAX_CHARS = 24


def generate_chapters(segments: list[dict], title: str) -> list[dict]:
    if not segments or is_mock_placeholder_segments(segments):
        return []

    ordered = sorted(segments, key=lambda item: float(item.get("start_time", 0)))
    boundaries = _chapter_boundaries(ordered)
    chapters: list[dict] = []
    for index, start_index in enumerate(boundaries):
        end_index = boundaries[index + 1] if index + 1 < len(boundaries) else len(ordered)
        chapter_segments = ordered[start_index:end_index]
        if not chapter_segments:
            continue
        start = float(chapter_segments[0]["start_time"])
        end = float(chapter_segments[-1]["end_time"])
        title_text = _chapter_title(chapter_segments, fallback=title)
        chapters.append({
            "title": title_text,
            "start_time": start,
            "end_time": end,
            "summary": _chapter_summary(chapter_segments),
            "importance": _chapter_importance(chapter_segments),
        })
    return _merge_tiny_chapters(chapters)


def _chapter_boundaries(segments: list[dict]) -> list[int]:
    boundaries = [0]
    last_boundary_time = float(segments[0]["start_time"])
    for index, segment in enumerate(segments[1:], start=1):
        start = float(segment["start_time"])
        elapsed = start - last_boundary_time
        text = _text(segment)
        if elapsed < MIN_CHAPTER_SECONDS:
            continue
        if elapsed >= MAX_CHAPTER_SECONDS or _looks_like_new_section(text):
            boundaries.append(index)
            last_boundary_time = start
    return boundaries


def _looks_like_new_section(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    return any(marker in compact for marker in TRANSITION_MARKERS + EXAMPLE_MARKERS)


def _chapter_title(segments: list[dict], *, fallback: str) -> str:
    joined = " ".join(_text(segment) for segment in segments[:8])
    topic = _extract_topic(joined) or _extract_topic(_text(segments[0])) or fallback or "课程片段"
    prefix = _chapter_prefix(joined)
    return f"{prefix}：{topic}" if prefix else topic


def _chapter_prefix(text: str) -> str:
    if any(marker in text for marker in EXAMPLE_MARKERS):
        return "例题/做题"
    if any(marker in text for marker in WARNING_MARKERS):
        return "重点提醒"
    if any(marker in text for marker in ("总结", "回顾")):
        return "总结回顾"
    if any(marker in text for marker in CONCEPT_MARKERS):
        return "知识点"
    return "课程讲解"


def _extract_topic(text: str) -> str:
    clean = re.sub(r"\s+", "", text)
    clean = re.sub(r"^(那么|然后|接下来|下面|我们来看|我们讲|首先|第二|第三|最后)", "", clean)
    sentences = re.split(r"[。！？；]", clean)
    candidates = [item.strip("，,：: ") for item in sentences if item.strip("，,：: ")]
    if not candidates:
        return ""
    best = max(candidates[:4], key=lambda item: _topic_score(item))
    return _trim_title(best)


def _topic_score(text: str) -> int:
    score = min(len(text), TITLE_MAX_CHARS)
    for marker in CONCEPT_MARKERS + EXAMPLE_MARKERS + WARNING_MARKERS:
        if marker in text:
            score += 12
    return score


def _trim_title(text: str) -> str:
    compact = text.strip("，,：:。 ")
    if len(compact) <= TITLE_MAX_CHARS:
        return compact
    return f"{compact[:TITLE_MAX_CHARS]}..."


def _chapter_summary(segments: list[dict]) -> str:
    texts = [_text(segment) for segment in segments if _text(segment)]
    if not texts:
        return "本段暂无可提取摘要。"
    summary = " ".join(texts[:3])
    return _trim_summary(summary)


def _trim_summary(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= 90:
        return compact
    return f"{compact[:90]}..."


def _chapter_importance(segments: list[dict]) -> int:
    text = " ".join(_text(segment) for segment in segments)
    if any(marker in text for marker in WARNING_MARKERS + EXAMPLE_MARKERS):
        return 4
    if any(marker in text for marker in CONCEPT_MARKERS):
        return 3
    return 2


def _merge_tiny_chapters(chapters: list[dict]) -> list[dict]:
    if len(chapters) <= 1:
        return chapters
    merged: list[dict] = []
    for chapter in chapters:
        duration = float(chapter["end_time"]) - float(chapter["start_time"])
        if merged and duration < MIN_CHAPTER_SECONDS / 2:
            previous = merged[-1]
            previous["end_time"] = chapter["end_time"]
            previous["summary"] = _trim_summary(f"{previous['summary']} {chapter['summary']}")
            previous["importance"] = max(int(previous["importance"]), int(chapter["importance"]))
            continue
        merged.append(chapter)
    return merged


def _text(segment: dict) -> str:
    return str(segment.get("cleaned_text") or segment.get("text") or "").strip()
