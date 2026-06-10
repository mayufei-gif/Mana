from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .. import database
from ..config import settings
from ..utils.file_utils import content_signature_file, fingerprint_file, is_video_file, quick_hash_file


def _iter_video_paths(video_dir: Path, recursive: bool) -> list[Path]:
    exclude_dirs = settings.video_exclude_dirs

    def excluded(path: Path) -> bool:
        try:
            relative = path.relative_to(video_dir).as_posix().strip("/")
        except ValueError:
            return False
        if not relative:
            return False
        parts = [part.lower() for part in relative.split("/") if part]
        if any(part.startswith(".") for part in parts):
            return True
        normalized = relative.lower()
        return any(
            normalized == rule
            or normalized.startswith(f"{rule}/")
            or rule in parts
            for rule in exclude_dirs
        )

    if not recursive:
        return [path for path in video_dir.glob("*") if not excluded(path) and is_video_file(path, settings.video_extensions)]

    video_paths: list[Path] = []
    for current_dir, dirnames, filenames in os.walk(video_dir):
        current = Path(current_dir)
        dirnames[:] = [name for name in dirnames if not excluded(current / name)]
        for filename in filenames:
            path = current / filename
            if not excluded(path) and is_video_file(path, settings.video_extensions):
                video_paths.append(path)
    return video_paths


def _normalize_for_priority(path_text: str) -> str:
    return path_text.replace("\\", "/").rstrip("/").lower()


def _split_env_paths(raw: str) -> list[str]:
    return [chunk.strip() for chunk in raw.replace("\n", ";").split(";") if chunk.strip()]


def _preferred_source_roots() -> list[str]:
    roots = ["/videos_upload", "G:/E盘/NAS视频字幕"]
    for env_name in ("PREFERRED_VIDEO_ROOTS", "HOST_UPLOAD_VIDEO_ROOT"):
        roots.extend(_split_env_paths(os.getenv(env_name, "")))
    normalized_roots: list[str] = []
    for root in roots:
        normalized = _normalize_for_priority(root)
        if normalized not in normalized_roots:
            normalized_roots.append(normalized)
    return normalized_roots


def _source_priority(path: Path) -> int:
    normalized = _normalize_for_priority(path.resolve().as_posix())
    for root in _preferred_source_roots():
        if normalized == root or normalized.startswith(f"{root}/"):
            return 100
    if normalized == "/videos_upload" or normalized.startswith("/videos_upload/"):
        return 100
    return 0


def _video_row(path: Path, base_dir: Path, root_index: int) -> dict[str, Any]:
    stat = path.stat()
    relative_parent = path.parent.relative_to(base_dir) if path.parent != base_dir else Path(".")
    return {
        "title": path.stem,
        "file_path": str(path.resolve()),
        "file_hash": fingerprint_file(path),
        "quick_hash": quick_hash_file(path),
        "content_signature": content_signature_file(path),
        "file_size": stat.st_size,
        "folder": "." if str(relative_parent) == "." else relative_parent.as_posix(),
        "extension": path.suffix.lower(),
        "modified_time": float(stat.st_mtime),
        "root_index": root_index,
        "source_priority": _source_priority(path.resolve()),
    }


def _dedupe_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (str(row["extension"]), int(row["file_size"]), str(row["content_signature"]))


