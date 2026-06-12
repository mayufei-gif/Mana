from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[2]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
LATEST_STATUS_JSON = RETURN_DIR / "latest_status.json"
LATEST_STATUS_SUMMARY = RETURN_DIR / "latest_status_微信摘要.txt"
ALLOWED_SUFFIXES = {".xlsx", ".md", ".txt", ".json", ".csv", ".opml"}
FOLO_APP_URL = "https://app.folo.is/"
FOLO_EXPORT_PATHS = [
    RETURN_DIR.parent / "InfoRadar_项目文件" / "07_Folo真实数据与订阅清单" / "folo_subscriptions_current.json",
    RETURN_DIR.parent / "folo_subscriptions_current.json",
]
FOLO_LINK_DIR = Path(os.environ.get("INFORADAR_FOLO_LINK_DIR", str(ROOT / "data" / "raw" / "folo_article_links")))
FOLO_LINK_JSONL = FOLO_LINK_DIR / "folo_article_links.jsonl"
FOLO_SIGNAL_JSONL = FOLO_LINK_DIR / "folo_article_signals.jsonl"
FOLO_LINK_INDEX_CACHE: dict | None = None
FOLO_LINK_INDEX_CACHE_STATE: tuple[float, int] | None = None
SEARCH_INDEX_DIR = Path(os.environ.get("INFORADAR_SEARCH_INDEX_DIR", str(ROOT / "data" / "cache")))
SEARCH_INDEX_JSONL = SEARCH_INDEX_DIR / "search_index.jsonl"
SEARCH_INDEX_META_JSON = SEARCH_INDEX_DIR / "search_index_meta.json"
SEARCH_INDEX_DB = SEARCH_INDEX_DIR / "search_index.sqlite"
SEARCH_INDEX_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt"}
SEARCH_INDEX_TEXT_LIMIT = 12000
SEARCH_INDEX_CACHE: list[dict] | None = None
SEARCH_INDEX_CACHE_STATE: tuple[float, int] | None = None
SEARCH_RESULT_CACHE: dict[tuple, tuple[float, dict]] = {}
SEARCH_RESULT_CACHE_TTL_SECONDS = 300
SEARCH_RESULT_CACHE_MAX_ITEMS = 128
DAILY_AUTOMATION_STATE_JSON = ROOT / "logs" / "daily_automation_latest.json"
INSPECTION_INTERVAL_STATE_JSON = ROOT / "data" / "folo_hive" / "inspection_interval.json"
EXPECTED_AUTOMATION_BEIJING_TIMES = ["08:30", "11:30", "17:30", "21:30"]


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def inspection_interval_status(current: str) -> dict:
    state = read_json(INSPECTION_INTERVAL_STATE_JSON)
    previous = str(state.get("previous") or "").strip()
    stored_current = str(state.get("current") or "").strip()
    if current and current != stored_current:
        next_state = {
            "previous": stored_current or previous,
            "current": current,
            "updated_at": now_iso(),
        }
        INSPECTION_INTERVAL_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
        INSPECTION_INTERVAL_STATE_JSON.write_text(json.dumps(next_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return next_state
    return {
        "previous": previous,
        "current": stored_current or current,
        "updated_at": str(state.get("updated_at") or ""),
    }


def size_text(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def file_category(path: Path) -> str:
    name = path.name.lower()
    if "watch" in name or "监控" in name:
        return "监控"
    if "manual" in name or "收集" in name:
        return "收集箱"
    if "source" in name or "rss" in name or "源" in name:
        return "源池"
    if "deep" in name or "深挖" in name:
        return "深挖"
    if "ai" in name:
        return "AI"
    if "全域" in name:
        return "全域情报"
    if "今日" in name or "folo_" in name:
        return "情报表"
    return "其他"


def file_entry(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "suffix": path.suffix.lower(),
        "size": stat.st_size,
        "size_text": size_text(stat.st_size),
        "modified_at": dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "category": file_category(path),
    }


def list_return_files(limit: int = 200) -> list[dict]:
    if not RETURN_DIR.exists():
        return []
    files = [
        path
        for path in RETURN_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [file_entry(path) for path in files[:limit]]


def automation_cron_beijing_times(cron_text: str) -> list[str]:
    times: set[str] = set()
    for line in str(cron_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "run_daily_automation.py" not in stripped:
            continue
        parts = stripped.split()
        if len(parts) < 6:
            continue
        minute, hour_field = parts[0], parts[1]
        if not minute.isdigit():
            continue
        try:
            minute_value = int(minute)
        except ValueError:
            continue
        if not 0 <= minute_value <= 59:
            continue
        for hour in hour_field.split(","):
            if not hour.isdigit():
                continue
            hour_value = (int(hour) + 8) % 24
            times.add(f"{hour_value:02d}:{minute_value:02d}")
    return sorted(times)


def automation_schedule_status() -> dict:
    if os.name != "posix":
        return {
            "configured": False,
            "note": "当前 Web 进程不在 Linux/systemd 环境，未检测 Ubuntu 自动任务。",
        }
    cron_configured = False
    cron_beijing_times: list[str] = []
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        cron_text = proc.stdout or ""
        cron_beijing_times = automation_cron_beijing_times(cron_text)
        cron_has_expected_times = all(time in cron_beijing_times for time in EXPECTED_AUTOMATION_BEIJING_TIMES)
        cron_configured = proc.returncode == 0 and "run_daily_automation.py" in cron_text and "InfoRadar" in cron_text and cron_has_expected_times
    except Exception:
        cron_configured = False
        cron_beijing_times = []
    try:
        proc = subprocess.run(
            ["systemctl", "is-enabled", "inforadar-daily.timer"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        enabled = proc.returncode == 0 and proc.stdout.strip() == "enabled"
    except Exception:
        enabled = False
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "inforadar-daily.timer"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        active = proc.returncode == 0 and proc.stdout.strip() == "active"
    except Exception:
        active = False
    systemd_configured = enabled and active
    configured = systemd_configured or cron_configured
    if systemd_configured:
        note = "Ubuntu systemd timer 已启用，每天自动刷新 InfoRadar。"
    elif cron_configured:
        note = "Ubuntu 用户级 crontab 已启用，每天自动刷新 InfoRadar。"
    else:
        note = "未检测到 inforadar-daily.timer 或 InfoRadar crontab 自动任务。"
    return {
        "configured": configured,
        "enabled": enabled,
        "active": active,
        "cron_configured": cron_configured,
        "cron_beijing_times": cron_beijing_times,
        "expected_beijing_times": EXPECTED_AUTOMATION_BEIJING_TIMES,
        "schedule_type": "systemd" if systemd_configured else "crontab" if cron_configured else "",
        "note": note,
    }


def search_index_status() -> dict:
    meta = read_json(SEARCH_INDEX_META_JSON)
    size = 0
    if SEARCH_INDEX_DB.exists():
        try:
            size = SEARCH_INDEX_DB.stat().st_size
        except OSError:
            size = 0
    return {
        "configured": SEARCH_INDEX_DB.exists(),
        "record_count": int(meta.get("record_count") or 0),
        "built_at": str(meta.get("built_at") or ""),
        "size_text": size_text(size) if size else "",
    }


def daily_automation_status() -> dict:
    state = read_json(DAILY_AUTOMATION_STATE_JSON)
    commands = state.get("commands") if isinstance(state.get("commands"), list) else []
    failed = [item for item in commands if isinstance(item, dict) and not item.get("success")]
    finished_at = str(state.get("finished_at") or "").strip()
    finished_dt = parse_status_datetime(finished_at)
    age_hours = None
    if finished_dt:
        age_hours = round((dt.datetime.now() - finished_dt).total_seconds() / 3600, 1)
    return {
        "configured": DAILY_AUTOMATION_STATE_JSON.exists(),
        "ok": bool(state.get("ok")) if state else False,
        "started_at": str(state.get("started_at") or ""),
        "finished_at": finished_at,
        "age_hours": age_hours,
        "command_count": len(commands),
        "success_count": len(commands) - len(failed),
        "failed_count": len(failed),
        "failed_commands": [str(item.get("command") or "未命名步骤") for item in failed[:5]],
        "is_stale": bool(age_hours is None or age_hours >= 30),
    }


def fetch_failed_examples(details: dict, limit: int = 6) -> list[dict]:
    raw_path = str(details.get("fetch_status_csv") or "").strip()
    if not raw_path:
        return []
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        return []
    examples: list[dict] = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = str(row.get("状态") or row.get("status") or "").lower()
                success = str(row.get("成功") or row.get("success") or "").lower()
                error = str(row.get("错误") or row.get("error") or "").strip()
                if status != "failed" and success not in {"false", "0", "否"} and not error:
                    continue
                examples.append(
                    {
                        "name": str(row.get("源名称") or row.get("source_name") or row.get("name") or "未命名源"),
                        "url": str(row.get("可抓取RSS链接") or row.get("实际抓取URL") or row.get("url") or ""),
                        "error": compact_text(error, 220),
                    }
                )
                if len(examples) >= limit:
                    break
    except Exception:
        return []
    return examples


def safe_return_file(raw_path: str) -> Path:
    if not raw_path:
        raise ValueError("path 不能为空")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = RETURN_DIR / raw_path
    resolved = candidate.resolve(strict=False)
    allowed_bases = [
        RETURN_DIR,
        ROOT / "sources",
        ROOT / "reports",
        ROOT / "data" / "raw" / "folo_article_links",
    ]
    allowed = False
    for base_path in allowed_bases:
        if not base_path.exists():
            continue
        base = base_path.resolve(strict=True)
        common = os.path.commonpath([str(base).lower(), str(resolved).lower()])
        if common == str(base).lower():
            allowed = True
            break
    if not allowed:
        raise ValueError("禁止访问 InfoRadar 白名单目录之外的文件")
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("该文件类型不允许通过 Web 读取")
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return resolved


def latest_status() -> dict:
    status = read_json(LATEST_STATUS_JSON)
    summary = read_text(LATEST_STATUS_SUMMARY)
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    schedule = automation_schedule_status()
    finished_at = str(status.get("finished_at") or details.get("ended") or "").strip()
    finished_dt = parse_status_datetime(finished_at)
    age_hours = None
    if finished_dt:
        age_hours = round((dt.datetime.now() - finished_dt).total_seconds() / 3600, 1)
    index_status = search_index_status()
    daily_status = daily_automation_status()
    inspection_interval = inspection_interval_status(finished_at)
    return {
        "ok": True,
        "generated_at": now_iso(),
        "status": status,
        "summary": summary,
        "files": list_return_files(30),
        "health": {
            "last_command": status.get("command") or "",
            "last_finished_at": finished_at,
            "previous_finished_at": inspection_interval.get("previous", ""),
            "current_finished_at": inspection_interval.get("current", ""),
            "inspection_interval_label": f"{inspection_interval.get('previous') or '首次记录'} → {inspection_interval.get('current') or finished_at or '等待巡检完成'}",
            "age_hours": age_hours,
            "is_stale": bool(age_hours is not None and age_hours >= 30),
            "schedule_configured": schedule.get("configured", False),
            "schedule_enabled": schedule.get("enabled", False),
            "schedule_active": schedule.get("active", False),
            "schedule_type": schedule.get("schedule_type", ""),
            "schedule_note": schedule.get("note", "当前只展示可验证的本地运行记录。"),
            "schedule_beijing_times": schedule.get("cron_beijing_times", []),
            "schedule_expected_beijing_times": schedule.get("expected_beijing_times", EXPECTED_AUTOMATION_BEIJING_TIMES),
            "daily_automation_configured": daily_status.get("configured", False),
            "daily_automation_ok": daily_status.get("ok", False),
            "daily_automation_started_at": daily_status.get("started_at", ""),
            "daily_automation_finished_at": daily_status.get("finished_at", ""),
            "daily_automation_age_hours": daily_status.get("age_hours"),
            "daily_automation_command_count": daily_status.get("command_count", 0),
            "daily_automation_success_count": daily_status.get("success_count", 0),
            "daily_automation_failed_count": daily_status.get("failed_count", 0),
            "daily_automation_failed_commands": daily_status.get("failed_commands", []),
            "daily_automation_is_stale": daily_status.get("is_stale", True),
            "search_index_record_count": index_status.get("record_count", 0),
            "search_index_built_at": index_status.get("built_at", ""),
            "search_index_size_text": index_status.get("size_text", ""),
            "fetch_source_count": details.get("fetch_source_count", 0),
            "fetch_success_source_count": details.get("fetch_success_source_count", 0),
            "fetch_failed_source_count": details.get("fetch_failed_source_count", 0),
            "fetch_success_ratio": details.get("fetch_success_ratio", 0),
            "fetch_failed_examples": fetch_failed_examples(details),
            "fetch_item_count": details.get("fetch_item_count", 0),
            "cache_fallback_used": bool(details.get("cache_fallback_used")),
            "cache_fallback_added_count": details.get("cache_fallback_added_count", 0),
            "auto_input_count": details.get("auto_input_count", 0),
            "manual_input_count": details.get("manual_input_count", 0),
            "manual_output_count": details.get("manual_output_count", 0),
            "folo_link_input_count": details.get("folo_link_input_count", 0),
            "folo_link_output_count": details.get("folo_link_output_count", 0),
        },
    }


def parse_status_datetime(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text[: len(dt.datetime.now().strftime(fmt))], fmt)
        except Exception:
            continue
    return None


def cell_col_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    idx = 0
    for char in letters:
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return max(0, idx - 1)


def read_xlsx_rows(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                shared.append("".join(t.text or "" for t in si.findall(".//a:t", ns)))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        parsed_rows: list[list[str]] = []
        for row in sheet.findall(".//a:row", ns):
            values: list[str] = []
            for cell in row.findall("a:c", ns):
                col_idx = cell_col_index(cell.get("r", "A1"))
                while len(values) <= col_idx:
                    values.append("")
                cell_type = cell.get("t", "")
                if cell_type == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//a:t", ns))
                else:
                    raw = cell.find("a:v", ns)
                    value = "" if raw is None else raw.text or ""
                    if cell_type == "s" and value:
                        value = shared[int(value)]
                values[col_idx] = value
            parsed_rows.append(values)
    if not parsed_rows:
        return []
    headers = [value.strip() for value in parsed_rows[0]]
    rows: list[dict] = []
    for values in parsed_rows[1 : limit + 1]:
        row = {header: values[idx].strip() if idx < len(values) else "" for idx, header in enumerate(headers) if header}
        if any(row.values()):
            rows.append(row)
    return rows


def latest_report_xlsx(topic: str = "") -> Path | None:
    safe_topic = re.sub(r"[^\w\u4e00-\u9fff]+", "_", topic or "").strip("_")
    patterns = [f"FOLO_{safe_topic}_*.xlsx"] if safe_topic else []
    patterns.extend(["FOLO_今日情报_*.xlsx", "FOLO_全域情报_*.xlsx", "FOLO_*.xlsx"])
    seen: set[Path] = set()
    candidates: list[Path] = []
    for pattern in patterns:
        for path in RETURN_DIR.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                candidates.append(path)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def compact_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def normalize_match_url(value: str) -> str:
    text = compact_url(value)
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except Exception:
        return text.lower()
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"from", "spm", "ref", "source"}
    ]
    path = parts.path.rstrip("/") or parts.path
    cleaned = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))
    return cleaned.rstrip("/").lower()


def normalize_match_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").strip().lower())


def folo_article_url(feed_id: str, entry_id: str) -> str:
    feed = str(feed_id or "").strip()
    entry = str(entry_id or "").strip()
    if feed and entry:
        return f"{FOLO_APP_URL}timeline/articles/{quote_plus(feed)}/{quote_plus(entry)}"
    return ""


def load_folo_article_link_index() -> dict:
    global FOLO_LINK_INDEX_CACHE, FOLO_LINK_INDEX_CACHE_STATE
    rows: list[dict] = []
    by_url: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    if not FOLO_LINK_JSONL.exists():
        return {"rows": rows, "by_url": by_url, "by_title": by_title}
    stat = FOLO_LINK_JSONL.stat()
    cache_state = (stat.st_mtime, stat.st_size)
    if FOLO_LINK_INDEX_CACHE is not None and FOLO_LINK_INDEX_CACHE_STATE == cache_state:
        return FOLO_LINK_INDEX_CACHE
    with FOLO_LINK_JSONL.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            url = str(item.get("folo_article_url") or "").strip()
            if not url:
                url = folo_article_url(str(item.get("feedId") or item.get("feed_id") or ""), str(item.get("entryId") or item.get("entry_id") or ""))
            if not url:
                continue
            item["folo_article_url"] = url
            rows.append(item)
            for key_name in ("original_url", "url", "article_url", "external_url"):
                key = normalize_match_url(str(item.get(key_name) or ""))
                if key:
                    by_url[key] = item
            title_key = normalize_match_title(str(item.get("title") or ""))
            if title_key:
                by_title[title_key] = item
    FOLO_LINK_INDEX_CACHE = {"rows": rows, "by_url": by_url, "by_title": by_title}
    FOLO_LINK_INDEX_CACHE_STATE = cache_state
    return FOLO_LINK_INDEX_CACHE


def folo_article_link_for_row(row: dict, link_index: dict) -> dict:
    for key_name in ("原文URL", "官方原文链接", "url", "article_url", "link"):
        key = normalize_match_url(str(row.get(key_name) or ""))
        if key and key in link_index.get("by_url", {}):
            item = link_index["by_url"][key]
            return {"url": item.get("folo_article_url", ""), "matched_by": "original_url", "item": item}
    title_key = normalize_match_title(str(row.get("标题") or row.get("title") or ""))
    if title_key and title_key in link_index.get("by_title", {}):
        item = link_index["by_title"][title_key]
        return {"url": item.get("folo_article_url", ""), "matched_by": "title", "item": item}
    return {"url": "", "matched_by": "", "item": {}}


def load_folo_feed_index() -> list[dict]:
    export_path = next((path for path in FOLO_EXPORT_PATHS if path.exists()), None)
    if not export_path:
        return []
    try:
        data = json.loads(export_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    subscriptions = data.get("data", {}).get("subscriptions", []) if isinstance(data, dict) else []
    feeds: list[dict] = []
    for item in subscriptions:
        feed_id = str(item.get("feedId") or "")
        feed = item.get("feeds") if isinstance(item.get("feeds"), dict) else {}
        list_obj = item.get("lists") if isinstance(item.get("lists"), dict) else {}
        if feed:
            feeds.append(
                {
                    "kind": "feed",
                    "id": feed_id or str(feed.get("id") or ""),
                    "title": item.get("title") or feed.get("title") or "",
                    "url": compact_url(feed.get("url") or ""),
                    "site_url": compact_url(feed.get("siteUrl") or ""),
                }
            )
        elif list_obj:
            feeds.append(
                {
                    "kind": "list",
                    "id": feed_id or str(list_obj.get("id") or ""),
                    "title": item.get("title") or list_obj.get("title") or "",
                    "url": "",
                    "site_url": "",
                }
            )
    return feeds


def folo_link_for_row(row: dict, feed_index: list[dict]) -> dict:
    feed_url = compact_url(row.get("订阅源URL", ""))
    source_name = (row.get("来源名称") or row.get("Folo订阅源名称") or "").strip()
    source_lower = source_name.lower()
    for feed in feed_index:
        if feed_url and feed_url in {feed.get("url"), feed.get("site_url")}:
            route = "lists" if feed.get("kind") == "list" else "feeds"
            return {"url": f"{FOLO_APP_URL}share/{route}/{feed.get('id')}", "matched": True}
        title = (feed.get("title") or "").strip()
        if source_lower and title and (source_lower == title.lower() or source_lower in title.lower() or title.lower() in source_lower):
            route = "lists" if feed.get("kind") == "list" else "feeds"
            return {"url": f"{FOLO_APP_URL}share/{route}/{feed.get('id')}", "matched": True}
    return {"url": "", "matched": False}


def load_source_pool_folo_link_index() -> dict:
    path = ROOT / "sources" / "source_pool_from_folo.csv"
    by_name: dict[str, dict] = {}
    by_url: dict[str, dict] = {}
    if not path.exists():
        return {"by_name": by_name, "by_url": by_url}
    try:
        rows = read_csv_rows(path)
    except Exception:
        return {"by_name": by_name, "by_url": by_url}
    for row in rows:
        feed_id = str(row.get("Folo源ID") or row.get("Folo订阅ID") or "").strip()
        if not feed_id:
            continue
        item = {
            "url": f"{FOLO_APP_URL}share/feeds/{quote_plus(feed_id)}",
            "feed_id": feed_id,
            "name": row.get("源名称") or row.get("Folo订阅源名称") or "",
        }
        for key_name in ("源名称", "Folo订阅源名称", "来源名称"):
            key = normalize_match_title(str(row.get(key_name) or ""))
            if key:
                by_name[key] = item
        for key_name in ("RSS链接", "可抓取RSS链接", "订阅源URL", "官网链接"):
            key = normalize_match_url(str(row.get(key_name) or ""))
            if key:
                by_url[key] = item
    return {"by_name": by_name, "by_url": by_url}


def folo_source_link_for_row(row: dict, source_index: dict | None) -> dict:
    if not source_index:
        return {"url": "", "matched_by": "", "item": {}}
    for key_name in ("订阅源URL", "RSS链接", "可抓取RSS链接", "original_rss_url"):
        key = normalize_match_url(str(row.get(key_name) or ""))
        if key and key in source_index.get("by_url", {}):
            item = source_index["by_url"][key]
            return {"url": item.get("url", ""), "matched_by": "source_url", "item": item}
    for key_name in ("来源名称", "源名称", "Folo订阅源名称", "source", "source_name"):
        key = normalize_match_title(str(row.get(key_name) or ""))
        if key and key in source_index.get("by_name", {}):
            item = source_index["by_name"][key]
            return {"url": item.get("url", ""), "matched_by": "source_name", "item": item}
    return {"url": "", "matched_by": "", "item": {}}


def folo_article_url_from_row(row: dict) -> str:
    feed_id = (
        row.get("feedId")
        or row.get("feed_id")
        or row.get("Folo feedId")
        or row.get("Folo Feed ID")
        or row.get("订阅源ID")
        or ""
    )
    entry_id = (
        row.get("entryId")
        or row.get("entry_id")
        or row.get("Folo entryId")
        or row.get("Folo Entry ID")
        or row.get("条目ID")
        or ""
    )
    feed_id = str(feed_id).strip()
    entry_id = str(entry_id).strip()
    return folo_article_url(feed_id, entry_id)


def extract_folo_article_link(payload: dict) -> dict:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    feed = payload.get("feed") if isinstance(payload.get("feed"), dict) else {}
    view = payload.get("view") if isinstance(payload.get("view"), dict) else {}
    category = payload.get("category") if isinstance(payload.get("category"), dict) else {}
    title = (
        payload.get("title")
        or entry.get("title")
        or view.get("title")
        or ""
    )
    feed_id = (
        payload.get("feedId")
        or payload.get("feed_id")
        or entry.get("feedId")
        or entry.get("feed_id")
        or feed.get("id")
        or feed.get("feedId")
        or ""
    )
    entry_id = (
        payload.get("entryId")
        or payload.get("entry_id")
        or payload.get("id")
        or entry.get("id")
        or entry.get("entryId")
        or ""
    )
    original_url = (
        payload.get("original_url")
        or payload.get("article_url")
        or payload.get("url")
        or entry.get("url")
        or entry.get("link")
        or entry.get("externalUrl")
        or view.get("url")
        or ""
    )
    source = (
        payload.get("source")
        or payload.get("source_name")
        or feed.get("title")
        or feed.get("name")
        or ""
    )
    summary = (
        payload.get("summary")
        or payload.get("description")
        or entry.get("summary")
        or entry.get("description")
        or entry.get("content")
        or view.get("summary")
        or ""
    )
    published_at = (
        payload.get("published_at")
        or payload.get("published")
        or payload.get("publishedAt")
        or entry.get("published_at")
        or entry.get("publishedAt")
        or entry.get("published")
        or entry.get("createdAt")
        or ""
    )
    folo_view = (
        payload.get("folo_view")
        or payload.get("view_type")
        or payload.get("view")
        or view.get("type")
        or view.get("name")
        or ""
    )
    if isinstance(folo_view, dict):
        folo_view = folo_view.get("type") or folo_view.get("name") or ""
    folo_category = (
        payload.get("folo_category")
        or payload.get("category_name")
        or category.get("name")
        or category.get("title")
        or ""
    )
    article_url = payload.get("folo_article_url") or folo_article_url(str(feed_id), str(entry_id))
    if not article_url:
        raise ValueError("缺少 Folo feedId/entryId，无法生成真实原条链接")
    if "{{" in str(feed_id) or "{{" in str(entry_id):
        raise ValueError("Folo 模板变量尚未被替换，拒绝写入占位符链接")
    if "[" in str(feed_id) or "[" in str(entry_id):
        raise ValueError("Folo 模板变量尚未被替换，拒绝写入占位符链接")
    return {
        "title": str(title or "").strip(),
        "source": str(source or "").strip(),
        "original_url": str(original_url or "").strip(),
        "feedId": str(feed_id or "").strip(),
        "entryId": str(entry_id or "").strip(),
        "folo_article_url": str(article_url or "").strip(),
        "published_at": str(published_at or "").strip(),
        "folo_view": str(folo_view or "").strip(),
        "folo_category": str(folo_category or "").strip(),
        "summary": str(summary or "").strip()[:1200],
        "created_at": now_iso(),
    }


def append_folo_article_link(payload: dict) -> dict:
    record = extract_folo_article_link(payload)
    FOLO_LINK_DIR.mkdir(parents=True, exist_ok=True)
    with FOLO_LINK_JSONL.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def append_folo_article_signal(payload: dict) -> dict:
    title = str(payload.get("title") or payload.get("标题") or "").strip()
    original_url = str(payload.get("original_url") or payload.get("url") or payload.get("原文URL") or "").strip()
    source = str(payload.get("source") or payload.get("来源") or "").strip()
    record = {
        "title": title,
        "source": source,
        "original_url": original_url,
        "published_at": str(payload.get("published_at") or payload.get("published") or "").strip(),
        "received_at": now_iso(),
        "status": "received_without_folo_internal_id",
        "raw": payload,
    }
    if not title and not original_url:
        raise ValueError("缺少 title/url，无法记录 Folo 信号")
    if "[title]" in title or "[url]" in original_url or "{{" in title or "{{" in original_url:
        raise ValueError("Folo 模板变量尚未被替换，拒绝写入占位符信号")
    FOLO_LINK_DIR.mkdir(parents=True, exist_ok=True)
    with FOLO_SIGNAL_JSONL.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def folo_article_link_summary(limit: int = 80) -> dict:
    index = load_folo_article_link_index()
    rows = index.get("rows", [])
    signals = read_jsonl_rows(FOLO_SIGNAL_JSONL, limit)
    return {
        "ok": True,
        "path": str(FOLO_LINK_JSONL),
        "count": len(rows),
        "items": rows[-limit:][::-1],
        "signal_path": str(FOLO_SIGNAL_JSONL),
        "signal_count": len(read_jsonl_rows(FOLO_SIGNAL_JSONL, 100000)),
        "signals": signals[::-1],
    }


def folo_item_search_url(row: dict) -> str:
    return ""


def row_has_folo_internal_id(row: dict) -> bool:
    return bool(folo_article_url_from_row(row))


def row_collection_type(row: dict) -> str:
    trace = str(row.get("source_trace_id") or row.get("来源追踪ID") or "").lower()
    folder = str(row.get("Folo文件夹路径") or "").lower()
    method = str(row.get("采集方式") or row.get("来源类型") or "").lower()
    feed = str(row.get("订阅源URL") or "")
    if "watch_" in trace or "watch_updates" in folder or "watch" in method or feed.startswith("watch://"):
        return "官网观察源"
    if "manual" in trace or "manual_inbox" in folder or "手动" in method:
        return "手动收集"
    if row.get("订阅源URL") or row.get("原始RSS链接") or row.get("实际抓取URL"):
        return "Folo/RSS 抓取"
    return "未知来源"


def normalize_publication_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        try:
            serial = float(text)
            if serial > 30000:
                date = dt.datetime(1899, 12, 30) + dt.timedelta(days=serial)
                return date.strftime("%Y-%m-%d")
        except Exception:
            return text
    return text


def publication_time_from_row(row: dict) -> str:
    for key in [
        "原文发布时间",
        "发布时间",
        "发布日期",
        "事件时间",
        "文章发布时间",
        "发布于",
        "published_at",
        "published",
        "pubDate",
        "date",
    ]:
        value = normalize_publication_time(row.get(key, ""))
        if value:
            return value
    return ""


def parse_search_datetime(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    text = re.sub(r"年|月", "-", text).replace("日", "")
    text = text.replace("/", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = f"{text} 00:00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        cleaned = text.replace("T", " ").split(".")[0].split("+")[0]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(cleaned[: len(dt.datetime.now().strftime(fmt))], fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def search_record_timestamp(record: dict) -> float:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    for key in ["published_at", "发布时间", "date"]:
        parsed = parse_search_datetime(str(payload.get(key, "")))
        if parsed is not None:
            return parsed.timestamp()
    kind = str(record.get("kind") or "")
    if "情报" in kind or kind == "监控":
        return 0.0
    for key in ["modified_at", "collected_at", "detected_at", "创建时间", "updated_at"]:
        parsed = parse_search_datetime(str(payload.get(key, "")))
        if parsed is not None:
            return parsed.timestamp()
    return 0.0


def is_generated_summary_title(title: str) -> bool:
    value = str(title or "").strip()
    lower = value.lower()
    if value.startswith("【InfoRadar"):
        return True
    return lower.startswith("inforadar ") or lower.startswith("inforadar_") or value.startswith("InfoRadar ")


def latest_intel_items(topic: str = "", limit: int = 50, resolve_folo_links: bool = True) -> dict:
    xlsx = latest_report_xlsx(topic)
    if not xlsx:
        return {"ok": True, "source_file": "", "items": [], "stats": {}}
    feed_index = load_folo_feed_index()
    link_index = load_folo_article_link_index() if resolve_folo_links else {"rows": [], "by_url": {}, "by_title": {}}
    rows = read_xlsx_rows(xlsx, limit)
    items: list[dict] = []
    total_rows = len(rows)
    folo_internal_count = 0
    manual_count = 0
    rss_count = 0
    source_url_count = 0
    original_url_count = 0
    folo_link_index_count = len(link_index.get("rows", []))
    for row in rows:
        folo = folo_link_for_row(row, feed_index)
        direct_folo_article_url = folo_article_url_from_row(row)
        linked_folo = folo_article_link_for_row(row, link_index) if resolve_folo_links else {"url": "", "matched_by": "", "item": {}}
        folo_article_url = direct_folo_article_url or linked_folo.get("url", "")
        has_folo_internal_id = bool(folo_article_url)
        matched_by = "row_id" if direct_folo_article_url else linked_folo.get("matched_by", "")
        collection_type = row_collection_type(row)
        is_watch_only = collection_type == "官网观察源"
        if has_folo_internal_id:
            folo_internal_count += 1
        if collection_type == "手动收集":
            manual_count += 1
        if collection_type == "Folo/RSS 抓取":
            rss_count += 1
        if row.get("订阅源URL"):
            source_url_count += 1
        if row.get("原文URL"):
            original_url_count += 1
        source_url = "" if is_watch_only else folo["url"]
        items.append(
            {
                "index": row.get("序号", ""),
                "title": row.get("标题", ""),
                "source": row.get("来源名称") or row.get("Folo订阅源名称", ""),
                "category": row.get("主分类", ""),
                "section": row.get("全域栏目", ""),
                "score": row.get("相关度评分", ""),
                "risk": row.get("风险等级", ""),
                "why": row.get("为什么与你有关", ""),
                "action": row.get("建议行动", ""),
                "article_url": row.get("原文URL", ""),
                "official_url": row.get("官方原文链接") or row.get("原文URL", ""),
                "feed_url": row.get("订阅源URL", ""),
                "folo_folder": row.get("Folo文件夹路径", ""),
                "source_file": str(xlsx),
                "source_row": row.get("序号", ""),
                "published_at": publication_time_from_row(row),
                "detected_at": row.get("detected_at", ""),
                "last_seen_at": row.get("last_seen_at", ""),
                "is_new": row.get("is_new", ""),
                "school_category": row.get("school_category", ""),
                "collection_type": collection_type,
                "has_folo_internal_id": False if is_watch_only else has_folo_internal_id,
                "folo_position_status": "官网观察源，不可定位到 Folo 原条" if is_watch_only else ("可打开 Folo 原条" if has_folo_internal_id else "缺少 Folo 内部条目 ID"),
                "folo_link_matched_by": matched_by,
                "folo_url": "" if is_watch_only else folo_article_url,
                "folo_article_url": "" if is_watch_only else folo_article_url,
                "folo_search_url": "",
                "folo_source_url": source_url,
                "folo_matched": False if is_watch_only else folo["matched"],
                "verify_status": row.get("核验状态", ""),
                "needs_official_verify": row.get("是否需要官方核验", ""),
            }
        )
    return {
        "ok": True,
        "source_file": str(xlsx),
        "items": items,
        "stats": {
            "item_count": total_rows,
            "rss_count": rss_count,
            "manual_count": manual_count,
            "source_url_count": source_url_count,
            "original_url_count": original_url_count,
            "folo_internal_id_count": folo_internal_count,
            "folo_link_index_count": folo_link_index_count,
            "folo_position_reliable": folo_internal_count == total_rows and total_rows > 0,
        },
    }


def read_csv_rows(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit]


def read_jsonl_rows(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-limit:]


def latest_path(pattern: str, base: Path = RETURN_DIR) -> Path | None:
    if not base.exists():
        return None
    paths = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def manual_inbox_summary() -> dict:
    inbox_dir = ROOT / "data" / "manual_inbox" / "wechat"
    processed_dir = ROOT / "data" / "manual_inbox" / "processed"
    latest_inbox = latest_path("manual_items_*.jsonl", inbox_dir) if inbox_dir.exists() else None
    latest_processed = latest_path("manual_processed_*.jsonl", processed_dir) if processed_dir.exists() else None
    collected_summary = latest_path("manual_collected_items*_微信摘要.txt")
    inbox_summary = RETURN_DIR / "manual_inbox_微信摘要.txt"
    inbox_rows = read_jsonl_rows(latest_inbox, 50) if latest_inbox else []
    processed_rows = read_jsonl_rows(latest_processed, 50) if latest_processed else []
    return {
        "ok": True,
        "latest_inbox_file": str(latest_inbox or ""),
        "latest_processed_file": str(latest_processed or ""),
        "today_count": len(inbox_rows),
        "processed_count": len(processed_rows),
        "recent_items": inbox_rows[-10:],
        "summary": read_text(collected_summary or inbox_summary),
    }


def watch_summary() -> dict:
    requests_path = ROOT / "sources" / "watch_only_requests.csv"
    updates_dir = ROOT / "data" / "watch" / "updates"
    latest_updates = latest_path("watch_updates_*.jsonl", updates_dir) if updates_dir.exists() else None
    requests = read_csv_rows(requests_path, 200)
    updates = read_jsonl_rows(latest_updates, 100) if latest_updates else []
    return {
        "ok": True,
        "request_file": str(requests_path),
        "request_count": len(requests),
        "requests": requests[-30:],
        "updates_file": str(latest_updates or ""),
        "update_count": len(updates),
        "updates": updates[-20:],
    }


def source_pool_summary(include_folo_links: bool = True) -> dict:
    source_dir = ROOT / "sources"
    source_files = []
    for pattern in [
        "source_pool_strategy.*",
        "source_pool_from_folo.*",
        "all_domain_*.*",
        "candidate_sources.*",
        "source_watchlist.*",
    ]:
        source_files.extend(path for path in source_dir.glob(pattern) if path.is_file())
    return_files = [
        path
        for path in RETURN_DIR.glob("*")
        if path.is_file() and ("RSS" in path.name or "源" in path.name or "source" in path.name.lower())
    ]
    all_files = sorted(set(source_files + return_files), key=lambda p: p.stat().st_mtime, reverse=True)
    folo_sources = read_csv_rows(source_dir / "source_pool_from_folo.csv", 500)
    candidate_sources = read_csv_rows(source_dir / "candidate_sources.csv", 300)
    all_domain_candidates = read_csv_rows(source_dir / "all_domain_candidate_sources.csv", 300)
    candidate_import_ready = [
        row
        for row in candidate_sources
        if str(row.get("是否可被Folo添加") or "").strip() == "是" and str(row.get("RSS链接") or "").strip()
    ]
    all_domain_import_ready_path = RETURN_DIR / "all_domain_folo_import_ready.xlsx"
    all_domain_import_ready = read_xlsx_rows(all_domain_import_ready_path, 200) if all_domain_import_ready_path.exists() else []
    import_ready = all_domain_import_ready or candidate_import_ready
    broad_candidates = [
        row
        for row in all_domain_candidates
        if str(row.get("源状态") or "").strip() == "候选待加入"
    ]
    latest_opml = latest_path("all_domain_folo_import_ready.opml", RETURN_DIR) or latest_path("*.opml", RETURN_DIR) or latest_path("*.opml", source_dir / "opml")
    folo_links = folo_article_link_summary(20) if include_folo_links else {"count": 0, "items": [], "signal_count": 0, "signals": []}
    return {
        "ok": True,
        "files": [file_entry(path) for path in all_files[:80]],
        "source_pool_strategy_csv": read_csv_rows(source_dir / "source_pool_strategy.csv", 50),
        "folo_source_count": len(folo_sources),
        "folo_sources": folo_sources[:80],
        "candidate_count": len(candidate_sources),
        "candidate_import_ready_count": len(candidate_import_ready),
        "import_ready_count": len(import_ready),
        "import_ready_sources": import_ready[:60],
        "import_ready_file": str(all_domain_import_ready_path if all_domain_import_ready else source_dir / "candidate_sources.csv"),
        "broad_candidate_count": len(broad_candidates),
        "broad_candidates": broad_candidates[:80],
        "latest_opml": file_entry(latest_opml) if latest_opml else {},
        "folo_article_link_count": folo_links.get("count", 0),
        "folo_article_links": folo_links.get("items", []),
        "folo_article_signal_count": folo_links.get("signal_count", 0),
        "folo_article_signals": folo_links.get("signals", []),
        "folo_link_token_configured": bool(os.environ.get("FOLO_LINK_TOKEN")),
        "folo_webhook_ready": bool(os.environ.get("FOLO_LINK_TOKEN") and latest_opml),
    }


def text_blob(value) -> str:
    if isinstance(value, dict):
        return " ".join(text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(text_blob(item) for item in value)
    return str(value or "")


def compact_text(value: str, limit: int = SEARCH_INDEX_TEXT_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def first_value(row: dict, keys: list[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def search_index_roots() -> list[Path]:
    roots = [ROOT / "data", ROOT / "sources", ROOT / "reports", FOLO_LINK_DIR]
    if RETURN_DIR.exists():
        roots.append(RETURN_DIR)
    seen = set()
    selected: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve(strict=False)
        except Exception:
            resolved = root
        key = str(resolved).lower()
        if key not in seen and root.exists():
            seen.add(key)
            selected.append(root)
    return selected


def search_index_source_files() -> list[Path]:
    files: list[Path] = []
    for root in search_index_roots():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SEARCH_INDEX_SUFFIXES:
                continue
            if SEARCH_INDEX_DIR in path.parents or "__pycache__" in path.parts:
                continue
            name = path.name
            lower_name = name.lower()
            suffix = path.suffix.lower()
            parts = {part.lower() for part in path.parts}
            is_rss_item_csv = suffix == ".csv" and (
                lower_name.startswith("folo_items_real")
                or (lower_name.startswith("folo_") and "deduped" in parts)
            )
            is_folo_link_jsonl = suffix == ".jsonl" and (
                "folo_article_links" in parts or lower_name == FOLO_LINK_JSONL.name.lower()
            )
            is_manual_json = suffix in {".json", ".jsonl"} and ("manual" in lower_name or "inbox" in lower_name or "收集" in name)
            is_return_summary = suffix in {".md", ".txt"} and lower_name.startswith("folo_") and RETURN_DIR.exists() and RETURN_DIR in path.parents
            if is_rss_item_csv or is_folo_link_jsonl or is_manual_json or is_return_summary:
                files.append(path)
    files.sort(key=lambda item: str(item).lower())
    return files


def search_source_signature(files: list[Path]) -> dict:
    max_mtime = 0.0
    total_size = 0
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        max_mtime = max(max_mtime, stat.st_mtime)
        total_size += stat.st_size
    return {"source_count": len(files), "source_max_mtime": max_mtime, "source_total_size": total_size}


def parse_index_datetime(value: str, fallback_path: Path | None = None) -> tuple[str, float]:
    parsed = parse_search_datetime(str(value or ""))
    if parsed is None and fallback_path is not None:
        try:
            parsed = dt.datetime.fromtimestamp(fallback_path.stat().st_mtime)
        except OSError:
            parsed = None
    if parsed is None:
        return "", 0.0
    return parsed.strftime("%Y-%m-%d %H:%M:%S"), parsed.timestamp()


def publication_datetime_from_url(value: str) -> str:
    text = str(value or "")
    patterns = [
        r"/(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})(?:/|_|-|\.|$)",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        y, m, d = match.groups()
        try:
            parsed = dt.datetime(int(y), int(m), int(d))
        except ValueError:
            continue
        return parsed.strftime("%Y-%m-%d 00:00:00")
    return ""


def stable_record_id(parts: list[str]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def search_tokens_for_text(text: str) -> str:
    value = str(text or "").lower()
    tokens: set[str] = set()
    for word in re.findall(r"[a-z0-9][a-z0-9_\-+.]{1,}", value):
        tokens.add(word[:80])
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        if len(chunk) <= 12:
            tokens.add(chunk)
        for size in (2, 3):
            for index in range(0, max(0, len(chunk) - size + 1)):
                tokens.add(chunk[index : index + size])
    return " ".join(sorted(tokens))


def fts_query_for_search(query: str, mode: str = "smart") -> str:
    tokens: set[str] = set()
    for term in query_terms(query, mode).keys():
        for token in search_tokens_for_text(term).split():
            if token:
                tokens.add(token.replace('"', '""'))
    return " OR ".join(f'"{token}"' for token in sorted(tokens))


def query_search_token_set(query: str, mode: str = "smart") -> set[str]:
    tokens: set[str] = set()
    for term in query_terms(query, mode).keys():
        for token in search_tokens_for_text(term).split():
            if token:
                tokens.add(token)
    return tokens


def search_record_from_row(
    row: dict,
    path: Path,
    row_index: int,
    link_index: dict | None = None,
    source_index: dict | None = None,
) -> dict | None:
    title = first_value(row, ["标题", "title", "Title", "name", "来源名称", "源名称", "source_name"])
    url = first_value(row, ["原文URL", "original_url", "url", "link", "链接", "article_url", "folo_article_url", "订阅源URL", "可抓取RSS链接"])
    source = first_value(row, ["来源名称", "源名称", "source", "source_name", "Folo订阅源名称"])
    folder = first_value(row, ["Folo文件夹路径", "folo_category", "folo_view", "folder", "category", "分类"])
    published_raw = first_value(row, ["发布时间", "published_at", "pubDate", "published", "created_at", "updated_at", "date", "finished_at"])
    summary = first_value(row, ["摘要", "summary", "description", "内容", "正文", "错误"])
    status = first_value(row, ["状态", "status"])
    if not title and not summary and not url:
        return None
    published_at, timestamp = parse_index_datetime(published_raw)
    if not published_at:
        published_at, timestamp = parse_index_datetime(publication_datetime_from_url(url))
    recorded_at, recorded_timestamp = parse_index_datetime("", path)
    kind = "历史情报" if title and ("标题" in row or "title" in row or "原文URL" in row or "发布时间" in row) else "历史记录"
    meta = " · ".join(filter(None, [source, folder, status]))
    tag_text = first_value(row, ["标签", "tags", "主分类", "全域分类", "来源类型", "采集方式"])
    search_text = compact_text(" ".join(filter(None, [title, source, folder, tag_text, published_raw, summary])), 1800)
    record_id = stable_record_id([url, title, source, published_at, str(path), str(row_index)])
    direct_folo_url = first_value(row, ["folo_article_url", "folo_url"]) or folo_article_url_from_row(row)
    linked_folo = folo_article_link_for_row(row, link_index) if link_index else {"url": "", "matched_by": "", "item": {}}
    source_folo = folo_source_link_for_row(row, source_index) if source_index else {"url": "", "matched_by": "", "item": {}}
    collection_type = row_collection_type(row)
    is_watch_only = collection_type == "官网观察源"
    resolved_folo_url = "" if is_watch_only else direct_folo_url or linked_folo.get("url", "") or source_folo.get("url", "")
    folo_matched_by = "" if is_watch_only else "row_id" if direct_folo_url else linked_folo.get("matched_by", "") or source_folo.get("matched_by", "")
    has_article_folo = False if is_watch_only else bool(direct_folo_url or linked_folo.get("url", ""))
    return {
        "id": record_id,
        "kind": kind,
        "title": title or source or path.name,
        "body": compact_text(summary or tag_text or meta, 700),
        "meta": meta,
        "url": url,
        "folo_url": resolved_folo_url,
        "folo_matched": bool(resolved_folo_url),
        "folo_label": "Folo 看原条" if has_article_folo else "Folo 源列表" if resolved_folo_url else "",
        "timestamp": timestamp,
        "search_text": search_text,
        "payload": {
            "index": row_index + 1,
            "published_at": published_at,
            "发布时间": published_at,
            "recorded_at": recorded_at,
            "记录时间": recorded_at,
            "source": source,
            "来源名称": source,
            "folo_folder": folder,
            "Folo文件夹路径": folder,
            "source_file": str(path),
            "source_file_name": path.name,
            "url": url,
            "collection_type": collection_type,
            "school_category": first_value(row, ["school_category"]),
            "detected_at": first_value(row, ["detected_at"]),
            "last_seen_at": first_value(row, ["last_seen_at"]),
            "is_new": first_value(row, ["is_new"]),
            "folo_article_url": resolved_folo_url,
            "folo_link_matched_by": folo_matched_by,
            "folo_article_matched": has_article_folo,
        },
    }


def search_record_from_document(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    text = compact_text(raw)
    if not text:
        return None
    published_at, timestamp = parse_index_datetime("", path)
    title = path.stem
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if first_line and len(first_line) <= 120:
        title = first_line.lstrip("# ").strip() or title
    return {
        "id": stable_record_id([str(path), str(path.stat().st_mtime)]),
        "kind": "历史文件",
        "title": title,
        "body": compact_text(text, 1200),
        "meta": file_category(path),
        "url": return_file_url(str(path)) if path.suffix.lower() in ALLOWED_SUFFIXES else "",
        "folo_url": "",
        "folo_matched": False,
        "folo_label": "",
        "timestamp": timestamp,
        "search_text": text,
        "payload": {
            "published_at": published_at,
            "modified_at": published_at,
            "source_file": str(path),
            "source_file_name": path.name,
        },
    }


def iter_search_records_from_file(path: Path, link_index: dict | None = None, source_index: dict | None = None):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader):
                    record = search_record_from_row(row, path, index, link_index, source_index)
                    if record:
                        yield record
        except Exception:
            return
    elif suffix == ".jsonl":
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for index, line in enumerate(handle):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        value = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(value, dict):
                        record = search_record_from_row(value, path, index, link_index, source_index)
                        if record:
                            yield record
        except Exception:
            return
    elif suffix == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            value = None
        rows = value if isinstance(value, list) else value.get("items") if isinstance(value, dict) and isinstance(value.get("items"), list) else []
        if rows:
            for index, row in enumerate(rows):
                if isinstance(row, dict):
                    record = search_record_from_row(row, path, index, link_index, source_index)
                    if record:
                        yield record
        else:
            record = search_record_from_document(path)
            if record:
                yield record
    else:
        record = search_record_from_document(path)
        if record:
            yield record


def build_search_index(force: bool = False) -> dict:
    files = search_index_source_files()
    signature = search_source_signature(files)
    meta = read_json(SEARCH_INDEX_META_JSON)
    if (
        not force
        and SEARCH_INDEX_DB.exists()
        and meta.get("source_count") == signature["source_count"]
        and float(meta.get("source_max_mtime") or 0) >= signature["source_max_mtime"]
        and int(meta.get("source_total_size") or 0) == signature["source_total_size"]
    ):
        return {"ok": True, "rebuilt": False, **meta}
    SEARCH_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    record_count = 0
    link_index = load_folo_article_link_index()
    source_index = load_source_pool_folo_link_index()
    tmp_db = SEARCH_INDEX_DIR / "search_index.sqlite.tmp"
    if tmp_db.exists():
        tmp_db.unlink()
    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        """
        CREATE TABLE records (
            rowid INTEGER PRIMARY KEY,
            id TEXT,
            kind TEXT,
            title TEXT,
            body TEXT,
            meta TEXT,
            url TEXT,
            folo_url TEXT,
            folo_matched INTEGER,
            folo_label TEXT,
            timestamp REAL,
            tokens TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute("CREATE VIRTUAL TABLE records_fts USING fts5(tokens, content='')")
    insert_record = conn.cursor()
    insert_fts = conn.cursor()
    try:
        for path in files:
            for record in iter_search_records_from_file(path, link_index, source_index):
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
                dedupe_key = "||".join(
                    [
                        str(record.get("url") or ""),
                        str(record.get("title") or ""),
                        str(payload.get("source") or payload.get("来源名称") or ""),
                        str(payload.get("published_at") or payload.get("发布时间") or ""),
                    ]
                ).lower()
                if not dedupe_key.strip("|"):
                    dedupe_key = str(record.get("id") or "")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                record_count += 1
                rowid = record_count
                tokens = search_tokens_for_text(
                    " ".join(
                        [
                            str(record.get("title", "")),
                            str(record.get("body", "")),
                            str(record.get("meta", "")),
                            str(record.get("search_text", "")),
                        ]
                    )
                )
                insert_record.execute(
                    """
                    INSERT INTO records (
                        rowid, id, kind, title, body, meta, url, folo_url,
                        folo_matched, folo_label, timestamp, tokens, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rowid,
                        record.get("id", ""),
                        record.get("kind", ""),
                        record.get("title", ""),
                        record.get("body", ""),
                        record.get("meta", ""),
                        record.get("url", ""),
                        record.get("folo_url", ""),
                        1 if record.get("folo_matched") else 0,
                        record.get("folo_label", ""),
                        float(record.get("timestamp") or 0),
                        tokens,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                insert_fts.execute("INSERT INTO records_fts(rowid, tokens) VALUES (?, ?)", (rowid, tokens))
        conn.execute("CREATE INDEX idx_records_timestamp ON records(timestamp DESC, rowid DESC)")
        conn.commit()
    finally:
        conn.close()
    if SEARCH_INDEX_DB.exists():
        SEARCH_INDEX_DB.unlink()
    tmp_db.replace(SEARCH_INDEX_DB)
    SEARCH_RESULT_CACHE.clear()
    if SEARCH_INDEX_JSONL.exists():
        try:
            SEARCH_INDEX_JSONL.unlink()
        except OSError:
            pass
    next_meta = {
        **signature,
        "record_count": record_count,
        "built_at": now_iso(),
        "index_file": str(SEARCH_INDEX_DB),
    }
    SEARCH_INDEX_META_JSON.write_text(json.dumps(next_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    global SEARCH_INDEX_CACHE, SEARCH_INDEX_CACHE_STATE
    SEARCH_INDEX_CACHE = None
    SEARCH_INDEX_CACHE_STATE = None
    return {"ok": True, "rebuilt": True, **next_meta}


def load_search_index() -> list[dict]:
    global SEARCH_INDEX_CACHE, SEARCH_INDEX_CACHE_STATE
    build_search_index(force=False)
    if not SEARCH_INDEX_JSONL.exists():
        return []
    stat = SEARCH_INDEX_JSONL.stat()
    state = (stat.st_mtime, stat.st_size)
    if SEARCH_INDEX_CACHE is not None and SEARCH_INDEX_CACHE_STATE == state:
        return SEARCH_INDEX_CACHE
    rows: list[dict] = []
    with SEARCH_INDEX_JSONL.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except Exception:
                continue
            if isinstance(value, dict):
                value["_search_text_lc"] = " ".join(
                    [
                        str(value.get("title", "")),
                        str(value.get("body", "")),
                        str(value.get("meta", "")),
                        str(value.get("search_text", "")),
                    ]
                ).lower()
                rows.append(value)
    SEARCH_INDEX_CACHE = rows
    SEARCH_INDEX_CACHE_STATE = state
    return rows


def index_match_score(query: str, record: dict, mode: str = "smart") -> int:
    terms = query_terms(query, mode)
    if not terms:
        return 0
    haystack = str(record.get("_search_text_lc") or "")
    if not haystack:
        haystack = " ".join(
            [
                str(record.get("title", "")),
                str(record.get("body", "")),
                str(record.get("meta", "")),
                str(record.get("search_text", "")),
            ]
        ).lower()
    score = 0
    for term, weight in terms.items():
        count = haystack.count(term)
        if count:
            score += weight + min(count, 8)
    normalized = " ".join((query or "").strip().split()).lower()
    if normalized and normalized in str(record.get("title", "")).lower():
        score += 12
    elif normalized and normalized in haystack:
        score += 8
    return score


def personal_search_priority(query: str, record: dict) -> int:
    normalized = " ".join((query or "").strip().split()).lower()
    if not normalized:
        return 0
    haystack = " ".join(
        [
            str(record.get("title", "")),
            str(record.get("body", "")),
            str(record.get("meta", "")),
            json.dumps(record.get("payload") or {}, ensure_ascii=False),
        ]
    ).lower()
    school_query = any(
        term in normalized
        for term in [
            "学校",
            "校园",
            "学院",
            "大学",
            "山西晋中理工",
            "晋中理工",
            "sxjzit",
            "教务",
            "学工",
            "团委",
            "奖学金",
            "助学金",
            "入团",
            "团员",
            "评优",
            "评先",
            "比赛",
            "竞赛",
            "挑战杯",
            "创新创业",
            "就业",
            "招聘",
            "实习",
            "实践",
            "毕业",
        ]
    )
    if school_query and any(term in haystack for term in ["山西晋中理工", "晋中理工", "sxjzit", "我的学校"]):
        return 3
    job_query = any(term in normalized for term in ["招聘", "就业", "校招", "岗位", "实习"])
    if job_query and any(term in haystack for term in ["山西焦煤", "霍州煤电", "晋能控股", "潞安", "太重", "山西晋中理工"]):
        return 2
    cert_query = any(term in normalized for term in ["证书", "电工证", "技能补贴", "职业技能", "报名"])
    if cert_query and any(term in haystack for term in ["低压电工", "高压电工", "特种作业", "技能补贴", "山西人社"]):
        return 2
    return 0


def history_search_sort_key(item: dict) -> tuple[int, float, int, str]:
    return (
        int(item.get("_personal_priority", 0) or 0),
        search_record_timestamp(item),
        int(item.get("score", 0) or 0),
        str(item.get("kind", "")),
    )


def search_history_records(query: str, limit: int, offset: int, mode: str = "smart") -> dict:
    if not SEARCH_INDEX_DB.exists():
        build_search_index(force=False)
    if not SEARCH_INDEX_DB.exists():
        return {"total": 0, "results": []}
    query_tokens = query_search_token_set(query, mode)
    if not query_tokens:
        return {"total": 0, "results": []}
    conn = sqlite3.connect(SEARCH_INDEX_DB)
    conn.row_factory = sqlite3.Row
    results: list[dict] = []
    matched_count = 0
    has_more = False

    def record_from_db_row(row: sqlite3.Row) -> dict:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        return {
            "kind": row["kind"],
            "title": row["title"],
            "body": row["body"],
            "meta": row["meta"],
            "url": row["url"],
            "folo_url": row["folo_url"],
            "folo_matched": bool(row["folo_matched"]),
            "folo_label": row["folo_label"],
            "payload": payload,
        }

    def scan_records_by_timestamp() -> dict:
        scan_candidates: list[dict] = []
        scan_matched_count = 0
        scan_has_more = False
        candidate_limit = max(300, (offset + limit) * 20)
        rows = conn.execute(
            """
            SELECT
                kind, title, body, meta, url, folo_url,
                folo_matched, folo_label, timestamp, tokens, payload_json
            FROM records
            ORDER BY timestamp DESC, rowid DESC
            """
        )
        for row in rows:
            record_tokens = set(str(row["tokens"] or "").split())
            if not query_tokens.intersection(record_tokens):
                continue
            record = record_from_db_row(row)
            if is_generated_summary_title(str(record.get("title") or "")) and not allow_generated_summary:
                continue
            search_text = " ".join([str(row["title"] or ""), str(row["body"] or ""), str(row["meta"] or "")])
            record["score"] = index_match_score(query, {**record, "search_text": search_text}, mode)
            if record["score"] <= 0:
                continue
            record["_personal_priority"] = personal_search_priority(query, record)
            scan_candidates.append(record)
            if len(scan_candidates) >= candidate_limit:
                scan_has_more = True
                break
        scan_candidates.sort(key=history_search_sort_key, reverse=True)
        scan_results = scan_candidates[offset : offset + limit]
        scan_matched_count = offset + len(scan_results)
        scan_total = offset + len(scan_results) + (1 if scan_has_more else 0)
        return {"total": scan_total, "results": scan_results, "has_more": scan_has_more, "total_is_estimated": scan_has_more}

    try:
        normalized = " ".join((query or "").strip().split())
        allow_generated_summary = "inforadar" in normalized.lower()
        use_phrase_search = len(normalized) >= 8 or (mode == "exact" and len(normalized) >= 2 and not normalized.isascii())
        if use_phrase_search:
            phrase_like = f"%{normalized}%"
            phrase_limit = 5000 if mode == "exact" else offset + limit + 1
            phrase_rows = conn.execute(
                """
                SELECT
                    kind, title, body, meta, url, folo_url,
                    folo_matched, folo_label, timestamp, tokens, payload_json
                FROM records
                WHERE title LIKE ? OR body LIKE ? OR meta LIKE ? OR payload_json LIKE ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ?
                """,
                (phrase_like, phrase_like, phrase_like, phrase_like, phrase_limit),
            )
            phrase_results: list[dict] = []
            for row in phrase_rows:
                record = record_from_db_row(row)
                if is_generated_summary_title(str(record.get("title") or "")) and not allow_generated_summary:
                    continue
                search_text = " ".join([str(row["title"] or ""), str(row["body"] or ""), str(row["meta"] or "")])
                record["score"] = index_match_score(query, {**record, "search_text": search_text}, mode)
                if record["score"] > 0:
                    record["_personal_priority"] = personal_search_priority(query, record)
                    phrase_results.append(record)
            if phrase_results:
                phrase_results.sort(key=history_search_sort_key, reverse=True)
                sliced = phrase_results[offset : offset + limit]
                return {
                    "total": len(phrase_results) if len(phrase_results) < phrase_limit else offset + len(sliced) + 1,
                    "results": sliced,
                    "has_more": len(phrase_results) > offset + limit or len(phrase_results) >= phrase_limit,
                    "total_is_estimated": len(phrase_results) >= phrase_limit,
                }

        if mode != "exact" and len(query_terms(query, mode)) >= 4:
            return scan_records_by_timestamp()

        fts_query = fts_query_for_search(query, mode)
        if fts_query:
            try:
                candidate_limit = min(600, max(160, (offset + limit) * 16))
                fts_rows = list(
                    conn.execute(
                        """
                        SELECT
                            r.kind, r.title, r.body, r.meta, r.url, r.folo_url,
                            r.folo_matched, r.folo_label, r.timestamp, r.tokens, r.payload_json
                        FROM records_fts
                        JOIN records r ON r.rowid = records_fts.rowid
                        WHERE records_fts MATCH ?
                        ORDER BY r.timestamp DESC, r.rowid DESC
                        LIMIT ?
                        """,
                        (fts_query, candidate_limit),
                    )
                )
                fts_results: list[dict] = []
                for row in fts_rows:
                    record = record_from_db_row(row)
                    if is_generated_summary_title(str(record.get("title") or "")) and not allow_generated_summary:
                        continue
                    search_text = " ".join([str(row["title"] or ""), str(row["body"] or ""), str(row["meta"] or "")])
                    record["score"] = index_match_score(query, {**record, "search_text": search_text}, mode)
                    if record["score"] > 0:
                        record["_personal_priority"] = personal_search_priority(query, record)
                        fts_results.append(record)
                fts_results.sort(key=history_search_sort_key, reverse=True)
                sliced = fts_results[offset : offset + limit]
                return {
                    "total": offset + len(sliced) + (1 if len(fts_results) > offset + limit or len(fts_rows) >= candidate_limit else 0),
                    "results": sliced,
                    "has_more": len(fts_results) > offset + limit or len(fts_rows) >= candidate_limit,
                    "total_is_estimated": True,
                }
            except sqlite3.OperationalError:
                pass

        scanned = scan_records_by_timestamp()
        results = scanned.get("results", [])
        has_more = bool(scanned.get("has_more"))
    finally:
        conn.close()
    known_total = offset + len(results) + (1 if has_more else 0)
    return {"total": known_total, "results": results, "has_more": has_more, "total_is_estimated": has_more}


QUERY_EXPANSION_GROUPS = [
    ["政治", "政策", "时政", "政务", "政府", "国务院", "官方公告", "法规", "规划", "补贴", "人社"],
    ["学校", "校园", "学院", "大学", "山西晋中理工学院", "晋中理工", "教务", "学工", "团委", "奖学金", "助学金", "入团", "团员", "评优", "评先", "比赛", "竞赛", "挑战杯", "创新创业", "互联网+", "考试", "就业", "招聘", "实习", "实践", "毕业"],
    ["购物", "消费", "优惠", "折扣", "价格", "补贴", "电商", "京东", "淘宝", "拼多多", "数码", "装备"],
    ["风险", "避坑", "诈骗", "虚假", "隐私", "预警", "提醒", "投诉", "维权"],
    ["网络安全", "安全", "漏洞", "攻击", "隐私", "账号", "数据泄露", "钓鱼", "诈骗"],
    ["法律", "权益", "维权", "法规", "合同", "劳动", "消费者", "投诉"],
    ["AI", "人工智能", "大模型", "OpenAI", "ChatGPT", "Codex", "Agent", "智能体", "自动化"],
]


def query_terms(query: str, mode: str = "smart") -> dict[str, int]:
    normalized = " ".join((query or "").strip().split())
    lower_query = normalized.lower()
    selected_mode = mode if mode in {"exact", "smart", "fuzzy"} else "smart"
    terms: dict[str, int] = {}

    def add(term: str, weight: int) -> None:
        value = str(term or "").strip()
        if not value:
            return
        if len(value) == 1 and not value.isascii():
            return
        key = value.lower()
        terms[key] = max(terms.get(key, 0), weight)

    add(normalized, 6)
    for part in re.split(r"\s+", normalized):
        add(part, 5)

    if selected_mode != "exact":
        for group in QUERY_EXPANSION_GROUPS:
            matched = False
            for keyword in group:
                key = keyword.lower()
                if key and (key in lower_query or lower_query in key):
                    matched = True
                    break
            if matched:
                is_school_group = "山西晋中理工学院" in group
                expansion_terms = group if selected_mode == "fuzzy" or is_school_group else group[:8]
                for keyword in expansion_terms:
                    add(keyword, 2 if selected_mode == "smart" else 3)

    return terms


def match_score(query: str, record: dict, mode: str = "smart") -> int:
    haystack = text_blob(record).lower()
    terms = query_terms(query, mode)
    if not terms:
        return 0
    score = 0
    for term, weight in terms.items():
        if term in haystack:
            score += weight
    if query.lower() in haystack:
        score += 8
    return score


def folo_search_url(query: str) -> str:
    normalized = " ".join((query or "").strip().split())
    return FOLO_APP_URL + ("?q=" + quote_plus(normalized) if normalized else "")


def return_file_url(path: str) -> str:
    return "/api/file?path=" + quote_plus(path or "")


def search_personal_radar(query: str, scope: str = "all", limit: int = 30, offset: int = 0, mode: str = "smart") -> dict:
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return {"ok": True, "query": "", "scope": scope, "results": [], "total": 0, "offset": 0, "limit": limit}

    allowed_scopes = {"all", "intel", "history", "files", "manual", "watch", "sources"}
    selected_scope = scope if scope in allowed_scopes else "all"
    selected_mode = mode if mode in {"exact", "smart", "fuzzy"} else "smart"
    safe_limit = max(1, min(int(limit or 30), 80))
    safe_offset = max(0, int(offset or 0))
    index_state = (0, 0)
    if SEARCH_INDEX_DB.exists():
        try:
            stat = SEARCH_INDEX_DB.stat()
            index_state = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            index_state = (0, 0)
    cache_key = (normalized.lower(), selected_scope, selected_mode, safe_limit, safe_offset, index_state)
    cached = SEARCH_RESULT_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= SEARCH_RESULT_CACHE_TTL_SECONDS:
        return {**cached[1], "cache_hit": True}

    results: list[dict] = []
    history_total: int | None = None
    history_page_full = False

    def include(target: str) -> bool:
        return selected_scope in {"all", target} or (selected_scope == "intel" and target == "history")

    def add(
        kind: str,
        title: str,
        body: str,
        meta: str = "",
        url: str = "",
        payload: dict | None = None,
        folo_url: str = "",
        folo_matched: bool = False,
        folo_label: str = "",
    ) -> None:
        record = {
            "kind": kind,
            "title": title or "未命名",
            "body": body or "",
            "meta": meta or "",
            "url": url or "",
            "folo_url": folo_url or "",
            "folo_matched": bool(folo_matched),
            "folo_label": folo_label or ("打开 Folo 源" if folo_matched else ""),
            "payload": payload or {},
        }
        score = match_score(normalized, record, selected_mode)
        if score > 0:
            record["score"] = score
            results.append(record)

    if include("history"):
        history = search_history_records(normalized, safe_limit, safe_offset, selected_mode)
        history_total = int(history.get("total") or 0)
        history_total_estimated = bool(history.get("total_is_estimated"))
        history_has_more = bool(history.get("has_more"))
        results.extend(history.get("results") or [])
        history_page_full = selected_scope in {"all", "intel"} and len(results) >= safe_limit

    if safe_offset == 0 and include("intel") and not history_page_full:
        for item in latest_intel_items("", 120, resolve_folo_links=False).get("items", []):
            has_folo_article = bool(item.get("folo_article_url") or item.get("folo_url"))
            add(
                "情报",
                item.get("title", ""),
                " / ".join(filter(None, [item.get("why", ""), item.get("action", ""), item.get("folo_folder", "")])),
                " · ".join(filter(None, [item.get("section", ""), item.get("source", ""), f"评分 {item.get('score', '-')}" ])),
                item.get("article_url", ""),
                item,
                item.get("folo_url", ""),
                has_folo_article,
                "Folo 看原条" if has_folo_article else "Folo 原条待补",
            )

    if safe_offset == 0 and include("files") and not history_page_full:
        for file in list_return_files(200):
            add(
                "文件",
                file.get("name", ""),
                file.get("path", ""),
                " · ".join(filter(None, [file.get("category", ""), file.get("size_text", ""), file.get("modified_at", "")])),
                return_file_url(file.get("path", "")),
                file,
            )

    if safe_offset == 0 and include("manual") and not history_page_full:
        manual = manual_inbox_summary()
        for item in manual.get("recent_items", []):
            add(
                "收集",
                item.get("raw_text") or item.get("标题") or item.get("source_trace_id", ""),
                text_blob(item),
                " · ".join(filter(None, [str(item.get("platform", "")), str(item.get("status", "")), str(item.get("collected_at", ""))])),
                "",
                item,
            )
        if manual.get("summary"):
            add("收集摘要", "收集箱摘要", manual.get("summary", ""), "", "", manual)

    if safe_offset == 0 and include("watch") and not history_page_full:
        watch = watch_summary()
        for item in [*watch.get("updates", []), *watch.get("requests", [])]:
            add(
                "监控",
                item.get("title") or item.get("关键词") or item.get("watch_keyword", ""),
                text_blob(item),
                " · ".join(filter(None, [str(item.get("source_name", "")), str(item.get("状态", "")), str(item.get("detected_at", ""))])),
                "",
                item,
            )

    if safe_offset == 0 and include("sources") and not history_page_full:
        source_pool = source_pool_summary(include_folo_links=False)
        feed_index = load_folo_feed_index()
        for file in source_pool.get("files", []):
            add(
                "源池文件",
                file.get("name", ""),
                file.get("path", ""),
                " · ".join(filter(None, [file.get("category", ""), file.get("size_text", ""), file.get("modified_at", "")])),
                "",
                file,
            )
        for row in source_pool.get("source_pool_strategy_csv", []):
            folo = folo_link_for_row(row, feed_index)
            add(
                "源池",
                row.get("来源名称") or row.get("name") or row.get("source_name", ""),
                text_blob(row),
                row.get("策略") or row.get("strategy") or "",
                row.get("订阅源URL") or row.get("url") or "",
                row,
                folo.get("url", ""),
                bool(folo.get("matched")),
                "打开 Folo 源" if folo.get("matched") else "Folo 搜源",
            )

    unique: list[dict] = []
    seen: set[str] = set()
    for item in results:
        title_text = str(item.get("title") or "").strip()
        if is_generated_summary_title(title_text) and "inforadar" not in normalized.lower():
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        key = "||".join(
            [
                str(item.get("url") or payload.get("url") or ""),
                str(item.get("title") or ""),
                str(payload.get("source") or payload.get("来源名称") or ""),
                str(payload.get("published_at") or payload.get("发布时间") or payload.get("modified_at") or ""),
            ]
        ).lower()
        if not key.strip("|"):
            key = f"{item.get('kind')}||{item.get('title')}||{item.get('meta')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda item: (int(item.get("_personal_priority", 0) or 0), search_record_timestamp(item), int(item.get("score", 0)), item.get("kind", "")), reverse=True)
    clipped = unique[:safe_limit] if history_total is not None else unique[safe_offset : safe_offset + safe_limit]
    total = history_total if history_total is not None else len(unique)
    response = {
        "ok": True,
        "query": normalized,
        "mode": selected_mode,
        "related_terms": [term for term in query_terms(normalized, selected_mode).keys() if term != normalized.lower()][:12],
        "scope": selected_scope,
        "total": total,
        "offset": safe_offset,
        "limit": safe_limit,
        "has_more": history_has_more if history_total is not None else safe_offset + safe_limit < total,
        "total_is_estimated": history_total_estimated if history_total is not None else False,
        "results": clipped,
    }
    if len(SEARCH_RESULT_CACHE) >= SEARCH_RESULT_CACHE_MAX_ITEMS:
        oldest_key = min(SEARCH_RESULT_CACHE, key=lambda key: SEARCH_RESULT_CACHE[key][0])
        SEARCH_RESULT_CACHE.pop(oldest_key, None)
    SEARCH_RESULT_CACHE[cache_key] = (now, response)
    return response
