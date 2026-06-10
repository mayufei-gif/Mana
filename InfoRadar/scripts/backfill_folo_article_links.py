#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
LINK_DIR = ROOT / "data" / "raw" / "folo_article_links"
LINK_JSONL = LINK_DIR / "folo_article_links.jsonl"
CURSOR_STATE_JSON = LINK_DIR / "backfill_cursor_state.json"
REPORT_DIR = ROOT / "reports"
FOLO_APP_URL = "https://app.folo.is/timeline/articles"
DEFAULT_VIEWS = ["articles", "social", "pictures", "videos", "audio", "notifications"]
VIEW_NUMBERS = {
    "articles": 0,
    "social": 1,
    "pictures": 2,
    "videos": 3,
    "audio": 4,
    "notifications": 5,
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def folo_article_url(feed_id: str, entry_id: str) -> str:
    if not feed_id or not entry_id:
        return ""
    return f"{FOLO_APP_URL}/{quote_plus(feed_id)}/{quote_plus(entry_id)}"


def load_existing(path: Path) -> tuple[dict[str, dict], list[dict]]:
    by_key: dict[str, dict] = {}
    rows: list[dict] = []
    if not path.exists():
        return by_key, rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        feed_id = str(item.get("feedId") or item.get("feed_id") or "").strip()
        entry_id = str(item.get("entryId") or item.get("entry_id") or "").strip()
        if not feed_id or not entry_id:
            continue
        item["feedId"] = feed_id
        item["entryId"] = entry_id
        item["folo_article_url"] = str(item.get("folo_article_url") or folo_article_url(feed_id, entry_id))
        key = f"{feed_id}|{entry_id}"
        by_key[key] = item
    rows = list(by_key.values())
    rows.sort(key=lambda row: str(row.get("published_at") or row.get("created_at") or ""), reverse=True)
    return by_key, rows


def npx_binary() -> str | None:
    npx_bin = shutil.which("npx.cmd") if os.name == "nt" else None
    return npx_bin or shutil.which("npx")


def run_json_command(cmd: list[str], timeout: int) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"command exited {proc.returncode}",
            "stdout_tail": stdout[-1000:],
            "stderr_tail": stderr[-1000:],
        }
    try:
        return json.loads(stdout)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"invalid json: {exc}",
            "stdout_tail": stdout[-1000:],
            "stderr_tail": stderr[-1000:],
        }


def run_folo_timeline(
    view: str,
    limit: int,
    cursor: str | None,
    timeout: int,
    *,
    category: str = "",
    feed_id: str = "",
    list_id: str = "",
) -> dict:
    npx_bin = npx_binary()
    if not npx_bin:
        return {"ok": False, "error": "npx was not found in PATH"}
    cmd = [
        npx_bin,
        "--yes",
        "folocli@latest",
        "timeline",
        "--view",
        view,
        "--limit",
        str(limit),
        "--format",
        "json",
    ]
    if cursor:
        cmd.extend(["--cursor", cursor])
    if category:
        cmd.extend(["--category", category])
    if feed_id:
        cmd.extend(["--feed", feed_id])
    if list_id:
        cmd.extend(["--list", list_id])
    payload = run_json_command(cmd, timeout)
    if not payload.get("ok"):
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        return {
            "ok": False,
            "error": error.get("message") or payload.get("error") or "folocli returned ok=false",
            "code": error.get("code", ""),
        }
    return payload


