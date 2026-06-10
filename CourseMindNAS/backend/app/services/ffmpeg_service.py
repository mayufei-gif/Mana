from __future__ import annotations

import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip() or proc.stdout.strip() or "FFmpeg command failed")
    return proc


def probe_duration(video_path: Path) -> float:
    proc = _run([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ])
    payload = json.loads(proc.stdout)
    return float(payload.get("format", {}).get("duration") or 0)


def extract_audio(video_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ])
    return output_path


def split_audio(audio_path: Path, output_dir: Path, chunk_seconds: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in [*output_dir.glob("chunk_*.mp3"), *output_dir.glob("chunk_*.dashscope.wav"), *output_dir.glob("chunk_*.probe.wav")]:
        stale.unlink(missing_ok=True)
    pattern = output_dir / "chunk_%03d.mp3"
    _run([
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        str(pattern),
    ])
    return sorted(output_dir.glob("chunk_*.mp3"))
