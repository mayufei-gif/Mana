from __future__ import annotations

import csv
import hashlib
import html as html_tools
import hmac
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import base64
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .command_runner import run_inforadar_command
from .file_index import (
    append_folo_article_link,
    append_folo_article_signal,
    folo_article_link_summary,
    latest_status,
    latest_intel_items,
    list_return_files,
    manual_inbox_summary,
    safe_return_file,
    search_personal_radar,
    source_pool_summary,
    watch_summary,
)
from .schemas import CommandRequest, CommandResponse, HealthResponse


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "web" / "frontend"
FOLO_TEST_FEED_STATE = ROOT / "data" / "raw" / "folo_article_links" / "test_feed.json"
RESOURCE_HIVE_PATH = ROOT / "data" / "resource_hive" / "resource_pool.jsonl"
RESOURCE_HIVE_LOCK = threading.Lock()
NAS_RESOURCE_ARCHIVE_ROOT = Path(os.environ.get("INFORADAR_NAS_RESOURCE_ROOT", str(ROOT / "data" / "resource_hive" / "nas_archive_plan")))
RESOURCE_DOWNLOAD_MAX_BYTES = int(os.environ.get("INFORADAR_RESOURCE_DOWNLOAD_MAX_BYTES", str(25 * 1024 * 1024)))
RESOURCE_DOWNLOAD_ALLOWED_SUFFIXES = {".pdf", ".epub", ".txt", ".md", ".json", ".csv", ".opml", ".xml"}
FOLO_SOURCE_TIMELINE_PATH = ROOT / "data" / "folo_hive" / "source_timeline.jsonl"
FOLO_SOURCE_TIMELINE_LOCK = threading.Lock()
FOLO_MANUAL_ENTRIES_PATH = ROOT / "data" / "folo_hive" / "manual_entries.jsonl"
FOLO_MANUAL_ENTRIES_LOCK = threading.Lock()
FOLO_COLLECTOR_ADAPTERS_PATH = ROOT / "data" / "folo_hive" / "collector_adapters.jsonl"
FOLO_COLLECTOR_ADAPTERS_LOCK = threading.Lock()
FOLO_COLLECTOR_WHITELIST_PATH = ROOT / "data" / "folo_hive" / "collector_whitelist.jsonl"
FOLO_COLLECTOR_RUNS_DIR = ROOT / "data" / "folo_hive" / "collector_runs"
FOLO_COLLECTOR_WHITELIST_LOCK = threading.Lock()
SAFE_COLLECTOR_RUNNERS = {"github-repo-metadata-snapshot"}
WECHAT_API_BASE = os.environ.get("INFORADAR_WECHAT_API_BASE", "http://127.0.0.1:5000").strip().rstrip("/")
SESSION_COOKIE = "inforadar_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
SESSION_STORE_PATH = Path(os.environ.get("WEB_SESSION_STORE_PATH", str(ROOT / "data" / "security" / "web_sessions.json")))
SESSION_LOCK = threading.Lock()
TAB_NONCE_HEADER = "x-inforadar-tab-nonce"
CODEX_SESSION_SLOTS = {
    "codex": {"name": "主 Codex", "role": "默认交互会话"},
    "codex-research": {"name": "研究会话", "role": "资料检索和方案沉淀"},
    "codex-build": {"name": "构建会话", "role": "构建、发布、服务维护"},
    "codex-qa": {"name": "日志/测试", "role": "验收、日志、回归检查"},
}
CODEX_WEB_CHAT_DIR = Path(os.environ.get("CODEX_WEB_CHAT_DIR", str(Path.home() / ".inforadar" / "codex-web-chat")))
CODEX_WEB_WORKDIR = Path(os.environ.get("CODEX_WEB_WORKDIR", str(Path.home() / "projects")))
CODEX_WEB_EXEC_TIMEOUT = int(os.environ.get("CODEX_WEB_EXEC_TIMEOUT", "600"))
CODEX_WEB_JOBS: dict[str, dict] = {}
CODEX_WEB_LOCK = threading.Lock()
RUNTIME_ENV_FILE = Path(os.environ.get("INFORADAR_WEB_ENV_FILE", "/home/mana/inforadar-runtime/inforadar-web.env"))
COURSEMIND_PREFIX = "/coursemind"
COURSEMIND_FRONTEND_URL = os.environ.get("COURSEMIND_FRONTEND_URL", "http://100.78.3.45:8788").rstrip("/")
COURSEMIND_BACKEND_URL = os.environ.get("COURSEMIND_BACKEND_URL", "http://100.78.3.45:8766").rstrip("/")
COURSEMIND_PROXY_TIMEOUT = float(os.environ.get("COURSEMIND_PROXY_TIMEOUT", "120"))

app = FastAPI(title="InfoRadar Web", version="0.1.0")


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> FileResponse:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def web_access_token() -> str:
    return os.environ.get("WEB_ACCESS_TOKEN", "").strip() or runtime_env_value("WEB_ACCESS_TOKEN")


def web_totp_secret() -> str:
    return (os.environ.get("WEB_TOTP_SECRET", "").strip() or runtime_env_value("WEB_TOTP_SECRET")).replace(" ", "").upper()


def folo_link_token() -> str:
    return os.environ.get("FOLO_LINK_TOKEN", "").strip() or runtime_env_value("FOLO_LINK_TOKEN")


def runtime_env_value(key: str) -> str:
    if not key or not RUNTIME_ENV_FILE.exists():
        return ""
    try:
        for line in RUNTIME_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def read_folo_test_feed_state() -> dict:
    if FOLO_TEST_FEED_STATE.exists():
        try:
            return json.loads(FOLO_TEST_FEED_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    return {
        "id": "inforadar-folo-webhook-test-initial",
        "title": "InfoRadar Folo Webhook 测试条目",
        "created_at": now.isoformat(),
        "summary": "用于验证 Folo Actions Webhook 是否能把 entry.id/feedId 回传到 InfoRadar。",
    }


def write_folo_test_feed_state() -> dict:
    now = datetime.now(timezone.utc)
    state = {
        "id": f"inforadar-folo-webhook-test-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "title": f"InfoRadar Folo Webhook 测试条目 {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "created_at": now.isoformat(),
        "summary": "如果 Folo Actions 配置正确，订阅这个测试 Feed 后应自动回传 entry.id/feedId。",
    }
    FOLO_TEST_FEED_STATE.parent.mkdir(parents=True, exist_ok=True)
    FOLO_TEST_FEED_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def clean_resource_text(value: object, max_length: int = 600) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:max_length]


def resource_hive_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resource_hive_fingerprint(item: dict) -> str:
    raw = "|".join(
        [
            clean_resource_text(item.get("type"), 80).lower(),
            clean_resource_text(item.get("name"), 300).lower(),
            clean_resource_text(item.get("link"), 1000).lower(),
            clean_resource_text(item.get("nas_path"), 1000).lower(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize_resource_hive_payload(payload: dict) -> dict:
    item = {
        "type": clean_resource_text(payload.get("type") or payload.get("resource_type") or "其它资源", 80),
        "name": clean_resource_text(payload.get("name") or payload.get("title") or payload.get("filename") or "", 300),
        "link": clean_resource_text(payload.get("link") or payload.get("url") or "", 1000),
        "nas_path": clean_resource_text(payload.get("nas_path") or payload.get("nasPath") or "", 1000),
        "source": clean_resource_text(payload.get("source") or "web-resource-hive", 120),
        "status": clean_resource_text(payload.get("status") or "candidate", 80),
        "notes": clean_resource_text(payload.get("notes") or payload.get("note") or "", 1000),
    }
    if not item["name"] and not item["link"] and not item["nas_path"]:
        raise HTTPException(status_code=400, detail="资源名称、链接、NAS路径至少需要一项")
    if not item["name"]:
        item["name"] = item["link"] or item["nas_path"]
    item["fingerprint"] = resource_hive_fingerprint(item)
    item["id"] = f"res-{item['fingerprint']}"
    return item


def read_resource_hive_entries() -> list[dict]:
    if not RESOURCE_HIVE_PATH.exists():
        return []
    rows: list[dict] = []
    for line in RESOURCE_HIVE_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_resource_hive_entries(rows: list[dict]) -> None:
    RESOURCE_HIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RESOURCE_HIVE_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""), encoding="utf-8")
    temp_path.replace(RESOURCE_HIVE_PATH)


def upsert_resource_hive_entry(payload: dict) -> dict:
    incoming = normalize_resource_hive_payload(payload)
    now = resource_hive_now()
    with RESOURCE_HIVE_LOCK:
        rows = read_resource_hive_entries()
        existing = next((item for item in rows if item.get("fingerprint") == incoming["fingerprint"]), None)
        if existing:
            existing.update({key: value for key, value in incoming.items() if value or key in {"status", "source"}})
            existing["updated_at"] = now
            existing["seen_count"] = int(existing.get("seen_count") or 1) + 1
            item = existing
        else:
            item = {
                **incoming,
                "created_at": now,
                "updated_at": now,
                "seen_count": 1,
            }
            rows.append(item)
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        write_resource_hive_entries(rows)
    return item


def resource_hive_summary(limit: int = 120) -> dict:
    rows = read_resource_hive_entries()
    rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    by_type: dict[str, int] = {}
    archived = 0
    linked = 0
    for item in rows:
        item_type = str(item.get("type") or "其它资源")
        by_type[item_type] = by_type.get(item_type, 0) + 1
        if item.get("nas_path"):
            archived += 1
        if item.get("link"):
            linked += 1
    return {
        "ok": True,
        "path": str(RESOURCE_HIVE_PATH),
        "total": len(rows),
        "linked_count": linked,
        "nas_archived_count": archived,
        "by_type": by_type,
        "items": rows[:limit],
        "export_markdown": "/api/resource-hive/export?format=md",
        "export_jsonl": "/api/resource-hive/export?format=jsonl",
        "note": "当前资源池负责沉淀候选资源；自动全网搜索和 NAS 自动归档由后续任务接入。",
    }


def resource_hive_markdown() -> str:
    data = resource_hive_summary(limit=10000)
    lines = [
        "# InfoRadar 全网资源鉴赏池",
        "",
        f"- 导出时间：{resource_hive_now()}",
        f"- 总资源：{data['total']}",
        f"- 有外部链接：{data['linked_count']}",
        f"- 已关联 NAS 路径：{data['nas_archived_count']}",
        f"- 数据文件：`{data['path']}`",
        "",
        "| 类型 | 名称 | 状态 | 次数 | 链接 | NAS路径 | 更新时间 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in data["items"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("type") or ""),
                    str(item.get("name") or "").replace("|", "\\|"),
                    str(item.get("status") or ""),
                    str(item.get("seen_count") or 1),
                    str(item.get("link") or "").replace("|", "%7C"),
                    str(item.get("nas_path") or "").replace("|", "\\|"),
                    str(item.get("updated_at") or item.get("created_at") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def archive_safe_name(value: str, max_length: int = 96) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", clean_resource_text(value, max_length)).strip(" ._")
    return cleaned or "未命名资源"


def resource_hive_archive_plan(limit: int = 120) -> dict:
    rows = read_resource_hive_entries()
    rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    pending = []
    for item in rows:
        if item.get("nas_path"):
            continue
        name = archive_safe_name(str(item.get("name") or "未命名资源"))
        resource_type = archive_safe_name(str(item.get("type") or "其它资源"), 48)
        link = str(item.get("link") or "").strip()
        suggested_path = NAS_RESOURCE_ARCHIVE_ROOT / resource_type / f"{name}.url"
        pending.append(
            {
                "name": item.get("name") or "未命名资源",
                "type": item.get("type") or "其它资源",
                "link": link,
                "source": item.get("source") or "",
                "fingerprint": item.get("fingerprint") or resource_hive_fingerprint(item),
                "suggested_nas_path": str(suggested_path),
                "safe_to_auto_download": False,
                "reason": "仅生成归档计划；版权、登录态和文件来源未确认前不自动下载。",
            }
        )
        if len(pending) >= limit:
            break
    return {
        "ok": True,
        "archive_root": str(NAS_RESOURCE_ARCHIVE_ROOT),
        "total_pending": len(pending),
        "items": pending,
        "note": "这是 NAS 归档安全门：只生成待归档计划，不自动下载或写入资源文件。",
    }


def write_url_shortcut(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")


def resource_hive_archive_links(limit: int = 120) -> dict:
    written = []
    skipped = []
    now = resource_hive_now()
    with RESOURCE_HIVE_LOCK:
        rows = read_resource_hive_entries()
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        for item in rows:
            if len(written) >= limit:
                break
            if item.get("nas_path"):
                continue
            link = str(item.get("link") or "").strip()
            if not link.startswith(("http://", "https://")):
                skipped.append({"name": item.get("name") or "未命名资源", "reason": "缺少 http/https 链接"})
                continue
            name = archive_safe_name(str(item.get("name") or "未命名资源"))
            resource_type = archive_safe_name(str(item.get("type") or "其它资源"), 48)
            shortcut_path = NAS_RESOURCE_ARCHIVE_ROOT / resource_type / f"{name}.url"
            write_url_shortcut(shortcut_path, link)
            item["nas_path"] = str(shortcut_path)
            item["archived_at"] = now
            item["status"] = "linked-to-nas"
            item["updated_at"] = now
            written.append(
                {
                    "name": item.get("name") or "未命名资源",
                    "type": item.get("type") or "其它资源",
                    "link": link,
                    "nas_path": str(shortcut_path),
                    "fingerprint": item.get("fingerprint") or resource_hive_fingerprint(item),
                }
            )
        write_resource_hive_entries(rows)
    return {
        "ok": True,
        "archive_root": str(NAS_RESOURCE_ARCHIVE_ROOT),
        "written_count": len(written),
        "skipped_count": len(skipped),
        "items": written,
        "skipped": skipped[:20],
        "resource_hive": resource_hive_summary(limit=120),
        "note": "仅写入 .url 链接文件，不下载原始资源内容。",
    }


def resource_hive_approve_download(fingerprint: str) -> dict:
    selected = clean_resource_text(fingerprint, 120)
    if not selected:
        raise HTTPException(status_code=400, detail="缺少资源 fingerprint")
    now = resource_hive_now()
    with RESOURCE_HIVE_LOCK:
        rows = read_resource_hive_entries()
        item = next((row for row in rows if row.get("fingerprint") == selected), None)
        if not item:
            raise HTTPException(status_code=404, detail="资源不存在")
        if not str(item.get("link") or "").startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="该资源没有可下载链接")
        item["status"] = "download-approved"
        item["download_approved_at"] = now
        item["updated_at"] = now
        write_resource_hive_entries(rows)
    return {**resource_hive_summary(limit=120), "item": item}


def resource_download_suffix(url: str, content_type: str = "") -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in RESOURCE_DOWNLOAD_ALLOWED_SUFFIXES:
        return suffix
    normalized = content_type.lower().split(";")[0].strip()
    mapping = {
        "application/pdf": ".pdf",
        "application/epub+zip": ".epub",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "application/json": ".json",
        "text/csv": ".csv",
        "application/xml": ".xml",
        "text/xml": ".xml",
    }
    return mapping.get(normalized, "")


def fetch_download_bytes(url: str) -> tuple[bytes, str]:
    safe_url = validate_public_http_url(url)
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 InfoRadarResourceDownloader/1.0",
            "Accept": "application/pdf,application/epub+zip,text/plain,text/markdown,application/json,text/csv,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("content-type", "")
        content_length = response.headers.get("content-length")
        try:
            if content_length and int(content_length) > RESOURCE_DOWNLOAD_MAX_BYTES:
                raise HTTPException(status_code=400, detail="文件超过允许下载大小")
        except ValueError:
            pass
        data = response.read(RESOURCE_DOWNLOAD_MAX_BYTES + 1)
    if len(data) > RESOURCE_DOWNLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过允许下载大小")
    return data, content_type


def resource_hive_download_approved(limit: int = 20) -> dict:
    downloaded = []
    skipped = []
    now = resource_hive_now()
    with RESOURCE_HIVE_LOCK:
        rows = read_resource_hive_entries()
        for item in rows:
            if len(downloaded) >= limit:
                break
            if item.get("status") != "download-approved":
                continue
            link = str(item.get("link") or "").strip()
            try:
                data, content_type = fetch_download_bytes(link)
                suffix = resource_download_suffix(link, content_type)
                if not suffix:
                    raise HTTPException(status_code=400, detail="文件类型不在下载白名单")
                name = archive_safe_name(str(item.get("name") or "未命名资源"))
                resource_type = archive_safe_name(str(item.get("type") or "其它资源"), 48)
                target_path = NAS_RESOURCE_ARCHIVE_ROOT / resource_type / f"{name}{suffix}"
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)
                item["nas_path"] = str(target_path)
                item["status"] = "downloaded-to-nas"
                item["downloaded_at"] = now
                item["updated_at"] = now
                downloaded.append(
                    {
                        "name": item.get("name") or "未命名资源",
                        "type": item.get("type") or "其它资源",
                        "link": link,
                        "nas_path": str(target_path),
                        "bytes": len(data),
                        "fingerprint": item.get("fingerprint") or resource_hive_fingerprint(item),
                    }
                )
            except Exception as exc:
                skipped.append({"name": item.get("name") or "未命名资源", "link": link, "reason": str(exc)})
        write_resource_hive_entries(rows)
    return {
        "ok": True,
        "archive_root": str(NAS_RESOURCE_ARCHIVE_ROOT),
        "downloaded_count": len(downloaded),
        "skipped_count": len(skipped),
        "items": downloaded,
        "skipped": skipped[:20],
        "resource_hive": resource_hive_summary(limit=120),
        "note": "只下载 status=download-approved 且类型/大小通过白名单的资源。",
    }


def folo_timeline_key(payload: dict) -> str:
    raw = "|".join(
        [
            clean_resource_text(payload.get("key"), 240),
            clean_resource_text(payload.get("url"), 1000),
            clean_resource_text(payload.get("title"), 300),
            clean_resource_text(payload.get("source"), 200),
        ]
    ).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_folo_timeline_payload(payload: dict) -> dict:
    item = {
        "key": clean_resource_text(payload.get("key") or payload.get("folo_key") or "", 240),
        "title": clean_resource_text(payload.get("title") or payload.get("folo_title") or "未命名 Folo 源", 300),
        "source": clean_resource_text(payload.get("source") or payload.get("folo_source") or "未知来源", 200),
        "url": clean_resource_text(payload.get("url") or payload.get("folo_url") or "", 1000),
    }
    if not item["key"]:
        item["key"] = folo_timeline_key(item)
    return item


def read_folo_timeline_entries() -> list[dict]:
    if not FOLO_SOURCE_TIMELINE_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FOLO_SOURCE_TIMELINE_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_folo_timeline_entries(rows: list[dict]) -> None:
    FOLO_SOURCE_TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = FOLO_SOURCE_TIMELINE_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""), encoding="utf-8")
    temp_path.replace(FOLO_SOURCE_TIMELINE_PATH)


def record_folo_timeline_click(payload: dict) -> dict:
    incoming = normalize_folo_timeline_payload(payload)
    now = resource_hive_now()
    click = {"at": now}
    with FOLO_SOURCE_TIMELINE_LOCK:
        rows = read_folo_timeline_entries()
        current = next((item for item in rows if item.get("key") == incoming["key"]), None)
        if current:
            current.update({key: value for key, value in incoming.items() if value})
            current["count"] = int(current.get("count") or 0) + 1
            current["updated_at"] = now
            current["clicks"] = [*(current.get("clicks") or []), click][-80:]
            item = current
        else:
            item = {
                **incoming,
                "count": 1,
                "created_at": now,
                "updated_at": now,
                "clicks": [click],
            }
            rows.append(item)
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        write_folo_timeline_entries(rows)
    return item


def folo_timeline_summary(limit: int = 80) -> dict:
    rows = read_folo_timeline_entries()
    rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    stars = [item for item in rows if int(item.get("count") or 0) >= 3]
    return {
        "ok": True,
        "path": str(FOLO_SOURCE_TIMELINE_PATH),
        "total": len(rows),
        "star_count": len(stars),
        "items": rows[:limit],
        "stars": stars[:limit],
        "note": "Folo 寻源点击时间线，点击 3 次及以上自动进入星标级别。",
    }


def manual_hive_fingerprint(payload: dict) -> str:
    raw = "|".join(
        [
            clean_resource_text(payload.get("platform"), 80),
            clean_resource_text(payload.get("name"), 300),
            clean_resource_text(payload.get("url"), 1000),
        ]
    ).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_manual_hive_payload(payload: dict) -> dict:
    try:
        score = int(payload.get("score") or 65)
    except Exception:
        score = 65
    item = {
        "id": clean_resource_text(payload.get("id") or "", 120),
        "platform": clean_resource_text(payload.get("platform") or "其它", 80),
        "name": clean_resource_text(payload.get("name") or payload.get("title") or "", 300),
        "url": clean_resource_text(payload.get("url") or "", 1000),
        "score": score,
        "source": clean_resource_text(payload.get("source") or "manual-hive", 120),
    }
    if not item["name"] and not item["url"]:
        raise ValueError("缺少名称或 URL")
    if not item["name"]:
        item["name"] = item["url"]
    item["fingerprint"] = manual_hive_fingerprint(item)
    if not item["id"]:
        item["id"] = f"manual-{item['fingerprint']}"
    return item


def read_manual_hive_entries() -> list[dict]:
    if not FOLO_MANUAL_ENTRIES_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FOLO_MANUAL_ENTRIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_manual_hive_entries(rows: list[dict]) -> None:
    FOLO_MANUAL_ENTRIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = FOLO_MANUAL_ENTRIES_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""), encoding="utf-8")
    temp_path.replace(FOLO_MANUAL_ENTRIES_PATH)