def clean_text(value: object, max_len: int = 600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def load_subscription_targets(timeout: int) -> list[dict]:
    npx_bin = npx_binary()
    if not npx_bin:
        return []
    payload = run_json_command(
        [npx_bin, "--yes", "folocli@latest", "subscription", "list", "--format", "json"],
        timeout,
    )
    if not payload.get("ok"):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    subscriptions = data.get("subscriptions") if isinstance(data.get("subscriptions"), list) else []
    targets: list[dict] = []
    seen: set[str] = set()
    seen_categories: set[str] = set()
    for item in subscriptions:
        if not isinstance(item, dict):
            continue
        view = item.get("view")
        category = clean_text(item.get("category"), 200)
        feed_id = clean_text(item.get("feedId"), 120)
        list_id = clean_text(item.get("listId"), 120)
        feed = item.get("feeds") if isinstance(item.get("feeds"), dict) else {}
        list_obj = item.get("lists") if isinstance(item.get("lists"), dict) else {}
        title = clean_text(item.get("title") or feed.get("title") or list_obj.get("title"), 300)
        if category:
            category_key = f"{view}|category|{category}"
            if category_key in seen_categories:
                continue
            seen_categories.add(category_key)
            key = category_key
            target = {"view": view, "category": category, "feedId": "", "listId": "", "title": category, "target_type": "category"}
        else:
            target_type = "list" if list_id and list_id == feed_id else "feed"
            key = f"{view}|{target_type}|{feed_id}|{list_id}"
            target = {
                "view": view,
                "category": "",
                "feedId": "" if target_type == "list" else feed_id,
                "listId": list_id if target_type == "list" else "",
                "title": title,
                "target_type": target_type,
            }
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
    return targets


def convert_row(item: dict, view: str) -> dict | None:
    entry = item.get("entries") if isinstance(item.get("entries"), dict) else {}
    feed = item.get("feeds") if isinstance(item.get("feeds"), dict) else {}
    subscription = item.get("subscriptions") if isinstance(item.get("subscriptions"), dict) else {}
    feed_id = clean_text(feed.get("id"), 120)
    entry_id = clean_text(entry.get("id"), 120)
    if not feed_id or not entry_id:
        return None
    title = clean_text(entry.get("title") or entry.get("description") or entry.get("summary"), 800)
    source = clean_text(feed.get("title") or entry.get("author") or subscription.get("title"), 300)
    original_url = clean_text(entry.get("url") or entry.get("guid") or "", 1000)
    published_at = clean_text(entry.get("publishedAt") or entry.get("insertedAt") or "", 80)
    return {
        "title": title,
        "source": source,
        "original_url": original_url,
        "feedId": feed_id,
        "entryId": entry_id,
        "folo_article_url": folo_article_url(feed_id, entry_id),
        "published_at": published_at,
        "folo_view": view,
        "folo_category": clean_text(subscription.get("category"), 200),
        "summary": clean_text(entry.get("summary") or entry.get("description") or "", 1000),
        "created_at": now_iso(),
        "backfill_source": "folocli timeline",
    }


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    last_error: Exception | None = None
    for _ in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error or PermissionError(str(path))


def append_jsonl_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def seed_cursor_state_from_reports(state_path: Path) -> dict:
    state: dict[str, dict] = {}
    for report_path in sorted(REPORT_DIR.glob("folo_article_links_backfill_*.json")):
        report = read_json(report_path, {})
        views = report.get("views") if isinstance(report.get("views"), dict) else {}
        for key, item in views.items():
            if not isinstance(item, dict):
                continue
            if item.get("has_next") and item.get("last_cursor"):
                state[key] = {
                    "cursor": str(item.get("last_cursor") or ""),
                    "exhausted": False,
                    "updated_at": str(report.get("generated_at") or ""),
                }
            elif item.get("pages", 0) > 0 and not item.get("has_next"):
                state[key] = {
                    "cursor": "",
                    "exhausted": True,
                    "updated_at": str(report.get("generated_at") or ""),
                }
    if state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill InfoRadar Folo article links from Folo timeline.")
    parser.add_argument("--views", nargs="+", default=DEFAULT_VIEWS, help="Folo views to fetch.")
    parser.add_argument("--limit", type=int, default=20, help="Entries per page.")
    parser.add_argument("--max-pages", type=int, default=2, help="Maximum pages per view.")
    parser.add_argument("--timeout", type=int, default=60, help="folocli timeout seconds per page.")
    parser.add_argument("--split-subscriptions", action="store_true", help="Fetch matching views by subscription category/feed/list.")
    parser.add_argument("--max-targets", type=int, default=0, help="Maximum subscription targets to fetch, 0 means no limit.")
    parser.add_argument("--resume", action="store_true", help="Resume each scope from cursor state.")
    parser.add_argument("--cursor-state", type=Path, default=CURSOR_STATE_JSON, help="Cursor state json path.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report without writing jsonl.")
    parser.add_argument("--output", type=Path, default=LINK_JSONL, help="Output jsonl path.")
    parser.add_argument("--report", type=Path, default=None, help="Optional report json path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    cursor_state_path = args.cursor_state.resolve()
    cursor_state: dict[str, dict] = {}
    if args.resume:
        cursor_state = read_json(cursor_state_path, {})
        if not cursor_state:
            cursor_state = seed_cursor_state_from_reports(cursor_state_path)
    existing, _ = load_existing(output)
    added: list[dict] = []
    stats: dict[str, dict] = {}

    def fetch_scope(
        stats_key: str,
        view: str,
        *,
        category: str = "",
        feed_id: str = "",
        list_id: str = "",
    ) -> None:
        scope_state = cursor_state.get(stats_key, {}) if isinstance(cursor_state.get(stats_key, {}), dict) else {}
        if args.resume and scope_state.get("exhausted"):
            stats[stats_key] = {
                "pages": 0,
                "fetched": 0,
                "added": 0,
                "duplicates": 0,
                "skipped": 0,
                "errors": [],
                "last_cursor": "",
                "has_next": False,
                "view": view,
                "category": category,
                "feedId": feed_id,
                "listId": list_id,
                "resumed_exhausted": True,
            }
            return
        cursor: str | None = str(scope_state.get("cursor") or "").strip() or None
        stats[stats_key] = {
            "pages": 0,
            "fetched": 0,
            "added": 0,
            "duplicates": 0,
            "skipped": 0,
            "errors": [],
            "last_cursor": "",
            "has_next": False,
            "view": view,
            "category": category,
            "feedId": feed_id,
            "listId": list_id,
        }
        for _ in range(max(0, args.max_pages)):
            payload = run_folo_timeline(
                view,
                args.limit,
                cursor,
                args.timeout,
                category=category,
                feed_id=feed_id,
                list_id=list_id,
            )
            if not payload.get("ok"):
                stats[stats_key]["errors"].append(
                    {k: payload.get(k) for k in ("error", "code", "stdout_tail", "stderr_tail") if payload.get(k)}
                )
                break
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            entries = data.get("entries") if isinstance(data.get("entries"), list) else []
            stats[stats_key]["pages"] += 1
            stats[stats_key]["fetched"] += len(entries)
            page_added: list[dict] = []
            for item in entries:
                row = convert_row(item, view) if isinstance(item, dict) else None
                if not row:
                    stats[stats_key]["skipped"] += 1
                    continue
                key = f"{row['feedId']}|{row['entryId']}"
                if key in existing:
                    stats[stats_key]["duplicates"] += 1
                    continue
                existing[key] = row
                added.append(row)
                page_added.append(row)
                stats[stats_key]["added"] += 1
            cursor = str(data.get("nextCursor") or "").strip() or None
            stats[stats_key]["last_cursor"] = cursor or ""
            stats[stats_key]["has_next"] = bool(data.get("hasNext"))
            if not args.dry_run:
                append_jsonl_rows(output, page_added)
                cursor_state[stats_key] = {
                    "cursor": cursor or "",
                    "exhausted": not bool(data.get("hasNext")) or not bool(cursor),
                    "updated_at": utc_now_iso(),
                    "view": view,
                    "category": category,
                    "feedId": feed_id,
                    "listId": list_id,
                }
                cursor_state_path.parent.mkdir(parents=True, exist_ok=True)
                cursor_state_path.write_text(json.dumps(cursor_state, ensure_ascii=False, indent=2), encoding="utf-8")
            if not cursor or not data.get("hasNext") or not entries:
                break

    subscription_targets: list[dict] = []
    if args.split_subscriptions:
        subscription_targets = load_subscription_targets(args.timeout)

    for view in args.views:
        if args.split_subscriptions and view in VIEW_NUMBERS:
            wanted_view = VIEW_NUMBERS[view]
            targets = [target for target in subscription_targets if target.get("view") == wanted_view]
            if args.max_targets > 0:
                targets = targets[: args.max_targets]
            if targets:
                for idx, target in enumerate(targets, start=1):
                    target_type = target.get("target_type") or "target"
                    target_name = target.get("category") or target.get("title") or target.get("feedId") or target.get("listId") or str(idx)
                    stats_key = f"{view}:{target_type}:{target_name}"
                    fetch_scope(
                        stats_key,
                        view,
                        category=str(target.get("category") or ""),
                        feed_id=str(target.get("feedId") or ""),
                        list_id=str(target.get("listId") or ""),
                    )
                continue
        fetch_scope(view, view)

    rows = list(existing.values())
    rows.sort(key=lambda row: str(row.get("published_at") or row.get("created_at") or ""), reverse=True)
    if not args.dry_run:
        write_jsonl_atomic(output, rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = args.report or REPORT_DIR / f"folo_article_links_backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "generated_at": utc_now_iso(),
        "output": str(output),
        "existing_before": len(existing) - len(added),
        "added": len(added),
        "total_after": len(rows),
        "views": stats,
        "sample_added": added[:10],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
