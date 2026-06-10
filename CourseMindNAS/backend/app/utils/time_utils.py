from __future__ import annotations


def clamp_seconds(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, float(value))


def format_clock(seconds: float | int | None) -> str:
    total = int(clamp_seconds(seconds))
    hour = total // 3600
    minute = (total % 3600) // 60
    second = total % 60
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def format_srt_time(seconds: float | int | None) -> str:
    value = clamp_seconds(seconds)
    hour = int(value // 3600)
    minute = int((value % 3600) // 60)
    second = int(value % 60)
    millis = int(round((value - int(value)) * 1000))
    return f"{hour:02d}:{minute:02d}:{second:02d},{millis:03d}"


def format_vtt_time(seconds: float | int | None) -> str:
    return format_srt_time(seconds).replace(",", ".")