def _choose_preferred(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(rows, key=lambda row: (-int(row["source_priority"]), int(row["root_index"]), str(row["file_path"])))[0]


def _select_migration_candidate(conn, duplicate_paths: list[str]) -> dict[str, Any] | None:
    if not duplicate_paths:
        return None
    placeholders = ",".join("?" for _ in duplicate_paths)
    return conn.execute(
        f"""
        SELECT *
        FROM videos
        WHERE file_path IN ({placeholders})
        ORDER BY
            CASE WHEN status = 'ready' THEN 0 ELSE 1 END,
            CASE WHEN subtitle_status = 'ready' THEN 0 ELSE 1 END,
            updated_at DESC,
            id DESC
        LIMIT 1
        """,
        tuple(duplicate_paths),
    ).fetchone()


def _delete_duplicate_rows(conn, duplicate_paths: list[str]) -> int:
    if not duplicate_paths:
        return 0
    placeholders = ",".join("?" for _ in duplicate_paths)
    cursor = conn.execute(f"DELETE FROM videos WHERE file_path IN ({placeholders})", tuple(duplicate_paths))
    return int(cursor.rowcount or 0)


def _upsert_preferred_row(conn, row: dict[str, Any], duplicate_paths: list[str]) -> tuple[str, int]:
    existing = conn.execute(
        "SELECT id, file_path, file_hash, quick_hash, status FROM videos WHERE file_path = ?",
        (row["file_path"],),
    ).fetchone()
    migrated = False
    if not existing:
        existing = _select_migration_candidate(conn, duplicate_paths)
        migrated = bool(existing)

    if not existing:
        conn.execute(
            """
            INSERT INTO videos (
                title, file_path, file_hash, file_size, status, folder, extension,
                modified_time, quick_hash, subtitle_status, analysis_status, note_status,
                missing, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, 'none', 'none', 'none', 0, CURRENT_TIMESTAMP)
            """,
            (
                row["title"],
                row["file_path"],
                row["file_hash"],
                row["file_size"],
                row["folder"],
                row["extension"],
                row["modified_time"],
                row["quick_hash"],
            ),
        )
        return "inserted", 0

    duplicate_deleted = _delete_duplicate_rows(
        conn,
        [path for path in duplicate_paths if path != existing.get("file_path")],
    )
    content_changed = (not migrated) and existing["quick_hash"] != row["quick_hash"]
    metadata_changed = (
        migrated
        or existing.get("file_path") != row["file_path"]
        or existing["file_hash"] != row["file_hash"]
        or existing["quick_hash"] != row["quick_hash"]
    )
    if metadata_changed:
        conn.execute(
            """
            UPDATE videos
            SET title = ?, file_path = ?, file_hash = ?, file_size = ?, folder = ?, extension = ?,
                modified_time = ?, quick_hash = ?, missing = 0,
                status = CASE
                    WHEN subtitle_status = 'ready' AND analysis_status = 'ready' AND note_status = 'ready' THEN 'ready'
                    WHEN status = 'missing' THEN 'pending'
                    WHEN ? AND status IN ('ready', 'failed') THEN 'pending'
                    ELSE status
                END,
                subtitle_status = CASE WHEN ? AND subtitle_status = 'ready' THEN 'pending' ELSE subtitle_status END,
                analysis_status = CASE WHEN ? AND analysis_status = 'ready' THEN 'pending' ELSE analysis_status END,
                note_status = CASE WHEN ? AND note_status = 'ready' THEN 'pending' ELSE note_status END,
                error_stage = CASE WHEN ? THEN NULL ELSE error_stage END,
                error_message = CASE WHEN ? THEN NULL ELSE error_message END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                row["title"],
                row["file_path"],
                row["file_hash"],
                row["file_size"],
                row["folder"],
                row["extension"],
                row["modified_time"],
                row["quick_hash"],
                content_changed,
                content_changed,
                content_changed,
                content_changed,
                content_changed,
                content_changed,
                existing["id"],
            ),
        )
        return "updated", duplicate_deleted

    conn.execute(
        """
        UPDATE videos
        SET title = ?,
            folder = ?,
            extension = ?,
            modified_time = ?,
            file_size = ?,
            missing = 0,
            status = CASE
                WHEN subtitle_status = 'ready' AND analysis_status = 'ready' AND note_status = 'ready' THEN 'ready'
                WHEN status = 'missing' THEN 'pending'
                ELSE status
            END,
            error_stage = NULL,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (row["title"], row["folder"], row["extension"], row["modified_time"], row["file_size"], existing["id"]),
    )
    return "skipped", duplicate_deleted


def scan_video_dir(video_dir: Path, *, recursive: bool | None = None) -> dict:
    return scan_video_dirs([video_dir], recursive=recursive)


def scan_video_dirs(video_dirs: list[Path], *, recursive: bool | None = None) -> dict:
    if not video_dirs:
        raise FileNotFoundError("未配置视频目录")
    normalized_dirs = [Path(path).resolve() for path in video_dirs]
    for video_dir in normalized_dirs:
        if not video_dir.exists():
            raise FileNotFoundError(f"视频目录不存在: {video_dir}")
        if not video_dir.is_dir():
            raise NotADirectoryError(f"不是目录: {video_dir}")
    recursive = settings.scan_recursive if recursive is None else recursive

    candidates_by_key: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    scan_results: list[dict[str, Any]] = []
    for root_index, video_dir in enumerate(normalized_dirs):
        video_paths = _iter_video_paths(video_dir, recursive)
        for path in video_paths:
            row = _video_row(path, video_dir, root_index)
            candidates_by_key.setdefault(_dedupe_key(row), []).append(row)
        scan_results.append(
            {
                "video_dir": str(video_dir),
                "found": len(video_paths),
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "deduped": 0,
            }
        )

    found = sum(len(rows) for rows in candidates_by_key.values())
    inserted = 0
    updated = 0
    skipped = 0
    deduped = 0
    missing = 0
    duplicate_rows_deleted = 0
    live_paths: set[str] = set()
    ignored_duplicate_paths: set[str] = set()

    with database.get_conn() as conn:
        for rows in candidates_by_key.values():
            preferred = _choose_preferred(rows)
            duplicate_paths = [str(row["file_path"]) for row in rows if row["file_path"] != preferred["file_path"]]
            ignored_duplicate_paths.update(duplicate_paths)
            live_paths.add(str(preferred["file_path"]))
            action, deleted = _upsert_preferred_row(conn, preferred, duplicate_paths)
            duplicate_rows_deleted += deleted
            if action == "inserted":
                inserted += 1
                scan_results[int(preferred["root_index"])]["inserted"] += 1
            elif action == "updated":
                updated += 1
                scan_results[int(preferred["root_index"])]["updated"] += 1
            else:
                skipped += 1
                scan_results[int(preferred["root_index"])]["skipped"] += 1
            if duplicate_paths:
                deduped += len(duplicate_paths)
                for row in rows:
                    if row["file_path"] in duplicate_paths:
                        scan_results[int(row["root_index"])]["deduped"] += 1

        duplicate_rows_deleted += _delete_duplicate_rows(conn, list(ignored_duplicate_paths))

        stored_paths = conn.execute("SELECT id, file_path FROM videos").fetchall()
        for item in stored_paths:
            if item["file_path"] in live_paths:
                continue
            if Path(item["file_path"]).exists():
                continue
            conn.execute(
                """
                UPDATE videos
                SET missing = 1, status = 'missing', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (item["id"],),
            )
            missing += 1
        conn.execute(
            """
            INSERT INTO scan_logs (scan_dir, found_count, new_count, missing_count, error_message)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (";".join(str(path) for path in normalized_dirs), found, inserted, missing),
        )

    return {
        "video_dir": str(normalized_dirs[0]),
        "video_dirs": [str(path) for path in normalized_dirs],
        "found": found,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "deduped": deduped,
        "duplicate_rows_deleted": duplicate_rows_deleted,
        "missing": missing,
        "recursive": recursive,
        "preferred_duplicate_root": "/videos_upload",
        "scans": scan_results,
    }
