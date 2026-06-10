from __future__ import annotations

from .subtitle_service import is_mock_placeholder_segments


KEYWORDS = {
    "重点": "exam",
    "注意": "warning",
    "总结": "summary",
    "定义": "definition",
    "公式": "formula",
    "例题": "example",
    "方法": "method",
    "易错": "mistake",
}


def extract_highlights(segments: list[dict]) -> list[dict]:
    if not segments or is_mock_placeholder_segments(segments):
        return []
    highlights: list[dict] = []
    for segment in segments:
        text = segment.get("cleaned_text") or segment.get("text") or ""
        matched = next(((word, kind) for word, kind in KEYWORDS.items() if word in text), None)
        if not matched:
            continue
        word, kind = matched
        highlights.append({
            "type": kind,
            "title": f"{word}相关内容",
            "content": text[:180],
            "start_time": float(segment["start_time"]),
            "end_time": float(segment["end_time"]),
            "importance": 4 if kind in {"exam", "mistake", "formula"} else 3,
        })
    return highlights[:20]