def upsert_manual_hive_entry(payload: dict) -> dict:
    incoming = normalize_manual_hive_payload(payload)
    now = resource_hive_now()
    with FOLO_MANUAL_ENTRIES_LOCK:
        rows = read_manual_hive_entries()
        current = next((item for item in rows if item.get("fingerprint") == incoming["fingerprint"]), None)
        if current:
            current.update({key: value for key, value in incoming.items() if value})
            current["seen_count"] = int(current.get("seen_count") or 1) + 1
            current["updated_at"] = now
            item = current
        else:
            item = {
                **incoming,
                "seen_count": 1,
                "created_at": payload.get("created_at") or now,
                "updated_at": now,
            }
            rows.append(item)
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        write_manual_hive_entries(rows)
    return item


def manual_hive_summary(limit: int = 80) -> dict:
    rows = read_manual_hive_entries()
    rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    return {
        "ok": True,
        "path": str(FOLO_MANUAL_ENTRIES_PATH),
        "total": len(rows),
        "items": rows[:limit],
        "note": "手动信息获取站服务端池，会并入信息寻缘卡片池。",
    }


def wechat_api_json(path: str, method: str = "GET", payload: dict | None = None, timeout: int = 40) -> dict:
    if not WECHAT_API_BASE:
        raise RuntimeError("未配置 INFORADAR_WECHAT_API_BASE")
    url = f"{WECHAT_API_BASE}{path}"
    data = None
    headers = {"User-Agent": "InfoRadarManualHive/1.0"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"微信采集器返回非 JSON：{text[:200]}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("微信采集器返回结构不是对象")
    return value


def wechat_api_text(path: str, timeout: int = 40) -> str:
    if not WECHAT_API_BASE:
        raise RuntimeError("未配置 INFORADAR_WECHAT_API_BASE")
    url = f"{WECHAT_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "InfoRadarManualHive/1.0",
            "Accept": "application/rss+xml,application/xml,text/xml,text/plain;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def wechat_rss_url(fakeid: str) -> str:
    fid = str(fakeid or "").strip()
    return f"/api/manual-hive/wechat/rss?fakeid={urllib.parse.quote(fid, safe='')}"


def request_public_base_url(request: Request) -> str:
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    return f"{scheme}://{host}".rstrip("/")


def absolute_url(request: Request, path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if not text.startswith("/"):
        text = f"/{text}"
    return f"{request_public_base_url(request)}{text}"


def wechat_folo_feed_url(request: Request, fakeid: str) -> str:
    fid = str(fakeid or "").strip()
    return absolute_url(request, f"/api/folo/wechat-feed?fakeid={urllib.parse.quote(fid, safe='')}")


def folo_open_url(feed_url: str, nickname: str = "") -> str:
    query = feed_url or nickname or "RSS"
    return f"https://app.folo.is/discover?keyword={urllib.parse.quote(query, safe='')}"


def wechat_rss_view_url(fakeid: str) -> str:
    fid = str(fakeid or "").strip()
    return f"/api/manual-hive/wechat/rss-view?fakeid={urllib.parse.quote(fid, safe='')}"


def wechat_internal_rss_path(fakeid: str) -> str:
    return f"/api/rss/{urllib.parse.quote(str(fakeid or '').strip(), safe='')}"


def rewrite_wechat_rss_self_url(rss_text: str, fakeid: str, replacement_url: str) -> str:
    fid = str(fakeid or "").strip()
    if not fid or not replacement_url:
        return rss_text
    quoted = urllib.parse.quote(fid, safe="")
    result = rss_text
    for old in (
        f"{WECHAT_API_BASE}/api/rss/{fid}",
        f"{WECHAT_API_BASE}/api/rss/{quoted}",
        wechat_rss_url(fid),
    ):
        result = result.replace(old, replacement_url)
    return result


def rss_datetime_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return text


def strip_rss_html(value: str, limit: int = 900) -> str:
    text = html_tools.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return clean_resource_text(text, limit)


def parse_wechat_rss_articles(rss_text: str, fakeid: str, nickname: str = "", limit: int = 80) -> list[dict]:
    try:
        root = ET.fromstring(rss_text.encode("utf-8"))
    except ET.ParseError as exc:
        raise RuntimeError("微信 RSS XML 解析失败") from exc
    channel_title = clean_resource_text(root.findtext(".//channel/title") or nickname or "微信公众号", 240)
    source_name = clean_resource_text(nickname or channel_title or "微信公众号", 240)
    rows: list[dict] = []
    content_key = "{http://purl.org/rss/1.0/modules/content/}encoded"
    for item in root.findall(".//item")[:limit]:
        title = clean_resource_text(item.findtext("title") or "", 240)
        link = clean_resource_text(item.findtext("link") or "", 1000)
        guid = clean_resource_text(item.findtext("guid") or link, 1000)
        published_at = rss_datetime_text(item.findtext("pubDate") or "")
        summary = strip_rss_html(item.findtext(content_key) or item.findtext("description") or "", 900)
        if not title and not link:
            continue
        rows.append(
            {
                "标题": title or f"{source_name} 文章",
                "来源名称": source_name,
                "Folo订阅源名称": source_name,
                "Folo文件夹路径": "微信公众号/手动信息获取站",
                "发布时间": published_at,
                "原文URL": link,
                "订阅源URL": wechat_rss_url(fakeid),
                "可抓取RSS链接": wechat_rss_url(fakeid),
                "来源类型": "微信公众号RSS",
                "采集方式": "wechat-download-api rss poll",
                "fakeid": fakeid,
                "标签": "微信公众号;手动信息获取站",
                "摘要": summary,
                "状态": "active",
                "guid": guid,
            }
        )
    return rows


def write_wechat_article_rows(fakeid: str, nickname: str, rows: list[dict]) -> Path:
    digest = hashlib.sha1(str(fakeid or nickname or "wechat").encode("utf-8", errors="ignore")).hexdigest()[:12]
    path = ROOT / "data" / "deduped" / "wechat" / f"folo_wechat_{digest}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "标题",
        "来源名称",
        "Folo订阅源名称",
        "Folo文件夹路径",
        "发布时间",
        "原文URL",
        "订阅源URL",
        "可抓取RSS链接",
        "来源类型",
        "采集方式",
        "fakeid",
        "标签",
        "摘要",
        "状态",
        "guid",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def import_wechat_rss_articles(fakeid: str, nickname: str = "", rebuild_index: bool = True) -> dict:
    fid = clean_resource_text(fakeid, 200)
    if not fid:
        raise ValueError("缺少 fakeid")
    rss_text = wechat_api_text(wechat_internal_rss_path(fid), timeout=45)
    rows = parse_wechat_rss_articles(rss_text, fid, nickname)
    csv_path = write_wechat_article_rows(fid, nickname, rows)
    index_result = {}
    if rebuild_index:
        try:
            from .file_index import build_search_index

            index_result = build_search_index(force=True)
        except Exception as exc:
            index_result = {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "fakeid": fid,
        "nickname": nickname,
        "article_count": len(rows),
        "csv": str(csv_path),
        "rss_url": wechat_rss_url(fid),
        "index": index_result,
    }


def render_wechat_rss_view(fakeid: str, rss_text: str) -> str:
    rows = parse_wechat_rss_articles(rss_text, fakeid)
    try:
        root = ET.fromstring(rss_text.encode("utf-8"))
        title = clean_resource_text(root.findtext(".//channel/title") or "微信公众号", 240)
        description = strip_rss_html(root.findtext(".//channel/description") or "", 300)
        updated = rss_datetime_text(root.findtext(".//channel/lastBuildDate") or "")
    except Exception:
        title, description, updated = "微信公众号", "", ""
    cards = []
    for row in rows:
        article_title = html_tools.escape(row.get("标题") or "未命名文章")
        article_url = html_tools.escape(row.get("原文URL") or "")
        published_at = html_tools.escape(row.get("发布时间") or "未记录时间")
        summary = html_tools.escape(row.get("摘要") or "暂无摘要")
        cards.append(
            f"""
            <article class="article-card">
              <div class="article-time">{published_at}</div>
              <h2>{article_title}</h2>
              <p>{summary}</p>
              {f'<a class="open-link" href="{article_url}" target="_blank" rel="noreferrer">打开微信原文</a>' if article_url else ''}
            </article>
            """
        )
    if not cards:
        cards.append('<article class="article-card"><p>当前 RSS 里还没有可展示的文章。</p></article>')
    safe_title = html_tools.escape(title)
    safe_description = html_tools.escape(description)
    safe_updated = html_tools.escape(updated or "未记录")
    raw_url = html_tools.escape(wechat_rss_url(fakeid))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title} - InfoRadar RSS 阅读</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #19312f;
      --muted: #60736d;
      --line: #d8e3dd;
      --panel: #ffffff;
      --bg: #f4f8f6;
      --mint: #16745f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.55;
    }}
    main {{
      width: min(920px, calc(100% - 28px));
      margin: 0 auto;
      padding: 22px 0 34px;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      margin: 0 -14px 16px;
      padding: 18px 14px 14px;
      background: rgba(244, 248, 246, .94);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(24px, 5vw, 38px);
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    a {{
      color: var(--mint);
      font-weight: 800;
      text-decoration: none;
    }}
    .actions a,
    .open-link {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid rgba(22, 116, 95, .24);
      border-radius: 7px;
      background: #eef7f2;
    }}
    .article-list {{
      display: grid;
      gap: 12px;
    }}
    .article-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
      box-shadow: 0 8px 20px rgba(31, 55, 49, .06);
    }}
    .article-time {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 6px;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    p {{
      margin: 0 0 12px;
      color: #40524d;
      overflow-wrap: anywhere;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{safe_title}</h1>
      <div class="meta">{safe_description}</div>
      <div class="meta">更新时间：{safe_updated} · 文章 {len(rows)} 篇</div>
      <div class="actions">
        <a href="/#inforadar">返回 InfoRadar</a>
        <a href="{raw_url}" target="_blank" rel="noreferrer">查看原始 RSS</a>
      </div>
    </header>
    <section class="article-list">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>"""


def manual_hive_wechat_actions(fakeid: str, nickname: str) -> list[dict]:
    rss_url = wechat_rss_url(fakeid) if fakeid else ""
    search_query = nickname or "微信公众号"
    return [
        {"key": "subscribe_wechat", "label": "订阅公众号", "method": "POST", "endpoint": "/api/manual-hive/wechat/subscribe"},
        {"key": "poll_articles", "label": "拉取文章", "method": "POST", "endpoint": "/api/manual-hive/wechat/subscribe"},
        {"key": "open_rss", "label": "查看文章", "url": wechat_rss_view_url(fakeid) if fakeid else rss_url},
        {"key": "open_folo", "label": "在 Folo 订阅并打开", "method": "POST", "endpoint": "/api/manual-hive/wechat/folo-open"},
        {"key": "search_inforadar", "label": "检索文章", "url": f"/#inforadar?search={urllib.parse.quote(search_query)}"},
    ]


def normalize_wechat_search_item(item: dict, subscribed_fakeids: set[str] | None = None) -> dict:
    fakeid = clean_resource_text(item.get("fakeid"), 200)
    nickname = clean_resource_text(item.get("nickname"), 240)
    alias = clean_resource_text(item.get("alias"), 120)
    rss_url = wechat_rss_url(fakeid) if fakeid else ""
    subscribed = bool(subscribed_fakeids and fakeid in subscribed_fakeids)
    return {
        "platform": "公众号",
        "fakeid": fakeid,
        "nickname": nickname,
        "name": nickname,
        "alias": alias,
        "service_type": item.get("service_type", 0),
        "round_head_img": clean_resource_text(item.get("round_head_img"), 1000),
        "rss_url": rss_url,
        "rss_view_url": wechat_rss_view_url(fakeid) if fakeid else "",
        "subscribed": subscribed,
        "status": "已订阅" if subscribed else "可订阅",
        "actions": manual_hive_wechat_actions(fakeid, nickname),
    }


def wechat_subscription_fakeids() -> set[str]:
    try:
        data = wechat_api_json("/api/rss/subscriptions", timeout=15)
    except Exception:
        return set()
    rows = data.get("data") if data.get("success") else []
    if not isinstance(rows, list):
        return set()
    return {str(item.get("fakeid") or "").strip() for item in rows if str(item.get("fakeid") or "").strip()}


def search_wechat_accounts(query: str, limit: int = 8) -> dict:
    text = clean_resource_text(query, 120)
    if not text:
        raise ValueError("缺少公众号名称")
    data = wechat_api_json(f"/api/public/searchbiz?query={urllib.parse.quote(text)}", timeout=35)
    if not data.get("success"):
        return {"ok": False, "platform": "公众号", "query": text, "items": [], "error": data.get("error") or "公众号搜索失败"}
    raw_items = ((data.get("data") or {}).get("list") or [])[:limit]
    subscribed = wechat_subscription_fakeids()
    items = [normalize_wechat_search_item(item, subscribed) for item in raw_items if isinstance(item, dict)]
    return {"ok": True, "platform": "公众号", "query": text, "items": items, "count": len(items), "source": "wechat-download-api"}


def subscribe_wechat_account(fakeid: str, nickname: str = "", poll: bool = True) -> dict:
    fid = clean_resource_text(fakeid, 200)
    name = clean_resource_text(nickname or "微信公众号", 240)
    if not fid:
        raise ValueError("缺少 fakeid")
    subscribe_payload = {"fakeid": fid, "nickname": name, "category": "手动信息获取站/公众号"}
    subscribe_result = wechat_api_json("/api/rss/subscribe", method="POST", payload=subscribe_payload, timeout=25)
    poll_result = {}
    if poll:
        try:
            poll_result = wechat_api_json("/api/rss/poll", method="POST", payload={}, timeout=90)
        except Exception as exc:
            poll_result = {"success": False, "error": str(exc)}
    import_result = {}
    try:
        import_result = import_wechat_rss_articles(fid, name, rebuild_index=True)
    except Exception as exc:
        import_result = {"ok": False, "error": str(exc)}
    manual_item = upsert_manual_hive_entry(
        {
            "platform": "公众号",
            "name": name,
            "url": wechat_rss_url(fid),
            "score": 75,
            "source": "wechat-download-api",
        }
    )
    return {
        "ok": bool(subscribe_result.get("success", True)),
        "platform": "公众号",
        "fakeid": fid,
        "nickname": name,
        "rss_url": wechat_rss_url(fid),
        "subscribe_result": subscribe_result,
        "poll_result": poll_result,
        "import_result": import_result,
        "item": normalize_wechat_search_item({"fakeid": fid, "nickname": name, "alias": ""}, {fid}),
        "manual_entry": manual_item,
    }


def open_wechat_in_folo(request: Request, fakeid: str, nickname: str = "", poll: bool = True) -> dict:
    fid = clean_resource_text(fakeid, 200)
    name = clean_resource_text(nickname or "微信公众号", 240)
    if not fid:
        raise ValueError("缺少 fakeid")
    subscription = subscribe_wechat_account(fid, name, poll=poll)
    feed_url = wechat_folo_feed_url(request, fid)
    open_url = folo_open_url(feed_url, name)
    return {
        **subscription,
        "ok": bool(subscription.get("ok", True)),
        "feed_url": feed_url,
        "folo_open_url": open_url,
        "folo_url": open_url,
        "rss_view_url": absolute_url(request, wechat_rss_view_url(fid)),
        "raw_rss_url": absolute_url(request, wechat_rss_url(fid)),
        "clipboard_text": feed_url,
        "message": "已订阅公众号并生成 Folo 可抓取 RSS；如果 Folo 未自动识别，请在 Folo 搜索框粘贴该 RSS 地址。",
    }


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._active_href = ""
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        classes = data.get("class", "")
        href = data.get("href", "").strip()
        if "result__a" in classes and href:
            self._active_href = href
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        title = re.sub(r"\s+", " ", " ".join(self._active_text)).strip()
        if title:
            self.results.append({"title": title, "href": self._active_href})
        self._active_href = ""
        self._active_text = []


def decode_duckduckgo_href(href: str) -> str:
    text = str(href or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    if text.startswith("/"):
        text = "https://duckduckgo.com" + text
    parsed = urllib.parse.urlparse(text)
    params = urllib.parse.parse_qs(parsed.query)
    if params.get("uddg"):
        return params["uddg"][0]
    return text


def decode_bing_href(href: str) -> str:
    text = str(href or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    params = urllib.parse.parse_qs(parsed.query)
    encoded = (params.get("u") or [""])[0]
    if encoded.startswith("a1"):
        raw = encoded[2:]
        padding = "=" * ((4 - len(raw) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8", errors="replace")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass
    return text


def resource_discovery_query(query: str, resource_type: str) -> str:
    base = clean_resource_text(query, 160)
    item_type = clean_resource_text(resource_type or "其它资源", 80)
    modifiers = {
        "书籍": "book pdf epub archive library",
        "解密档案": "declassified archive filetype:pdf",
        "题库": "exam questions pdf practice answer",
        "软件包": "software package GitHub release download documentation",
        "论文/报告": "paper report PDF dataset whitepaper",
    }
    return f"{base} {modifiers.get(item_type, item_type + ' 资源 标题 文件名')}".strip()


def fetch_search_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 InfoRadarResourceHive/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=14) as response:
        return response.read(1_000_000).decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 14) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 InfoRadarResourceHive/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))


def validate_public_http_url(url: str) -> str:
    cleaned = clean_resource_text(url, 1000)
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入 http/https 订阅源 URL")
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="不允许探测本机或局域网地址")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise HTTPException(status_code=400, detail="不允许探测私有或本机 IP")
    except ValueError:
        pass
    return cleaned


def fetch_feed_xml(url: str) -> str:
    safe_url = validate_public_http_url(url)
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 InfoRadarFeedProbe/1.0",
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=14) as response:
        return response.read(1_000_000).decode("utf-8", errors="replace")


def child_text(node: ET.Element | None, *names: str) -> str:
    if node is None:
        return ""
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return clean_resource_text(child.text, 1000)
    return ""


def atom_link(node: ET.Element) -> str:
    for link in node.findall("{http://www.w3.org/2005/Atom}link"):
        href = clean_resource_text(link.attrib.get("href") or "", 1000)
        rel = clean_resource_text(link.attrib.get("rel") or "alternate", 80)
        if href and rel in {"alternate", ""}:
            return href
    return ""


def parse_feed_xml(feed_xml: str, source_url: str = "", limit: int = 12) -> dict:
    try:
        root = ET.fromstring(feed_xml.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail="URL 返回内容不是可解析的 RSS/Atom XML") from exc
    items = []
    channel = root.find("channel")
    if channel is not None:
        feed_title = child_text(channel, "title") or source_url
        for item in channel.findall("item")[:limit]:
            items.append(
                {
                    "title": child_text(item, "title") or "未命名条目",
                    "link": child_text(item, "link"),
                    "published_at": child_text(item, "pubDate", "published", "updated"),
                    "summary": child_text(item, "description"),
                }
            )
    elif root.tag.endswith("feed"):
        ns = "{http://www.w3.org/2005/Atom}"
        feed_title = child_text(root, f"{ns}title") or source_url
        for entry in root.findall(f"{ns}entry")[:limit]:
            items.append(
                {
                    "title": child_text(entry, f"{ns}title") or "未命名条目",
                    "link": atom_link(entry),
                    "published_at": child_text(entry, f"{ns}published", f"{ns}updated"),
                    "summary": child_text(entry, f"{ns}summary", f"{ns}content"),
                }
            )
    else:
        raise HTTPException(status_code=400, detail="未识别 RSS channel 或 Atom feed")
    return {
        "ok": True,
        "title": feed_title,
        "source_url": source_url,
        "count": len(items),
        "items": items,
        "note": "RSS/Atom 内置适配器只解析公开订阅源，不执行外部采集器代码。",
    }


def discover_openlibrary_candidates(query: str, limit: int = 8) -> list[dict]:
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode({"q": query, "limit": limit})
    data = fetch_json(url)
    rows = []
    for doc in (data.get("docs") or [])[:limit]:
        title = clean_resource_text(doc.get("title"), 240)
        key = clean_resource_text(doc.get("key"), 240)
        if not title or not key:
            continue
        authors = ", ".join(clean_resource_text(item, 80) for item in (doc.get("author_name") or [])[:2])
        year = doc.get("first_publish_year") or ""
        rows.append(
            {
                "id": f"openlibrary-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}",
                "type": "书籍",
                "name": f"{title}{f' - {authors}' if authors else ''}{f' ({year})' if year else ''}",
                "link": f"https://openlibrary.org{key}",
                "source": "openlibrary-api",
                "status": "discovered",
                "notes": f"query={query}",
            }
        )
    return rows


def discover_github_candidates(query: str, limit: int = 8) -> list[dict]:
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": query, "per_page": limit, "sort": "stars"})
    data = fetch_json(url)
    rows = []
    for repo in (data.get("items") or [])[:limit]:
        name = clean_resource_text(repo.get("full_name") or repo.get("name"), 240)
        link = clean_resource_text(repo.get("html_url"), 1000)
        if not name or not link:
            continue
        description = clean_resource_text(repo.get("description") or "", 240)
        rows.append(
            {
                "id": f"github-{repo.get('id')}",
                "type": "软件包",
                "name": name,
                "link": link,
                "source": "github-search-api",
                "status": "discovered",
                "notes": description or f"query={query}",
            }
        )
    return rows


COLLECTOR_ADAPTER_PRESETS = [
    {"platform": "公众号", "query": "wechat official account crawler rss github"},
    {"platform": "快手", "query": "kuaishou crawler downloader github"},
    {"platform": "抖音", "query": "douyin crawler downloader github"},
    {"platform": "B站", "query": "bilibili crawler rss github"},
    {"platform": "Twitch", "query": "twitch api crawler github"},
    {"platform": "YouTube", "query": "youtube rss crawler github"},
    {"platform": "TED", "query": "ted talks scraper rss github"},
]


def collector_adapter_fingerprint(item: dict) -> str:
    raw = "|".join(
        [
            clean_resource_text(item.get("platform"), 80),
            clean_resource_text(item.get("repo_url") or item.get("link"), 1000),
            clean_resource_text(item.get("name"), 240),
        ]
    ).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_collector_adapter(payload: dict) -> dict:
    item = {
        "platform": clean_resource_text(payload.get("platform") or "其它", 80),
        "name": clean_resource_text(payload.get("name") or "未命名采集器", 240),
        "repo_url": clean_resource_text(payload.get("repo_url") or payload.get("link") or "", 1000),
        "source": clean_resource_text(payload.get("source") or "github-search-api", 120),
        "status": clean_resource_text(payload.get("status") or "候选", 80),
        "notes": clean_resource_text(payload.get("notes") or "", 500),
    }
    item["fingerprint"] = collector_adapter_fingerprint(item)
    return item


def read_collector_adapters() -> list[dict]:
    if not FOLO_COLLECTOR_ADAPTERS_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FOLO_COLLECTOR_ADAPTERS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_collector_adapters(rows: list[dict]) -> None:
    FOLO_COLLECTOR_ADAPTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = FOLO_COLLECTOR_ADAPTERS_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""), encoding="utf-8")
    temp_path.replace(FOLO_COLLECTOR_ADAPTERS_PATH)


def read_collector_whitelist() -> list[dict]:
    if not FOLO_COLLECTOR_WHITELIST_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FOLO_COLLECTOR_WHITELIST_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_collector_whitelist(rows: list[dict]) -> None:
    FOLO_COLLECTOR_WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = FOLO_COLLECTOR_WHITELIST_PATH.with_suffix(".jsonl.tmp")
    temp_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + ("\n" if rows else ""), encoding="utf-8")
    temp_path.replace(FOLO_COLLECTOR_WHITELIST_PATH)


def read_collector_runs(limit: int = 20) -> list[dict]:
    if not FOLO_COLLECTOR_RUNS_DIR.exists():
        return []
    rows: list[dict] = []
    for path in FOLO_COLLECTOR_RUNS_DIR.glob("*/*/result.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    rows.sort(key=lambda entry: str(entry.get("finished_at") or entry.get("started_at") or ""), reverse=True)
    return rows[:limit]


def upsert_collector_adapter(payload: dict) -> dict:
    incoming = normalize_collector_adapter(payload)
    now = resource_hive_now()
    with FOLO_COLLECTOR_ADAPTERS_LOCK:
        rows = read_collector_adapters()
        current = next((item for item in rows if item.get("fingerprint") == incoming["fingerprint"]), None)
        if current:
            current.update({key: value for key, value in incoming.items() if value})
            current["seen_count"] = int(current.get("seen_count") or 1) + 1
            current["updated_at"] = now
            item = current
        else:
            item = {**incoming, "seen_count": 1, "created_at": now, "updated_at": now}
            rows.append(item)
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
        write_collector_adapters(rows)
    return item


def collector_adapter_summary(limit: int = 80) -> dict:
    rows = read_collector_adapters()
    rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    platforms = {item["platform"]: item for item in COLLECTOR_ADAPTER_PRESETS}
    whitelist = read_collector_whitelist()
    whitelist.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("allowed_at") or ""), reverse=True)
    return {
        "ok": True,
        "path": str(FOLO_COLLECTOR_ADAPTERS_PATH),
        "whitelist_path": str(FOLO_COLLECTOR_WHITELIST_PATH),
        "run_dir": str(FOLO_COLLECTOR_RUNS_DIR),
        "presets": list(platforms.values()),
        "safe_runners": sorted(SAFE_COLLECTOR_RUNNERS),
        "total": len(rows),
        "items": rows[:limit],
        "whitelist": whitelist[:limit],
        "runs": read_collector_runs(limit=20),
        "note": "这里只登记开源采集器候选，不自动运行未知仓库代码。",
    }


def discover_collector_adapters(platform: str, limit: int = 5) -> dict:
    selected = clean_resource_text(platform or "其它", 80)
    preset = next((item for item in COLLECTOR_ADAPTER_PRESETS if item["platform"] == selected), None)
    query = preset["query"] if preset else f"{selected} crawler rss github"
    candidates = discover_github_candidates(query, limit=limit)
    added = []
    for candidate in candidates:
        added.append(
            upsert_collector_adapter(
                {
                    "platform": selected,
                    "name": candidate.get("name"),
                    "repo_url": candidate.get("link"),
                    "source": candidate.get("source"),
                    "status": "候选",
                    "notes": candidate.get("notes") or f"query={query}",
                }
            )
        )
    return {**collector_adapter_summary(limit=80), "platform": selected, "query": query, "added": added}


def github_repo_from_url(repo_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(clean_resource_text(repo_url, 1000))
    if parsed.netloc.lower() != "github.com":
        raise HTTPException(status_code=400, detail="仅支持 GitHub 仓库 URL 审核")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="GitHub 仓库 URL 格式错误")
    return parts[0], parts[1]


def review_collector_adapter(fingerprint: str) -> dict:
    selected = clean_resource_text(fingerprint, 120)
    if not selected:
        raise HTTPException(status_code=400, detail="缺少采集器 fingerprint")
    with FOLO_COLLECTOR_ADAPTERS_LOCK:
        rows = read_collector_adapters()
        item = next((row for row in rows if row.get("fingerprint") == selected), None)
        if not item:
            raise HTTPException(status_code=404, detail="采集器候选不存在")
        owner, repo = github_repo_from_url(str(item.get("repo_url") or ""))
    repo_api = fetch_json(f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}")
    license_info = repo_api.get("license") or {}
    reviewed = {
        "github_full_name": repo_api.get("full_name") or f"{owner}/{repo}",
        "github_description": clean_resource_text(repo_api.get("description") or "", 500),
        "github_stars": repo_api.get("stargazers_count") or 0,
        "github_forks": repo_api.get("forks_count") or 0,
        "github_default_branch": repo_api.get("default_branch") or "",
        "github_license": license_info.get("spdx_id") or license_info.get("name") or "NOASSERTION",
        "github_pushed_at": repo_api.get("pushed_at") or "",
        "reviewed_at": resource_hive_now(),
        "allow_execute": False,
        "status": "reviewed-license-found" if license_info else "reviewed-license-missing",
        "review_note": "已完成 GitHub 元数据审核；默认不执行仓库代码，需另行加入白名单。",
    }
    with FOLO_COLLECTOR_ADAPTERS_LOCK:
        rows = read_collector_adapters()
        item = next((row for row in rows if row.get("fingerprint") == selected), None)
        if not item:
            raise HTTPException(status_code=404, detail="采集器候选不存在")
        item.update(reviewed)
        item["updated_at"] = reviewed["reviewed_at"]
        write_collector_adapters(rows)
    return {**collector_adapter_summary(limit=80), "item": item}


def allow_collector_adapter_execution(fingerprint: str, runner: str = "github-repo-metadata-snapshot") -> dict:
    selected = clean_resource_text(fingerprint, 120)
    selected_runner = clean_resource_text(runner, 120) or "github-repo-metadata-snapshot"
    if not selected:
        raise HTTPException(status_code=400, detail="缺少采集器 fingerprint")
    if selected_runner not in SAFE_COLLECTOR_RUNNERS:
        raise HTTPException(status_code=400, detail="runner 不在安全白名单中")
    with FOLO_COLLECTOR_ADAPTERS_LOCK:
        rows = read_collector_adapters()
        adapter = next((row for row in rows if row.get("fingerprint") == selected), None)
    if not adapter:
        raise HTTPException(status_code=404, detail="采集器候选不存在")
    if not str(adapter.get("status") or "").startswith("reviewed-"):
        raise HTTPException(status_code=400, detail="请先完成仓库审核，再加入执行白名单")
    license_name = str(adapter.get("github_license") or "")
    if not license_name or license_name == "NOASSERTION":
        raise HTTPException(status_code=400, detail="缺少明确 License，不能加入执行白名单")
    github_repo_from_url(str(adapter.get("repo_url") or ""))
    now = resource_hive_now()
    whitelist_item = {
        "fingerprint": selected,
        "platform": adapter.get("platform") or "其它",
        "name": adapter.get("name") or adapter.get("github_full_name") or "未命名采集器",
        "repo_url": adapter.get("repo_url") or "",
        "github_full_name": adapter.get("github_full_name") or "",
        "github_license": license_name,
        "runner": selected_runner,
        "allow_execute": True,
        "execution_scope": "builtin-runner-only",
        "sandbox_root": str(FOLO_COLLECTOR_RUNS_DIR / selected),
        "allowed_at": now,
        "updated_at": now,
        "note": "仅允许调用内置安全 runner，不执行仓库源码或任意 shell 命令。",
    }
    with FOLO_COLLECTOR_WHITELIST_LOCK:
        rows = read_collector_whitelist()
        current = next((row for row in rows if row.get("fingerprint") == selected), None)
        if current:
            current.update(whitelist_item)
            item = current
        else:
            item = whitelist_item
            rows.append(item)
        rows.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("allowed_at") or ""), reverse=True)
        write_collector_whitelist(rows)
    return {**collector_adapter_summary(limit=80), "allowed": item}


def run_collector_adapter_execution(fingerprint: str) -> dict:
    selected = clean_resource_text(fingerprint, 120)
    if not selected:
        raise HTTPException(status_code=400, detail="缺少采集器 fingerprint")
    with FOLO_COLLECTOR_WHITELIST_LOCK:
        whitelist_rows = read_collector_whitelist()
        whitelist_item = next((row for row in whitelist_rows if row.get("fingerprint") == selected), None)
    if not whitelist_item:
        raise HTTPException(status_code=403, detail="采集器未加入执行白名单")
    runner = str(whitelist_item.get("runner") or "")
    if runner not in SAFE_COLLECTOR_RUNNERS:
        raise HTTPException(status_code=400, detail="runner 不在安全白名单中")
    owner, repo = github_repo_from_url(str(whitelist_item.get("repo_url") or ""))
    started_at = resource_hive_now()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir = FOLO_COLLECTOR_RUNS_DIR / selected / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    repo_api = fetch_json(f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}")
    license_info = repo_api.get("license") or {}
    collected = [
        {
            "platform": whitelist_item.get("platform") or "GitHub",
            "name": repo_api.get("full_name") or whitelist_item.get("name") or f"{owner}/{repo}",
            "url": repo_api.get("html_url") or whitelist_item.get("repo_url") or "",
            "score": 72,
            "source": f"collector-whitelist:{runner}",
            "summary": clean_resource_text(repo_api.get("description") or "", 500),
            "license": license_info.get("spdx_id") or license_info.get("name") or whitelist_item.get("github_license") or "",
        }
    ]
    manual_entry = upsert_manual_hive_entry(collected[0])
    finished_at = resource_hive_now()
    result = {
        "ok": True,
        "run_id": run_id,
        "fingerprint": selected,
        "runner": runner,
        "execution_scope": "builtin-runner-only",
        "sandbox_dir": str(run_dir),
        "started_at": started_at,
        "finished_at": finished_at,
        "collected_count": len(collected),
        "items": collected,
        "manual_entry": manual_entry,
        "note": "已在隔离运行目录写入采集结果；本次未执行仓库源码。",
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with FOLO_COLLECTOR_WHITELIST_LOCK:
        rows = read_collector_whitelist()
        current = next((row for row in rows if row.get("fingerprint") == selected), None)
        if current:
            current["last_run_at"] = finished_at
            current["last_run_id"] = run_id
            current["last_collected_count"] = len(collected)
            current["updated_at"] = finished_at
            write_collector_whitelist(rows)
    return {**collector_adapter_summary(limit=80), "run": result, "manual_entries": manual_hive_summary(limit=80)}


def discover_archive_candidates(query: str, resource_type: str, limit: int = 8) -> list[dict]:
    params = [
        ("q", query),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "creator"),
        ("fl[]", "year"),
        ("rows", str(limit)),
        ("output", "json"),
    ]
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params)
    data = fetch_json(url)
    docs = (((data.get("response") or {}).get("docs")) or [])[:limit]
    rows = []
    for doc in docs:
        identifier = clean_resource_text(doc.get("identifier"), 240)
        title = clean_resource_text(doc.get("title"), 240)
        if not identifier or not title:
            continue
        creator = doc.get("creator")
        if isinstance(creator, list):
            creator_text = ", ".join(clean_resource_text(item, 80) for item in creator[:2])
        else:
            creator_text = clean_resource_text(creator or "", 120)
        year = clean_resource_text(doc.get("year") or "", 40)
        rows.append(
            {
                "id": f"archive-{identifier}",
                "type": resource_type,
                "name": f"{title}{f' - {creator_text}' if creator_text else ''}{f' ({year})' if year else ''}",
                "link": f"https://archive.org/details/{urllib.parse.quote(identifier)}",
                "source": "internet-archive-api",
                "status": "discovered",
                "notes": f"query={query}",
            }
        )
    return rows


def parse_duckduckgo_results(page_html: str) -> list[dict]:
    parser = DuckDuckGoResultParser()
    parser.feed(page_html)
    raw_results = list(parser.results)
    if not raw_results:
        for href, title_html in re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page_html, flags=re.I | re.S):
            title = re.sub(r"<[^>]+>", " ", html_tools.unescape(title_html))
            raw_results.append({"title": title, "href": html_tools.unescape(href)})
    return raw_results


def parse_bing_results(page_html: str) -> list[dict]:
    raw_results: list[dict] = []
    blocks = re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>.*?</li>', page_html, flags=re.I | re.S)
    if not blocks:
        blocks = [page_html]
    for block in blocks:
        for href, title_html in re.findall(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S):
            title = re.sub(r"<[^>]+>", " ", html_tools.unescape(title_html))
            raw_results.append({"title": title, "href": html_tools.unescape(href)})
    return raw_results


def discover_resource_candidates(query: str, resource_type: str = "其它资源", limit: int = 8) -> dict:
    cleaned_query = clean_resource_text(query, 160)
    if not cleaned_query:
        raise HTTPException(status_code=400, detail="请输入资源搜索关键词")
    selected_type = clean_resource_text(resource_type or "其它资源", 80)
    api_errors = []
    try:
        api_rows = []
        api_provider = ""
        if selected_type == "书籍":
            api_rows = discover_openlibrary_candidates(cleaned_query, limit=limit)
            api_provider = "openlibrary-api"
        elif selected_type == "软件包":
            api_rows = discover_github_candidates(cleaned_query, limit=limit)
            api_provider = "github-search-api"
        elif selected_type in {"解密档案", "题库"}:
            api_rows = discover_archive_candidates(cleaned_query, selected_type, limit=limit)
            api_provider = "internet-archive-api"
        if api_rows:
            return {
                "ok": True,
                "query": cleaned_query,
                "resource_type": selected_type,
                "search_query": cleaned_query,
                "provider": api_provider,
                "items": api_rows[:limit],
                "count": len(api_rows[:limit]),
                "searched_at": resource_hive_now(),
                "errors": [],
                "note": "优先使用公开 API 候选发现，不自动下载文件，也不判断版权可用性。",
            }
    except Exception as exc:
        api_errors.append(f"{selected_type}-api: {exc}")
    search_query = resource_discovery_query(cleaned_query, selected_type)
    providers = [
        (
            "duckduckgo-html",
            "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": search_query}),
            parse_duckduckgo_results,
        ),
        (
            "bing-html",
            "https://www.bing.com/search?" + urllib.parse.urlencode({"q": search_query}),
            parse_bing_results,
        ),
    ]
    raw_results: list[dict] = []
    provider = ""
    errors = api_errors
    for provider_name, url, parser in providers:
        try:
            raw_results = parser(fetch_search_html(url))
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
            raw_results = []
        if raw_results:
            provider = provider_name
            break
    if not provider:
        provider = providers[-1][0]
    rows = []
    seen: set[str] = set()
    for result in raw_results:
        title = clean_resource_text(result.get("title"), 300)
        raw_href = result.get("href", "")
        link = decode_bing_href(raw_href) if provider == "bing-html" else decode_duckduckgo_href(raw_href)
        link = clean_resource_text(link, 1000)
        if not title or not link:
            continue
        fingerprint = hashlib.sha256(f"{selected_type}|{title.lower()}|{link.lower()}".encode("utf-8")).hexdigest()[:20]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        rows.append(
            {
                "id": f"candidate-{fingerprint}",
                "type": selected_type,
                "name": title,
                "link": link,
                "source": provider,
                "status": "discovered",
                "notes": f"query={cleaned_query}",
            }
        )
        if len(rows) >= limit:
            break
    return {
        "ok": True,
        "query": cleaned_query,
        "resource_type": selected_type,
        "search_query": search_query,
        "provider": provider,
        "items": rows,
        "count": len(rows),
        "searched_at": resource_hive_now(),
        "errors": errors,
        "note": "这里只做公开网页候选发现，不自动下载文件，也不判断版权可用性。",
    }


RESOURCE_HIVE_PRESET_QUERIES = [
    {"type": "书籍", "query": "artificial intelligence"},
    {"type": "解密档案", "query": "declassified technology policy"},
    {"type": "题库", "query": "exam questions electrical engineering"},
    {"type": "软件包", "query": "open source agent framework GitHub release documentation"},
]


def normalize_resource_discovery_queries(payload: dict) -> list[dict]:
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raw_queries = RESOURCE_HIVE_PRESET_QUERIES
    rows = []
    for item in raw_queries[:8]:
        if isinstance(item, str):
            rows.append({"query": clean_resource_text(item, 160), "type": "其它资源"})
        elif isinstance(item, dict):
            rows.append(
                {
                    "query": clean_resource_text(item.get("query") or item.get("q") or "", 160),
                    "type": clean_resource_text(item.get("type") or item.get("resource_type") or "其它资源", 80),
                }
            )
    return [item for item in rows if item["query"]]


def discover_resource_batch(payload: dict) -> dict:
    queries = normalize_resource_discovery_queries(payload)
    try:
        limit_per_query = int(payload.get("limit_per_query") or 2)
    except Exception:
        limit_per_query = 2
    limit_per_query = max(1, min(limit_per_query, 5))
    auto_add = bool(payload.get("auto_add"))
    items: list[dict] = []
    added: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        try:
            data = discover_resource_candidates(query["query"], query["type"], limit=limit_per_query)
        except Exception as exc:
            errors.append({"query": query["query"], "type": query["type"], "error": str(exc)})
            continue
        for candidate in data.get("items", []):
            fingerprint = resource_hive_fingerprint(candidate)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(candidate)
            if auto_add:
                added.append(upsert_resource_hive_entry(candidate))
    result = {
        "ok": True,
        "queries": queries,
        "count": len(items),
        "items": items,
        "added": added,
        "errors": errors,
        "searched_at": resource_hive_now(),
        "note": "批量预设巡检只记录公开网页候选，不自动下载文件，不判断版权可用性。",
    }
    if auto_add:
        result["resource_hive"] = resource_hive_summary(limit=120)
    return result


def session_digest(value: str) -> str:
    token_scope = web_access_token() or "no-access-token"
    return hashlib.sha256(f"inforadar-session:v3:{token_scope}:{value}".encode("utf-8")).hexdigest()


def tab_nonce_digest(value: str) -> str:
    token_scope = web_access_token() or "no-access-token"
    return hashlib.sha256(f"inforadar-tab:v1:{token_scope}:{value}".encode("utf-8")).hexdigest()


def load_session_store_unlocked() -> dict:
    if SESSION_STORE_PATH.exists():
        try:
            data = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                sessions = data.get("sessions")
                if isinstance(sessions, dict):
                    return {"sessions": sessions}
        except Exception:
            pass
    return {"sessions": {}}


def save_session_store_unlocked(data: dict) -> None:
    SESSION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SESSION_STORE_PATH.with_suffix(f"{SESSION_STORE_PATH.suffix}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SESSION_STORE_PATH)


def prune_session_store_unlocked(data: dict, now: float | None = None) -> bool:
    current = now or time.time()
    sessions = data.setdefault("sessions", {})
    expired = [key for key, item in sessions.items() if float(item.get("expires_at") or 0) <= current]
    for key in expired:
        sessions.pop(key, None)
    return bool(expired)


def create_web_session() -> tuple[str, str, float]:
    session_id = secrets.token_urlsafe(32)
    tab_nonce = secrets.token_urlsafe(24)
    now = time.time()
    expires_at = now + SESSION_MAX_AGE
    with SESSION_LOCK:
        data = load_session_store_unlocked()
        prune_session_store_unlocked(data, now)
        data.setdefault("sessions", {})[session_digest(session_id)] = {
            "created_at": now,
            "last_seen": now,
            "expires_at": expires_at,
            "tab_nonce_hash": tab_nonce_digest(tab_nonce),
        }
        save_session_store_unlocked(data)
    return session_id, tab_nonce, expires_at


def verify_web_session(request: Request) -> bool:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id:
        return False
    session_key = session_digest(session_id)
    now = time.time()
    with SESSION_LOCK:
        data = load_session_store_unlocked()
        changed = prune_session_store_unlocked(data, now)
        item = data.setdefault("sessions", {}).get(session_key)
        if not item:
            if changed:
                save_session_store_unlocked(data)
            return False
        item["last_seen"] = now
        save_session_store_unlocked(data)
    return True


def revoke_web_session(request: Request) -> None:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if not session_id:
        return
    session_key = session_digest(session_id)
    with SESSION_LOCK:
        data = load_session_store_unlocked()
        sessions = data.setdefault("sessions", {})
        if session_key in sessions:
            sessions.pop(session_key, None)
            save_session_store_unlocked(data)


def totp_code(secret: str, timestamp: float | None = None, step: int = 30, digits: int = 6) -> str:
    cleaned = secret.replace(" ", "").upper()
    padded = cleaned + "=" * ((8 - len(cleaned) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((timestamp or time.time()) // step).to_bytes(8, "big")
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def verify_totp(code: str, secret: str) -> bool:
    submitted = re.sub(r"\D", "", str(code or ""))
    if len(submitted) != 6 or not secret:
        return False
    now = time.time()
    try:
        return any(hmac.compare_digest(submitted, totp_code(secret, now + offset)) for offset in (-30, 0, 30))
    except Exception:
        return False


def agenthub_root() -> Path | None:
    configured = os.environ.get("AGENTHUB_DIR", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend([ROOT.parent / "NASAgentHub", ROOT.parent / "AgentHub", Path("/home/mana/NASAgentHub"), Path("/home/mana/AgentHub")])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def agenthub_queue_token() -> str:
    return (
        os.environ.get("AGENTHUB_QUEUE_TOKEN", "").strip()
        or os.environ.get("OPENCLAW_AGENTHUB_QUEUE_TOKEN", "").strip()
        or runtime_env_value("AGENTHUB_QUEUE_TOKEN")
        or runtime_env_value("OPENCLAW_AGENTHUB_QUEUE_TOKEN")
        or folo_link_token()
        or web_access_token()
    )


def require_agenthub_queue_access(request: Request) -> None:
    if has_access(request):
        return
    token = agenthub_queue_token()
    if not token:
        raise HTTPException(status_code=403, detail="未配置 AGENTHUB_QUEUE_TOKEN，拒绝接收队列请求")
    submitted = (
        request.headers.get("x-agenthub-token", "")
        or request.headers.get("x-inforadar-token", "")
        or request.query_params.get("token", "")
        or request.query_params.get("access_token", "")
    ).strip()
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        submitted = auth[7:].strip()
    if submitted and hmac.compare_digest(submitted, token):
        return
    raise HTTPException(status_code=401, detail="AgentHub 队列口令错误")


def read_agenthub_json(root: Path, relative_path: str) -> dict:
    path = root / relative_path
    if not path.exists():
        return {"version": "1.0", "updated_at": "", "items": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_agenthub_queue(args: list[str], timeout: int = 20) -> dict | list:
    root = agenthub_root()
    if root is None:
        raise HTTPException(status_code=404, detail="AgentHub 目录不存在")
    script = root / "shared" / "common_scripts" / "agent_command_queue.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="AgentHub 队列脚本不存在")
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(root),
        env=os.environ.copy(),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = sanitize_log_text(proc.stdout or "", max_chars=12000)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=output or f"队列命令失败：{proc.returncode}")
    try:
        return json.loads(output)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"队列返回无法解析：{output}") from exc


def run_status_command(args: list[str], timeout: int = 4) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def run_status_command_with_input(args: list[str], input_text: str, timeout: int = 4) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            input=input_text,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def listening_on(lines: list[str], port: int) -> bool:
    marker = f":{port}"
    return any(marker in line for line in lines)


def sanitize_log_text(text: str, max_chars: int = 6000) -> str:
    clipped = text[-max_chars:]
    clipped = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", clipped)
    clipped = re.sub(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", "[device-code-redacted]", clipped)
    clipped = re.sub(r"sk-[A-Za-z0-9_\-]{16,}", "[api-key-redacted]", clipped)
    clipped = re.sub(r"https://auth\.openai\.com/[^\s]+", "[openai-auth-url-redacted]", clipped)
    return clipped


def tail_file(path: Path, max_lines: int = 80) -> dict:
    if not path.exists():
        return {"name": path.name, "path": str(path), "exists": False, "lines": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception as exc:
        return {"name": path.name, "path": str(path), "exists": True, "error": str(exc), "lines": []}
    return {
        "name": path.name,
        "path": str(path),
        "exists": True,
        "lines": sanitize_log_text("\n".join(lines)).splitlines(),
    }


def normalize_codex_session(session: str | None) -> str:
    selected = str(session or "codex").strip()
    if selected not in CODEX_SESSION_SLOTS:
        raise HTTPException(status_code=400, detail="不允许的 Codex 会话")
    return selected


def tmux_session_exists(session: str) -> bool:
    code, _ = run_status_command(["tmux", "has-session", "-t", session], timeout=3)
    return code == 0


def ensure_codex_tmux_session(session: str) -> None:
    if tmux_session_exists(session):
        return
    run_codex = str(Path.home() / "bin" / "run-codex")
    code, out = run_status_command(["tmux", "new-session", "-d", "-s", session, run_codex], timeout=8)
    if code != 0:
        raise HTTPException(status_code=503, detail=out or f"无法启动 {session}")


def tmux_capture(session: str, max_lines: int = 80) -> dict:
    code, out = run_status_command(["tmux", "capture-pane", "-pt", session, "-S", f"-{max_lines}"], timeout=4)
    return {
        "name": f"tmux:{session}",
        "path": f"tmux://{session}",
        "exists": code == 0,
        "lines": sanitize_log_text(out).splitlines() if code == 0 else [],
        "error": "" if code == 0 else out,
    }


def codex_terminal_payload(session: str = "codex", max_lines: int = 120, start: bool = False) -> dict:
    selected = normalize_codex_session(session)
    return codex_web_chat_payload(selected)


def codex_web_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def codex_web_session_dir(session: str) -> Path:
    selected = normalize_codex_session(session)
    return CODEX_WEB_CHAT_DIR / selected


def codex_web_log_path(session: str) -> Path:
    return codex_web_session_dir(session) / "messages.jsonl"


def codex_exec_env() -> dict:
    env = os.environ.copy()
    extra_path = [
        str(Path.home() / ".local" / "node" / "bin"),
        str(Path.home() / ".local" / "npm-global" / "bin"),
        str(Path.home() / "bin"),
    ]
    env["PATH"] = ":".join(extra_path + [env.get("PATH", "")])
    return env


def codex_exec_command(output_path: Path) -> list[str]:
    codex_bin = Path.home() / ".local" / "npm-global" / "bin" / "codex"
    command = [
        str(codex_bin),
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(CODEX_WEB_WORKDIR if CODEX_WEB_WORKDIR.exists() else Path.home()),
        "-s",
        "workspace-write",
        "--output-last-message",
        str(output_path),
        "-",
    ]
    return command


def read_codex_web_entries(session: str, limit: int = 80) -> list[dict]:
    path = codex_web_log_path(session)
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except Exception:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def format_codex_web_cache_lines(session: str, entries: list[dict], job: dict | None = None) -> list[str]:
    selected = normalize_codex_session(session)
    path = codex_web_log_path(selected)
    lines = [
        f"Codex 聊天缓存 · {selected}",
        f"path: {path}",
        f"entries: {len(entries)}",
        f"updated: {codex_web_now()}",
        "",
    ]
    if not entries and not job:
        lines.append("当前会话还没有聊天记录。发送第一条消息后，这里会实时写入缓存。")
        return lines

    for entry in entries:
        role = entry.get("role", "")
        label = "USER" if role == "user" else "CODEX" if role == "assistant" else "SYSTEM"
        at = str(entry.get("at", ""))[:19].replace("T", " ")
        job_id = str(entry.get("job_id") or "")
        text = sanitize_log_text(str(entry.get("text", "")), max_chars=12000)
        lines.append(f"[{at}] {label}{f' job={job_id}' if job_id else ''}")
        lines.extend(text.splitlines() or [""])
        lines.append("")

    if job and job.get("status") in {"queued", "running"}:
        lines.append(f"[{str(job.get('started_at', ''))[:19].replace('T', ' ')}] JOB {job.get('status')} id={job.get('id', '')}")
        lines.extend(sanitize_log_text(str(job.get("output") or "等待 Codex 返回..."), max_chars=12000).splitlines())
    return lines


def codex_web_cache_log_payload(
    session: str,
    entries: list[dict] | None = None,
    job: dict | None = None,
    job_id: str | None = None,
    limit: int = 120,
) -> dict:
    selected = normalize_codex_session(session)
    resolved_entries = entries if entries is not None else read_codex_web_entries(selected, limit=limit)
    resolved_job = job if job is not None else active_codex_web_job(selected, job_id=job_id)
    path = codex_web_log_path(selected)
    return {
        "name": f"聊天缓存:{selected}",
        "path": str(path),
        "exists": True,
        "is_chat_cache": True,
        "session": selected,
        "entry_count": len(resolved_entries),
        "lines": format_codex_web_cache_lines(selected, resolved_entries, resolved_job),
        "export_markdown": f"/api/codex-terminal/export?session={selected}&format=md",
        "export_jsonl": f"/api/codex-terminal/export?session={selected}&format=jsonl",
    }


def codex_web_export_markdown(session: str) -> str:
    selected = normalize_codex_session(session)
    entries = read_codex_web_entries(selected, limit=10000)
    lines = [
        f"# Codex 浏览器会话导出 - {selected}",
        "",
        f"- 导出时间：{codex_web_now()}",
        f"- 缓存文件：`{codex_web_log_path(selected)}`",
        f"- 消息条数：{len(entries)}",
        "",
    ]
    if not entries:
        lines.append("> 当前会话暂无聊天记录。")
        return "\n".join(lines)
    for entry in entries:
        role = entry.get("role", "")
        label = "你" if role == "user" else "Codex" if role == "assistant" else "系统"
        at = str(entry.get("at", ""))[:19].replace("T", " ")
        job_id = str(entry.get("job_id") or "")
        text = sanitize_log_text(str(entry.get("text", "")), max_chars=50000)
        lines.extend([f"## {label} · {at}", ""])
        if job_id:
            lines.extend([f"`job_id: {job_id}`", ""])
        lines.extend([text or "(空)", ""])
    return "\n".join(lines).rstrip() + "\n"


def append_codex_web_entry(session: str, entry: dict) -> None:
    selected = normalize_codex_session(session)
    directory = codex_web_session_dir(selected)
    directory.mkdir(parents=True, exist_ok=True)
    data = {**entry, "session": selected, "at": entry.get("at") or codex_web_now()}
    with CODEX_WEB_LOCK:
        with codex_web_log_path(selected).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def active_codex_web_job(session: str, job_id: str | None = None) -> dict | None:
    selected = normalize_codex_session(session)
    with CODEX_WEB_LOCK:
        if job_id:
            job = CODEX_WEB_JOBS.get(job_id)
            return dict(job) if job and job.get("session") == selected else None
        jobs = [job for job in CODEX_WEB_JOBS.values() if job.get("session") == selected and job.get("status") in {"queued", "running"}]
        if not jobs:
            return None
        jobs.sort(key=lambda item: str(item.get("started_at", "")), reverse=True)
        return dict(jobs[0])


def format_codex_web_transcript(entries: list[dict], job: dict | None = None) -> str:
    lines = [f"Codex 浏览器直连会话 · {job.get('session') if job else 'ready'}"]
    if not entries and not job:
        lines.append("\n现在可以直接在下方输入消息。Enter 发送，Shift+Enter 换行。")
        lines.append("这条路径使用 codex exec 后台任务，不再把 tmux 读屏当作聊天窗口。")
    for entry in entries:
        role = entry.get("role", "")
        label = "你" if role == "user" else "Codex" if role == "assistant" else "系统"
        text = sanitize_log_text(str(entry.get("text", "")), max_chars=12000)
        at = str(entry.get("at", ""))[:19].replace("T", " ")
        if text:
            lines.append(f"\n[{at}] {label}\n{text}")
    if job and job.get("status") in {"queued", "running"}:
        output = sanitize_log_text(str(job.get("output", "")), max_chars=12000)
        running_text = output or "Codex 任务已启动，正在等待模型返回..."
        lines.append(f"\n[{str(job.get('started_at', ''))[:19].replace('T', ' ')}] Codex 正在回复\n{running_text}")
    return "\n".join(lines).strip()


def codex_web_chat_payload(session: str = "codex", job_id: str | None = None) -> dict:
    selected = normalize_codex_session(session)
    job = active_codex_web_job(selected, job_id=job_id)
    entries = read_codex_web_entries(selected)
    job_status = str(job.get("status", "")) if job else ""
    return {
        "ok": True,
        "session": selected,
        "source": "codex-exec-web",
        "pane_command": "codex exec",
        "output": format_codex_web_transcript(entries, job),
        "has_history": bool(entries),
        "job_id": job.get("id") if job else job_id or "",
        "job_status": job_status,
        "cache_log": codex_web_cache_log_payload(selected, entries=entries, job=job, job_id=job_id),
        "checked_at": codex_web_now(),
    }


def run_codex_web_job(job_id: str, session: str, message: str) -> None:
    selected = normalize_codex_session(session)
    output_file = Path(tempfile.gettempdir()) / f"inforadar-codex-{job_id}.txt"
    workdir = CODEX_WEB_WORKDIR if CODEX_WEB_WORKDIR.exists() else Path.home()
    started = codex_web_now()
    with CODEX_WEB_LOCK:
        if job_id in CODEX_WEB_JOBS:
            CODEX_WEB_JOBS[job_id].update({"status": "running", "started_at": started, "output": "Codex 进程已启动..."})
    try:
        proc = subprocess.run(
            codex_exec_command(output_file),
            input=message,
            cwd=str(workdir),
            env=codex_exec_env(),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CODEX_WEB_EXEC_TIMEOUT,
        )
        stdout = sanitize_log_text(proc.stdout or "", max_chars=12000)
        final_text = ""
        if output_file.exists():
            final_text = output_file.read_text(encoding="utf-8", errors="replace").strip()
        final_text = sanitize_log_text(final_text or stdout or "Codex 已结束，但没有返回可显示内容。", max_chars=12000)
        status = "done" if proc.returncode == 0 else "error"
        if status == "error":
            final_text = f"Codex 执行失败，退出码 {proc.returncode}。\n\n{final_text}"
        append_codex_web_entry(selected, {"role": "assistant", "text": final_text, "job_id": job_id})
        with CODEX_WEB_LOCK:
            CODEX_WEB_JOBS[job_id].update({"status": status, "output": final_text, "finished_at": codex_web_now(), "returncode": proc.returncode})
    except subprocess.TimeoutExpired as exc:
        output = sanitize_log_text(str(exc.output or exc), max_chars=12000)
        final_text = f"Codex 执行超时，已停止等待。\n\n{output}".strip()
        append_codex_web_entry(selected, {"role": "assistant", "text": final_text, "job_id": job_id})
        with CODEX_WEB_LOCK:
            CODEX_WEB_JOBS[job_id].update({"status": "timeout", "output": final_text, "finished_at": codex_web_now()})
    except Exception as exc:
        final_text = f"Codex 执行异常：{exc}"
        append_codex_web_entry(selected, {"role": "assistant", "text": final_text, "job_id": job_id})
        with CODEX_WEB_LOCK:
            CODEX_WEB_JOBS[job_id].update({"status": "error", "output": final_text, "finished_at": codex_web_now()})
    finally:
        try:
            output_file.unlink(missing_ok=True)
        except Exception:
            pass


def send_to_codex_web(message: str, session: str = "codex") -> dict:
    selected = normalize_codex_session(session)
    text = str(message or "").replace("\x00", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if len(text) > 12000:
        raise HTTPException(status_code=413, detail="消息过长，最多 12000 字符")

    job_id = uuid.uuid4().hex[:16]
    now = codex_web_now()
    append_codex_web_entry(selected, {"role": "user", "text": text, "job_id": job_id, "at": now})
    with CODEX_WEB_LOCK:
        CODEX_WEB_JOBS[job_id] = {"id": job_id, "session": selected, "status": "queued", "message": text, "output": "", "started_at": now}
    thread = threading.Thread(target=run_codex_web_job, args=(job_id, selected, text), daemon=True)
    thread.start()
    return codex_web_chat_payload(selected, job_id=job_id)


def send_to_codex_tmux(message: str, session: str = "codex") -> dict:
    selected = normalize_codex_session(session)
    text = str(message or "").replace("\x00", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")
    if len(text) > 4000:
        raise HTTPException(status_code=413, detail="消息过长，最多 4000 字符")

    ensure_codex_tmux_session(selected)

    # Clear any draft text that Codex TUI may leave in the prompt before pasting a new browser message.
    code, out = run_status_command(["tmux", "send-keys", "-t", selected, "C-u"], timeout=4)
    if code != 0:
        raise HTTPException(status_code=500, detail=out or "清空 codex 输入行失败")

    code, out = run_status_command_with_input(["tmux", "load-buffer", "-"], text, timeout=4)
    if code != 0:
        raise HTTPException(status_code=500, detail=out or "写入 tmux buffer 失败")
    code, out = run_status_command(["tmux", "paste-buffer", "-t", selected], timeout=4)
    if code != 0:
        raise HTTPException(status_code=500, detail=out or "粘贴到 codex 会话失败")
    # Codex runs as a full-screen TUI; C-m is more reliable than the literal Enter key in tmux.
    code, out = run_status_command(["tmux", "send-keys", "-t", selected, "C-m"], timeout=4)
    if code != 0:
        raise HTTPException(status_code=500, detail=out or "发送 Enter 失败")
    return codex_terminal_payload(session=selected, max_lines=140)


def codex_thread_summaries() -> list[dict]:
    root = agenthub_root()
    if root is None:
        return []
    threads = read_agenthub_json(root, "coordination/CODEX_APP_THREADS.json")
    rows = []
    for item in threads.get("items", []):
        rows.append(
            {
                "agent_id": item.get("agent_id", ""),
                "status": item.get("status", ""),
                "title": item.get("title", "") or item.get("session_thread_name", ""),
                "preview": item.get("preview", ""),
                "thread_id": item.get("thread_id", ""),
                "updated_at": item.get("updated_at", ""),
                "cwd": item.get("cwd", ""),
                "privacy_mode": item.get("privacy_mode", threads.get("privacy_mode", "")),
            }
        )
    return rows


def codex_workstation_status() -> dict:
    _, host = run_status_command(["hostname"], timeout=3)
    _, ip_out = run_status_command(["hostname", "-I"], timeout=3)
    _, sessions_out = run_status_command(["tmux", "ls"], timeout=4)
    _, ports_out = run_status_command(["ss", "-lnt"], timeout=4)
    _, codex_proc_out = run_status_command(["pgrep", "-af", "codex"], timeout=4)
    _, ipv6_out = run_status_command(["sysctl", "-n", "net.ipv6.conf.all.disable_ipv6"], timeout=3)
    _, route_out = run_status_command(["ip", "-4", "route", "show", "default"], timeout=3)
    _, surfshark_out = run_status_command(["ip", "link", "show", "surfshark"], timeout=3)

    sessions = [line.split(":", 1)[0] for line in sessions_out.splitlines() if line.strip()]
    port_lines = [line for line in ports_out.splitlines() if line.strip()]
    ips = ip_out.split()
    tailscale_ip = next((ip for ip in ips if ip.startswith("100.")), "")
    lan_ip = next((ip for ip in ips if ip.startswith("192.168.")), "")
    codex_process_count = len([line for line in codex_proc_out.splitlines() if "codex" in line and "pgrep" not in line])
    ttyd_line = next((line for line in port_lines if ":7681" in line), "")

    checks = {
        "codex_tmux": "codex" in sessions,
        "codex_process": codex_process_count > 0,
        "project_hub": listening_on(port_lines, 8787),
        "web_terminal": listening_on(port_lines, 7681),
        "web_console": listening_on(port_lines, 9090),
        "inforadar_web": listening_on(port_lines, 8769),
        "ipv6_disabled": ipv6_out.strip() == "1",
        "surfshark_interface": "surfshark" in surfshark_out,
    }
    online_score = sum(1 for value in checks.values() if value)
    status = "online" if checks["codex_tmux"] and checks["codex_process"] else "partial"
    if not checks["codex_tmux"] and not checks["codex_process"]:
        status = "offline"
    known_slots = [
        {"id": "codex", "name": "主 Codex 会话", "role": "默认交互会话"},
        {"id": "codex-research", "name": "研究/资料会话", "role": "预留：资料检索和方案沉淀"},
        {"id": "codex-build", "name": "构建/部署会话", "role": "预留：构建、发布、服务维护"},
        {"id": "codex-qa", "name": "测试/日志会话", "role": "预留：验收、日志、回归检查"},
    ]
    session_cards = []
    for slot in known_slots:
        online = slot["id"] in sessions
        session_cards.append({**slot, "status": "online" if online else "reserved", "tmux_session": slot["id"]})
    for session in sessions:
        if not any(item["id"] == session for item in session_cards):
            session_cards.append({"id": session, "name": session, "role": "检测到的 tmux 会话", "status": "online", "tmux_session": session})

    home = Path.home()
    logs = [
        codex_web_cache_log_payload("codex"),
        tail_file(home / ".cache" / "codex-workstation" / "startup.log", max_lines=80),
        tmux_capture("codex", max_lines=80),
    ]

    return {
        "ok": True,
        "status": status,
        "status_label": "24h 会话在线" if status == "online" else ("部分服务在线" if status == "partial" else "未检测到 Codex 会话"),
        "host": host,
        "ips": ips,
        "lan_ip": lan_ip,
        "tailscale_ip": tailscale_ip,
        "tmux_sessions": sessions,
        "session_cards": session_cards,
        "codex_threads": codex_thread_summaries(),
        "logs": logs,
        "codex_process_count": codex_process_count,
        "checks": checks,
        "online_score": online_score,
        "web_terminal_bind": ttyd_line,
        "project_hub_url": f"http://{lan_ip or '192.168.1.163'}:8787",
        "web_console_url": f"https://{lan_ip or '192.168.1.163'}:9090",
        "tailscale_terminal_url": f"http://{tailscale_ip}:7681" if tailscale_ip else "",
        "start_command": "NODE_OPTIONS=--dns-result-order=ipv4first codex",
        "tmux_command": "tmux attach -t codex",
        "default_route": route_out,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_agent_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def merge_agent_realtime_status(agents: list[dict], heartbeats: dict) -> list[dict]:
    heartbeat_items = {item.get("agent_id"): item for item in heartbeats.get("items", []) if item.get("agent_id")}
    now = datetime.now(timezone.utc)
    max_age_seconds = int(os.environ.get("AGENTHUB_HEARTBEAT_MAX_AGE_SECONDS", "300"))
    merged = []
    for agent in agents:
        row = dict(agent)
        heartbeat = heartbeat_items.get(agent.get("agent_id")) or {}
        heartbeat_at = parse_agent_time(heartbeat.get("heartbeat_at") or heartbeat.get("last_seen_at"))
        age_seconds = int((now - heartbeat_at).total_seconds()) if heartbeat_at else None
        if heartbeat_at and age_seconds is not None and age_seconds <= max_age_seconds:
            realtime_state = "online"
            realtime_label = "实时在线"
        elif heartbeat_at:
            realtime_state = "stale"
            realtime_label = "心跳过期"
        else:
            realtime_state = "unverified"
            realtime_label = "未接入实时检查"
        row.update(
            {
                "declared_status": agent.get("status"),
                "heartbeat_at": heartbeat.get("heartbeat_at") or heartbeat.get("last_seen_at") or "",
                "heartbeat_age_seconds": age_seconds,
                "heartbeat_source": heartbeat.get("source") or "",
                "realtime_state": realtime_state,
                "realtime_label": realtime_label,
                "realtime_checked_at": now.isoformat(),
                "realtime_note": heartbeat.get("note") or "",
            }
        )
        merged.append(row)
    return merged


def merge_agent_codex_threads(agents: list[dict], codex_threads: dict) -> list[dict]:
    thread_items = {
        item.get("agent_id"): item
        for item in codex_threads.get("items", [])
        if item.get("agent_id")
    }
    merged = []
    for agent in agents:
        row = dict(agent)
        thread = thread_items.get(agent.get("agent_id")) or {}
        row["codex_thread"] = thread
        row["codex_thread_status"] = thread.get("status") or "not_connected"
        row["codex_thread_updated_at"] = thread.get("updated_at") or ""
        row["codex_thread_title"] = thread.get("session_thread_name") or thread.get("title") or ""
        row["codex_thread_preview"] = thread.get("preview") or thread.get("message") or ""
        merged.append(row)
    return merged


def read_agenthub_events(root: Path, limit: int = 200) -> list[dict]:
    path = root / "logs" / "EVENT_LOG.ndjson"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"level": "warn", "event": "parse_error", "message": line[:240]})
    return events[-limit:]


def list_agent_outputs(root: Path, agent_id: str, limit: int = 20) -> list[dict]:
    output_dir = root / "agents" / agent_id / "output"
    if not output_dir.exists():
        return []
    rows = []
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        stat = path.stat()
        rows.append(
            {
                "name": path.name,
                "relative_path": str(path.relative_to(root)).replace("\\", "/"),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone().isoformat(timespec="seconds"),
            }
        )
    rows.sort(key=lambda item: item["modified_at"], reverse=True)
    return rows[:limit]


def enrich_agents_with_activity(root: Path, agents: list[dict], tasks: list[dict], events: list[dict]) -> list[dict]:
    enriched = []
    for agent in agents:
        agent_id = agent.get("agent_id", "")
        row = dict(agent)
        row["tasks"] = [task for task in tasks if task.get("owner_agent") == agent_id]
        row["events"] = [event for event in events if event.get("agent_id") == agent_id][-20:]
        row["outputs"] = list_agent_outputs(root, agent_id)
        enriched.append(row)
    return enriched


def request_is_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def has_access(request: Request) -> bool:
    token = web_access_token()
    if not token:
        return False
    return verify_web_session(request)


def require_access(request: Request) -> None:
    if has_access(request):
        return
    raise HTTPException(status_code=401, detail="未授权")


def require_folo_link_access(request: Request) -> None:
    token = folo_link_token() or web_access_token()
    if not token:
        raise HTTPException(status_code=403, detail="未配置 FOLO_LINK_TOKEN，拒绝接收外部回传")
    submitted = (
        request.headers.get("x-inforadar-token", "")
        or request.query_params.get("token", "")
        or request.query_params.get("access_token", "")
    ).strip()
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        submitted = auth[7:].strip()
    if submitted and hmac.compare_digest(submitted, token):
        return
    raise HTTPException(status_code=401, detail="Folo 回传口令错误")


@app.get("/api/health", response_model=HealthResponse)
def health() -> dict:
    return {"ok": True, "service": "InfoRadar Web"}


@app.get("/api/session")
def get_session(request: Request) -> dict:
    return {
        "ok": True,
        "protected": bool(web_access_token()),
        "totp_required": bool(web_totp_secret()),
        "session_max_age_seconds": SESSION_MAX_AGE,
        "tab_bound": False,
        "authenticated": has_access(request),
    }


@app.post("/api/session")
async def create_session(request: Request) -> JSONResponse:
    token = web_access_token()
    if not token:
        raise HTTPException(status_code=503, detail="服务端未配置 WEB_ACCESS_TOKEN，拒绝开放访问")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    submitted = str(payload.get("token") or payload.get("password") or "").strip()
    if not hmac.compare_digest(submitted, token):
        raise HTTPException(status_code=401, detail="口令错误")
    totp_secret = web_totp_secret()
    if totp_secret and not verify_totp(str(payload.get("totp") or payload.get("code") or ""), totp_secret):
        raise HTTPException(status_code=401, detail="动态码错误")
    session_id, tab_nonce, expires_at = create_web_session()
    response = JSONResponse(
        {
            "ok": True,
            "authenticated": True,
            "protected": True,
            "tab_nonce": tab_nonce,
            "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        }
    )
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=request_is_secure(request),
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/logout")
def logout(request: Request) -> JSONResponse:
    revoke_web_session(request)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/", secure=request_is_secure(request), httponly=True, samesite="lax")
    return response


@app.post("/api/command", response_model=CommandResponse, dependencies=[Depends(require_access)])
def run_command(payload: CommandRequest) -> dict:
    return run_inforadar_command(payload.command)


@app.get("/api/latest", dependencies=[Depends(require_access)])
def get_latest() -> dict:
    return latest_status()


@app.get("/api/items", dependencies=[Depends(require_access)])
def get_items(topic: str = "", limit: int = Query(default=40, ge=1, le=120)) -> dict:
    return latest_intel_items(topic, limit)


@app.get("/api/folo/article-links", dependencies=[Depends(require_access)])
def get_folo_article_links(limit: int = Query(default=80, ge=1, le=300)) -> dict:
    return folo_article_link_summary(limit)


@app.get("/api/folo/source-timeline", dependencies=[Depends(require_access)])
def get_folo_source_timeline(limit: int = Query(default=80, ge=1, le=300)) -> dict:
    return folo_timeline_summary(limit)


@app.post("/api/folo/source-timeline", dependencies=[Depends(require_access)])
async def post_folo_source_timeline(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    item = record_folo_timeline_click(payload)
    data = folo_timeline_summary(limit=80)
    return {**data, "item": item}


@app.get("/api/folo/manual-entries", dependencies=[Depends(require_access)])
def get_folo_manual_entries(limit: int = Query(default=80, ge=1, le=300)) -> dict:
    return manual_hive_summary(limit)


@app.post("/api/folo/manual-entries", dependencies=[Depends(require_access)])
async def post_folo_manual_entries(request: Request) -> dict:
    try:
        payload = await request.json()
        item = upsert_manual_hive_entry(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    data = manual_hive_summary(limit=80)
    return {**data, "item": item}


@app.delete("/api/folo/manual-entries", dependencies=[Depends(require_access)])
def delete_folo_manual_entries() -> dict:
    with FOLO_MANUAL_ENTRIES_LOCK:
        write_manual_hive_entries([])
    return manual_hive_summary(limit=80)


@app.post("/api/manual-hive/wechat/search", dependencies=[Depends(require_access)])
async def post_manual_hive_wechat_search(request: Request) -> dict:
    try:
        payload = await request.json()
        return search_wechat_accounts(str(payload.get("query") or payload.get("name") or ""), int(payload.get("limit") or 8))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公众号采集器不可用：{exc}") from exc


@app.post("/api/manual-hive/wechat/subscribe", dependencies=[Depends(require_access)])
async def post_manual_hive_wechat_subscribe(request: Request) -> dict:
    try:
        payload = await request.json()
        return subscribe_wechat_account(
            str(payload.get("fakeid") or ""),
            str(payload.get("nickname") or payload.get("name") or ""),
            bool(payload.get("poll", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公众号订阅失败：{exc}") from exc


@app.post("/api/manual-hive/wechat/folo-open", dependencies=[Depends(require_access)])
async def post_manual_hive_wechat_folo_open(request: Request) -> dict:
    try:
        payload = await request.json()
        return open_wechat_in_folo(
            request,
            str(payload.get("fakeid") or ""),
            str(payload.get("nickname") or payload.get("name") or ""),
            bool(payload.get("poll", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公众号 Folo 订阅打开失败：{exc}") from exc


@app.get("/api/manual-hive/wechat/rss", dependencies=[Depends(require_access)])
def get_manual_hive_wechat_rss(fakeid: str = Query(default="", min_length=1)) -> Response:
    try:
        fid = clean_resource_text(fakeid, 200)
        rss_text = wechat_api_text(wechat_internal_rss_path(fid), timeout=45)
        rss_text = rewrite_wechat_rss_self_url(rss_text, fid, wechat_rss_url(fid))
        return Response(content=rss_text, media_type="application/rss+xml; charset=utf-8")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公众号 RSS 打开失败：{exc}") from exc


@app.get("/api/folo/wechat-feed")
def get_folo_wechat_feed(request: Request, fakeid: str = Query(default="", min_length=1)) -> Response:
    try:
        fid = clean_resource_text(fakeid, 200)
        if fid not in wechat_subscription_fakeids():
            raise HTTPException(status_code=404, detail="该公众号尚未在 InfoRadar 订阅")
        rss_text = wechat_api_text(wechat_internal_rss_path(fid), timeout=45)
        rss_text = rewrite_wechat_rss_self_url(rss_text, fid, wechat_folo_feed_url(request, fid))
        return Response(content=rss_text, media_type="application/rss+xml; charset=utf-8")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Folo 公众号 Feed 打开失败：{exc}") from exc


@app.get("/api/manual-hive/wechat/rss-view", dependencies=[Depends(require_access)])
def get_manual_hive_wechat_rss_view(fakeid: str = Query(default="", min_length=1)) -> HTMLResponse:
    try:
        fid = clean_resource_text(fakeid, 200)
        rss_text = wechat_api_text(wechat_internal_rss_path(fid), timeout=45)
        return HTMLResponse(render_wechat_rss_view(fid, rss_text))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公众号文章列表打开失败：{exc}") from exc


@app.get("/api/folo/collector-adapters", dependencies=[Depends(require_access)])
def get_folo_collector_adapters(limit: int = Query(default=80, ge=1, le=300)) -> dict:
    return collector_adapter_summary(limit)


@app.post("/api/folo/collector-adapters/discover", dependencies=[Depends(require_access)])
async def post_folo_collector_adapters_discover(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    try:
        limit = int(payload.get("limit") or 5) if isinstance(payload, dict) else 5
    except Exception:
        limit = 5
    limit = max(1, min(limit, 10))
    platform = str(payload.get("platform") or "其它") if isinstance(payload, dict) else "其它"
    return discover_collector_adapters(platform, limit=limit)


@app.post("/api/folo/collector-adapters/review", dependencies=[Depends(require_access)])
async def post_folo_collector_adapters_review(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式错误")
    return review_collector_adapter(str(payload.get("fingerprint") or ""))


@app.post("/api/folo/collector-adapters/allow", dependencies=[Depends(require_access)])
async def post_folo_collector_adapters_allow(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式错误")
    return allow_collector_adapter_execution(
        str(payload.get("fingerprint") or ""),
        str(payload.get("runner") or "github-repo-metadata-snapshot"),
    )


@app.post("/api/folo/collector-adapters/run", dependencies=[Depends(require_access)])
async def post_folo_collector_adapters_run(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式错误")
    return run_collector_adapter_execution(str(payload.get("fingerprint") or ""))


@app.post("/api/folo/feed-probe", dependencies=[Depends(require_access)])
async def post_folo_feed_probe(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式错误")
    url = str(payload.get("url") or "").strip()
    try:
        limit = int(payload.get("limit") or 12)
    except Exception:
        limit = 12
    feed_xml = fetch_feed_xml(url)
    return parse_feed_xml(feed_xml, source_url=url, limit=max(1, min(limit, 30)))


@app.get("/api/folo/test-feed.xml")
def get_folo_test_feed(request: Request) -> Response:
    state = read_folo_test_feed_state()
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/") or f"{scheme}://{host}"
    item_url = f"{base_url}/api/folo/test-item/{state.get('id', 'initial')}"
    published = datetime.fromisoformat(str(state.get("created_at") or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>InfoRadar Folo Webhook Test</title>
    <link>{xml_escape(base_url)}</link>
    <description>InfoRadar test feed for Folo Actions Webhook verification</description>
    <lastBuildDate>{format_datetime(published)}</lastBuildDate>
    <item>
      <guid isPermaLink="false">{xml_escape(str(state.get("id") or "initial"))}</guid>
      <title>{xml_escape(str(state.get("title") or "InfoRadar Folo Webhook 测试条目"))}</title>
      <link>{xml_escape(item_url)}</link>
      <pubDate>{format_datetime(published)}</pubDate>
      <description>{xml_escape(str(state.get("summary") or ""))}</description>
    </item>
  </channel>
</rss>
"""
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/api/folo/test-item/{item_id}")
def get_folo_test_item(item_id: str) -> Response:
    state = read_folo_test_feed_state()
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{xml_escape(str(state.get("title") or "InfoRadar Folo Webhook 测试条目"))}</title>
</head>
<body>
  <h1>{xml_escape(str(state.get("title") or "InfoRadar Folo Webhook 测试条目"))}</h1>
  <p>{xml_escape(str(state.get("summary") or ""))}</p>
  <p>item_id: {xml_escape(item_id)}</p>
  <p>created_at: {xml_escape(str(state.get("created_at") or ""))}</p>
</body>
</html>
"""
    return Response(content=html, media_type="text/html; charset=utf-8")


@app.post("/api/folo/test-feed/bump", dependencies=[Depends(require_access)])
def bump_folo_test_feed() -> dict:
    state = write_folo_test_feed_state()
    return {"ok": True, "state": state, "feed_url": "/api/folo/test-feed.xml"}


@app.get("/api/folo/webhook-config", dependencies=[Depends(require_access)])
def get_folo_webhook_config(request: Request) -> dict:
    token = folo_link_token()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = forwarded_host or request.headers.get("host", "")
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme
    base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base_url and host:
        base_url = f"{scheme}://{host}"
    webhook_url = f"{base_url}/api/folo/article-link?token={token}" if base_url and token else ""
    links = folo_article_link_summary(5)
    return {
        "ok": True,
        "configured": bool(token),
        "webhook_url": webhook_url,
        "test_feed_url": f"{base_url}/api/folo/test-feed.xml" if base_url else "/api/folo/test-feed.xml",
        "target": f"{base_url}/api/folo/article-link" if base_url else "/api/folo/article-link",
        "article_link_count": links.get("count", 0),
        "recent_links": links.get("items", []),
        "required_fields": ["entry.id", "entry.feedId"],
        "note": "在 Folo Actions / Webhooks 中配置该 URL；回传 entry.id 与 entry.feedId 后，InfoRadar 会生成真实 Folo 原条链接。",
    }


def ingest_folo_payload(payload: dict) -> dict:
    try:
        record = append_folo_article_link(payload)
    except ValueError as exc:
        message = str(exc)
        if "feedId/entryId" not in message:
            raise HTTPException(status_code=400, detail=message) from exc
        try:
            signal = append_folo_article_signal(payload)
        except ValueError as signal_exc:
            raise HTTPException(status_code=400, detail=str(signal_exc)) from signal_exc
        return {"ok": True, "kind": "signal", "item": signal, "warning": message}
    return {"ok": True, "kind": "article_link", "item": record}


@app.get("/api/folo/article-link")
async def get_folo_article_link(request: Request) -> dict:
    require_folo_link_access(request)
    payload = dict(request.query_params)
    payload.pop("token", None)
    payload.pop("access_token", None)
    if not any(str(payload.get(key) or "").strip() for key in ("title", "url", "original_url", "entryId", "feedId")):
        return {"ok": True, "kind": "ping", "message": "Folo webhook endpoint is reachable. Use POST JSON or GET query fields to submit entry data."}
    return ingest_folo_payload(payload)


@app.post("/api/folo/article-link")
async def post_folo_article_link(request: Request) -> dict:
    require_folo_link_access(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    return ingest_folo_payload(payload)


@app.get("/api/files", dependencies=[Depends(require_access)])
def get_files(limit: int = Query(default=200, ge=1, le=500)) -> dict:
    return {"ok": True, "files": list_return_files(limit)}


@app.get("/api/file", dependencies=[Depends(require_access)])
def get_file(path: str, download: bool = False) -> FileResponse:
    try:
        file_path = safe_return_file(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    disposition = "attachment" if download else "inline"
    return FileResponse(str(file_path), filename=file_path.name, content_disposition_type=disposition)


@app.get("/api/manual-inbox", dependencies=[Depends(require_access)])
def get_manual_inbox() -> dict:
    return manual_inbox_summary()


@app.get("/api/watch", dependencies=[Depends(require_access)])
def get_watch() -> dict:
    return watch_summary()


@app.get("/api/source-pool", dependencies=[Depends(require_access)])
def get_source_pool() -> dict:
    return source_pool_summary()


@app.get("/api/resource-hive", dependencies=[Depends(require_access)])
def get_resource_hive(limit: int = Query(default=120, ge=1, le=500)) -> dict:
    return resource_hive_summary(limit)


@app.post("/api/resource-hive", dependencies=[Depends(require_access)])
async def post_resource_hive(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    item = upsert_resource_hive_entry(payload)
    data = resource_hive_summary(limit=120)
    return {**data, "item": item}


@app.post("/api/resource-hive/discover", dependencies=[Depends(require_access)])
async def post_resource_hive_discover(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    limit = int(payload.get("limit") or 8)
    limit = max(1, min(limit, 20))
    data = discover_resource_candidates(
        str(payload.get("query") or payload.get("q") or ""),
        str(payload.get("type") or payload.get("resource_type") or "其它资源"),
        limit=limit,
    )
    if payload.get("auto_add"):
        added = []
        for candidate in data["items"]:
            added.append(upsert_resource_hive_entry(candidate))
        data["added"] = added
        data["resource_hive"] = resource_hive_summary(limit=120)
    return data


@app.post("/api/resource-hive/discover-batch", dependencies=[Depends(require_access)])
async def post_resource_hive_discover_batch(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    return discover_resource_batch(payload if isinstance(payload, dict) else {})


@app.get("/api/resource-hive/export", dependencies=[Depends(require_access)])
def export_resource_hive(format: str = "md"):
    selected = str(format or "md").lower()
    if selected == "jsonl":
        if not RESOURCE_HIVE_PATH.exists():
            RESOURCE_HIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            RESOURCE_HIVE_PATH.write_text("", encoding="utf-8")
        return FileResponse(str(RESOURCE_HIVE_PATH), filename="inforadar_resource_hive.jsonl", media_type="application/x-ndjson")
    if selected not in {"md", "markdown"}:
        raise HTTPException(status_code=400, detail="仅支持 md 或 jsonl 导出")
    return Response(
        content=resource_hive_markdown(),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inforadar_resource_hive.md"'},
    )


@app.get("/api/resource-hive/archive-plan", dependencies=[Depends(require_access)])
def get_resource_hive_archive_plan(limit: int = Query(default=120, ge=1, le=500)) -> dict:
    return resource_hive_archive_plan(limit)


@app.post("/api/resource-hive/archive-links", dependencies=[Depends(require_access)])
def post_resource_hive_archive_links(limit: int = Query(default=120, ge=1, le=500)) -> dict:
    return resource_hive_archive_links(limit)


@app.post("/api/resource-hive/download-approval", dependencies=[Depends(require_access)])
async def post_resource_hive_download_approval(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求格式错误")
    return resource_hive_approve_download(str(payload.get("fingerprint") or ""))


@app.post("/api/resource-hive/download-approved", dependencies=[Depends(require_access)])
def post_resource_hive_download_approved(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return resource_hive_download_approved(limit)


@app.get("/api/codex-workstation", dependencies=[Depends(require_access)])
def get_codex_workstation() -> dict:
    return codex_workstation_status()


@app.get("/api/codex-terminal", dependencies=[Depends(require_access)])
def get_codex_terminal(
    session: str = Query(default="codex"),
    start: bool = Query(default=False),
    lines: int = Query(default=140, ge=40, le=320),
) -> dict:
    return codex_terminal_payload(session=session, max_lines=lines, start=start)


@app.post("/api/codex-terminal/send", dependencies=[Depends(require_access)])
async def post_codex_terminal(request: Request) -> dict:
    payload = await request.json()
    return send_to_codex_web(str(payload.get("message", "")), session=str(payload.get("session", "codex")))


@app.get("/api/codex-terminal/job/{job_id}", dependencies=[Depends(require_access)])
def get_codex_terminal_job(job_id: str, session: str = Query(default="codex")) -> dict:
    return codex_web_chat_payload(session=session, job_id=job_id)


@app.get("/api/search", dependencies=[Depends(require_access)])
def search(
    q: str = "",
    scope: str = "all",
    mode: str = "smart",
    limit: int = Query(default=30, ge=1, le=80),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return search_personal_radar(q, scope, limit, offset, mode)


@app.get("/api/agenthub", dependencies=[Depends(require_access)])
def get_agenthub() -> dict:
    root = agenthub_root()
    if root is None:
        return {"ok": False, "error": "AgentHub 目录不存在", "projects": [], "tasks": [], "agents": [], "locks": []}
    projects = read_agenthub_json(root, "coordination/PROJECT_REGISTRY.json")
    tasks = read_agenthub_json(root, "coordination/TASK_BOARD.json")
    agents = read_agenthub_json(root, "coordination/AGENT_STATUS.json")
    heartbeats = read_agenthub_json(root, "coordination/AGENT_HEARTBEATS.json")
    codex_threads = read_agenthub_json(root, "coordination/CODEX_APP_THREADS.json")
    locks = read_agenthub_json(root, "coordination/LOCKS.json")
    task_items = tasks.get("items", [])
    events = read_agenthub_events(root)
    realtime_agents = merge_agent_realtime_status(agents.get("items", []), heartbeats)
    codex_agents = merge_agent_codex_threads(realtime_agents, codex_threads)
    activity_agents = enrich_agents_with_activity(root, codex_agents, task_items, events)
    return {
        "ok": True,
        "root": str(root),
        "projects": projects.get("items", []),
        "tasks": task_items,
        "agents": activity_agents,
        "codex_threads": codex_threads.get("items", []),
        "codex_threads_updated_at": str(codex_threads.get("updated_at", "")),
        "codex_threads_privacy_mode": str(codex_threads.get("privacy_mode", "")),
        "events": events[-50:],
        "locks": locks.get("items", []),
        "heartbeat_max_age_seconds": int(os.environ.get("AGENTHUB_HEARTBEAT_MAX_AGE_SECONDS", "300")),
        "updated_at": max(
            [
                str(projects.get("updated_at", "")),
                str(tasks.get("updated_at", "")),
                str(agents.get("updated_at", "")),
                str(heartbeats.get("updated_at", "")),
                str(codex_threads.get("updated_at", "")),
                str(locks.get("updated_at", "")),
            ]
        ),
    }


def add_cli_arg(args: list[str], flag: str, value: object | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        args.extend([flag, text])


@app.post("/api/agenthub/commands/enqueue")
async def post_agenthub_command_enqueue(request: Request) -> dict:
    require_agenthub_queue_access(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    text = str(payload.get("text") or payload.get("raw_text") or payload.get("command") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="队列指令不能为空")
    args = [
        "enqueue",
        "--text",
        text,
        "--source",
        str(payload.get("source") or "openclaw-weixin"),
        "--policy",
        str(payload.get("policy") or payload.get("dispatchPolicy") or "queue"),
        "--target-runner",
        str(payload.get("target_runner") or payload.get("targetRunner") or "any"),
        "--created-by",
        str(payload.get("created_by") or payload.get("createdBy") or "openclaw"),
    ]
    add_cli_arg(args, "--external-id", payload.get("external_msg_id") or payload.get("externalMsgId") or payload.get("requestId"))
    add_cli_arg(args, "--dedupe-key", payload.get("dedupe_key") or payload.get("dedupeKey"))
    add_cli_arg(args, "--command-id", payload.get("command_id") or payload.get("commandId"))
    if payload.get("priority") is not None:
        add_cli_arg(args, "--priority", payload.get("priority"))
    item = run_agenthub_queue(args)
    return {"ok": True, "item": item}


@app.post("/api/agenthub/commands/claim")
async def post_agenthub_command_claim(request: Request) -> dict:
    require_agenthub_queue_access(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    runner_id = str(payload.get("runner_id") or payload.get("runnerId") or "").strip()
    runner_kind = str(payload.get("runner_kind") or payload.get("runnerKind") or "").strip()
    if not runner_id or runner_kind not in {"win11", "ubuntu"}:
        raise HTTPException(status_code=400, detail="runner_id / runner_kind 无效")
    args = ["claim", "--runner-id", runner_id, "--runner-kind", runner_kind]
    add_cli_arg(args, "--command-id", payload.get("command_id") or payload.get("commandId"))
    add_cli_arg(args, "--limit", payload.get("limit") or 1)
    add_cli_arg(args, "--lease-seconds", payload.get("lease_seconds") or payload.get("leaseSeconds") or 900)
    items = run_agenthub_queue(args)
    return {"ok": True, "items": items}


@app.post("/api/agenthub/commands/complete")
async def post_agenthub_command_complete(request: Request) -> dict:
    require_agenthub_queue_access(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    command_id = str(payload.get("command_id") or payload.get("commandId") or "").strip()
    runner_id = str(payload.get("runner_id") or payload.get("runnerId") or "").strip()
    if not command_id or not runner_id:
        raise HTTPException(status_code=400, detail="command_id / runner_id 不能为空")
    args = ["complete", "--command-id", command_id, "--runner-id", runner_id]
    add_cli_arg(args, "--result-summary", payload.get("result_summary") or payload.get("resultSummary") or "")
    item = run_agenthub_queue(args)
    return {"ok": True, "item": item}


@app.post("/api/agenthub/commands/fail")
async def post_agenthub_command_fail(request: Request) -> dict:
    require_agenthub_queue_access(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式错误") from exc
    command_id = str(payload.get("command_id") or payload.get("commandId") or "").strip()
    runner_id = str(payload.get("runner_id") or payload.get("runnerId") or "").strip()
    if not command_id or not runner_id:
        raise HTTPException(status_code=400, detail="command_id / runner_id 不能为空")
    args = ["fail", "--command-id", command_id, "--runner-id", runner_id]
    add_cli_arg(args, "--error", payload.get("error") or "")
    add_cli_arg(args, "--result-summary", payload.get("result_summary") or payload.get("resultSummary") or "")
    item = run_agenthub_queue(args)
    return {"ok": True, "item": item}


def coursemind_target_url(proxy_path: str, query: str) -> str:
    normalized = proxy_path.strip("/")
    if normalized == "api" or normalized.startswith("api/"):
        base = COURSEMIND_BACKEND_URL
    else:
        base = COURSEMIND_FRONTEND_URL
    suffix = f"/{normalized}" if normalized else "/"
    target = f"{base}{suffix}"
    if query:
        target = f"{target}?{query}"
    return target


def coursemind_rewrite_text(content: bytes, content_type: str) -> bytes:
    charset = "utf-8"
    match = re.search(r"charset=([^;]+)", content_type, re.I)
    if match:
        charset = match.group(1).strip()
    text = content.decode(charset, errors="replace")
    prefix = COURSEMIND_PREFIX
    replacements = [
        ('"/@', f'"{prefix}/@'),
        ("'/@", f"'{prefix}/@"),
        ('("/@', f'("{prefix}/@'),
        ("('/@", f"('{prefix}/@"),
        ('"/src/', f'"{prefix}/src/'),
        ("'/src/", f"'{prefix}/src/"),
        ('("/src/', f'("{prefix}/src/'),
        ("('/src/", f"('{prefix}/src/"),
        ('"/node_modules/', f'"{prefix}/node_modules/'),
        ("'/node_modules/", f"'{prefix}/node_modules/"),
        ('("/node_modules/', f'("{prefix}/node_modules/'),
        ("('/node_modules/", f"('{prefix}/node_modules/"),
        ('"VITE_API_BASE": ""', f'"VITE_API_BASE": "{prefix}"'),
        ('const API_BASE = import.meta.env.VITE_API_BASE ?? "";', f'const API_BASE = "{prefix}";'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text.encode(charset, errors="replace")


def is_rewriteable_coursemind_response(content_type: str) -> bool:
    lowered = content_type.lower()
    return (
        "text/html" in lowered
        or "javascript" in lowered
        or "typescript" in lowered
        or "text/css" in lowered
        or "application/json" in lowered and "vite" in lowered
    )


def coursemind_response_headers(upstream_headers) -> dict[str, str]:
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-encoding",
    }
    headers: dict[str, str] = {}
    for key, value in upstream_headers.items():
        lowered = key.lower()
        if lowered in hop_by_hop:
            continue
        headers[key] = value
    headers["Cache-Control"] = "no-store"
    return headers


@app.get(f"{COURSEMIND_PREFIX}", include_in_schema=False)
def coursemind_redirect() -> Response:
    return Response(status_code=307, headers={"Location": f"{COURSEMIND_PREFIX}/"})


@app.api_route(f"{COURSEMIND_PREFIX}/{{proxy_path:path}}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
async def coursemind_proxy(proxy_path: str, request: Request):
    target = coursemind_target_url(proxy_path, request.url.query)
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
    }
    headers["Accept-Encoding"] = "identity"
    upstream_request = urllib.request.Request(
        target,
        data=body if body and request.method not in {"GET", "HEAD"} else None,
        headers=headers,
        method=request.method,
    )
    try:
        upstream = urllib.request.urlopen(upstream_request, timeout=COURSEMIND_PROXY_TIMEOUT)
    except urllib.error.HTTPError as exc:
        content = exc.read()
        content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
        response_headers = coursemind_response_headers(exc.headers)
        response_headers.pop("Content-Length", None)
        response_headers.pop("content-length", None)
        if content and is_rewriteable_coursemind_response(content_type):
            content = coursemind_rewrite_text(content, content_type)
        return Response(content=content, status_code=exc.code, media_type=content_type, headers=response_headers)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"CourseMind proxy unavailable: {exc}") from exc

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    response_headers = coursemind_response_headers(upstream.headers)
    if is_rewriteable_coursemind_response(content_type):
        content = upstream.read()
        upstream.close()
        content = coursemind_rewrite_text(content, content_type)
        response_headers.pop("Content-Length", None)
        response_headers.pop("content-length", None)
        return Response(content=content, status_code=upstream.status, media_type=content_type, headers=response_headers)

    def iter_upstream():
        try:
            while True:
                chunk = upstream.read(1024 * 512)
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    return StreamingResponse(iter_upstream(), status_code=upstream.status, media_type=content_type, headers=response_headers)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"), headers={"Cache-Control": "no-store"})


app.mount("/static", VersionedStaticFiles(directory=str(FRONTEND_DIR)), name="static")
