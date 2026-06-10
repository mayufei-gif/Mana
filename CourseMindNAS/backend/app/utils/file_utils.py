from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import settings


def is_video_file(path: Path, allowed_extensions: tuple[str, ...] | None = None) -> bool:
    extensions = allowed_extensions or settings.video_extensions
    return path.is_file() and path.suffix.lower() in set(extensions)


def fingerprint_file(path: Path) -> str:
    stat = path.stat()
    seed = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def quick_hash_file(path: Path, sample_size: int = 1024 * 256) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).encode("utf-8"))
    digest.update(str(stat.st_size).encode("utf-8"))
    with path.open("rb") as file_obj:
        head = file_obj.read(sample_size)
        digest.update(head)
        if stat.st_size > sample_size:
            file_obj.seek(max(0, stat.st_size - sample_size))
            digest.update(file_obj.read(sample_size))
    return digest.hexdigest()


def content_signature_file(path: Path, sample_size: int = 1024 * 256) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("utf-8"))
    with path.open("rb") as file_obj:
        digest.update(file_obj.read(sample_size))
        if stat.st_size > sample_size:
            file_obj.seek(max(0, stat.st_size - sample_size))
            digest.update(file_obj.read(sample_size))
    return digest.hexdigest()


def ensure_child_path(base: Path, child: Path) -> Path:
    resolved_base = base.resolve()
    resolved_child = child.resolve()
    if resolved_base not in resolved_child.parents and resolved_child != resolved_base:
        raise ValueError(f"Path is outside allowed base: {resolved_child}")
    return resolved_child
