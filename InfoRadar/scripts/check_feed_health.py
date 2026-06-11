#!/usr/bin/env python3
import argparse
import os
import csv
import os
import datetime as dt
import os
import json
import os
import re
import os
import shutil
import socket
import os
import subprocess
import time
import os
import urllib.error
import os
import urllib.request
import os
import xml.etree.ElementTree as ET
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import rsshub_tools
import os
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_POOL = ROOT / "sources" / "source_pool_from_folo.csv"
RAW_RSS_DIR = ROOT / "data" / "raw" / "rss_items"
DEFAULT_RETURN_DIR = Path(r"G:\E盘\工作项目文件\NAS回传\FOLO") if os.name == "nt" else Path("/home/mana/inforadar-return/FOLO")
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", str(DEFAULT_RETURN_DIR)))
LOG_DIR = ROOT / "logs"
STRATEGY_CSV = ROOT / "sources" / "source_pool_strategy.csv"
STRATEGY_XLSX = ROOT / "sources" / "source_pool_strategy.xlsx"


HEADERS = [
    "源名称",
    "原始RSS链接",
    "实际抓取URL",
    "RSS链接",
    "Folo文件夹路径",
    "抓取策略",
    "是否抓取成功",
    "HTTP状态",
    "错误类型",
    "错误详情",
    "最近成功时间",
    "是否使用缓存",
    "失败次数",
    "RSSHub实例",
    "是否建议替换",
    "是否建议废弃",
    "建议处理方式",
]

STRATEGY_HEADERS = [
    "源名称",
    "RSS链接",
    "Folo文件夹路径",
    "当前状态",
    "抓取策略",
    "推荐权重",
    "最近成功时间",
    "连续失败次数",
    "建议动作",
    "备注",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def source_url(row: dict) -> str:
    return (row.get("可抓取RSS链接") or row.get("RSS链接") or "").strip()


def normalize_key(name: str, url: str) -> str:
    return f"{name.strip().lower()}|{url.strip().lower()}"


def source_key(row: dict) -> str:
    return normalize_key(row.get("源名称") or row.get("Folo订阅源名称") or "", source_url(row))


def decode_response(data: bytes, headers) -> str:
    content_type = headers.get("Content-Type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, re.I)
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8", "gb18030"])
    for encoding in encodings:
        try:
            return data.decode(encoding, errors="strict")
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def count_feed_items(xml_text: str) -> int:
    root = ET.fromstring(xml_text.encode("utf-8"))
    return sum(1 for elem in root.iter() if local_name(elem.tag) in ("item", "entry"))


def classify_error(url: str, http_status: str, error: str, strategy: str = "") -> str:
    error_lower = f"{http_status} {error} {strategy}".lower()
    if not rsshub_tools.is_http_url(url):
        return "URL异常"
    if http_status == "403":
        return "403访问限制"
    if http_status == "404":
        return "404源失效"
    if "timed out" in error_lower or "timeout" in error_lower:
        return "网络超时"
    if "empty" in error_lower or "0 items" in error_lower:
        return "空内容"
    if "xml" in error_lower or "parse" in error_lower or "mismatched tag" in error_lower:
        return "XML解析失败"
    if "decode" in error_lower or "encoding" in error_lower or "codec" in error_lower:
        return "编码错误"
    if strategy == "rsshub_primary":
        return "RSSHub主实例失败"
    if strategy == "rsshub_backup":
        return "RSSHub备用实例失败"
    return "未知错误"


def source_score(source: dict) -> int:
    for key in ("长期价值评分", "来源权威度"):
        raw = str(source.get(key) or "").strip()
        if raw.isdigit():
            return int(raw)
    return 50


def is_official_source(source: dict) -> bool:
    hay = " ".join(
        str(source.get(key, ""))
        for key in ["源名称", "官网链接", "Folo文件夹路径", "主分类", "标签", "备注"]
    )
    return any(token in hay for token in ["gov.cn", "edu.cn", "政府", "人社", "教育厅", "工信", "学校", "学院", "官网"])


def is_sensitive_or_low_value_source(source: dict) -> bool:
    hay = " ".join(
        str(source.get(key, ""))
        for key in ["源名称", "官网链接", "Folo文件夹路径", "主分类", "标签", "备注"]
    )
    blocked_terms = [
        "泄密",
        "私密",
        "自拍福利",
        "成人",
        "裸",
        "写真",
        "AV视频",
        "网盘影视",
        "高品质影视",
        "影视站",
        "侵权资源",
    ]
    return any(term in hay for term in blocked_terms)


def finalize_strategy(source: dict, row: dict) -> None:
    success = row.get("是否抓取成功") == "是"
    error_type = row.get("错误类型", "")
    cache_available = row.get("是否使用缓存") == "是"
    current_strategy = row.get("抓取策略") or rsshub_tools.source_fetch_strategy(source)
    score = source_score(source)

    row["是否建议替换"] = "否"
    row["是否建议废弃"] = "否"

    if is_sensitive_or_low_value_source(source):
        row["抓取策略"] = "disabled"
        row["是否建议废弃"] = "是"
        row["建议处理方式"] = "敏感/低价值/可能侵权来源；不尝试备用 RSSHub，建议从 InfoRadar 源池废弃。"
        return

    if success:
        row["建议处理方式"] = "保留；当前抓取正常。"
        return

    if error_type == "URL异常":
        row["抓取策略"] = "replace_needed"
        row["是否建议替换"] = "是"
        row["建议处理方式"] = "RSS/URL 格式异常；需要重新查找可用 RSS 或保留官网人工查看。"
        return

    if cache_available:
        row["建议处理方式"] = "暂用缓存兜底；仍需修复 RSS 或替换来源，避免长期只靠旧内容。"

    if error_type == "403访问限制":
        if current_strategy.startswith("rsshub_"):
            row["抓取策略"] = current_strategy
            row["是否建议替换"] = "是"
            row["建议处理方式"] = row.get("建议处理方式") or "RSSHub/上游返回 403；不硬绕访问控制，尝试备用 RSSHub、自建 RSSHub 或替换公开 RSS。"
        elif is_official_source(source):
            row["抓取策略"] = "official_page"
            row["建议处理方式"] = row.get("建议处理方式") or "官方网站无稳定 RSS 或限制抓取；保留人工核验/后续官网监控。"
        elif score < 45:
            row["抓取策略"] = "disabled"
            row["是否建议废弃"] = "是"
            row["建议处理方式"] = row.get("建议处理方式") or "低价值源且 403；建议废弃或降权。"
        else:
            row["抓取策略"] = "replace_needed"
            row["是否建议替换"] = "是"
            row["建议处理方式"] = row.get("建议处理方式") or "不绕过 403；搜索替代 RSS、官方源或 GitHub/文档更新 Atom。"
        return

    if error_type in ("404源失效", "XML解析失败"):
        row["抓取策略"] = "replace_needed"
        row["是否建议替换"] = "是"
        if score < 45:
            row["是否建议废弃"] = "是"
        row["建议处理方式"] = row.get("建议处理方式") or "RSS 地址失效或不是标准 Feed；需要替换 RSS，低价值源可废弃。"
        return

    if error_type in ("RSSHub主实例失败", "RSSHub备用实例失败"):
        row["抓取策略"] = current_strategy if current_strategy.startswith("rsshub_") else "rsshub_primary"
        row["是否建议替换"] = "是"
        row["建议处理方式"] = row.get("建议处理方式") or "检查 RSSHub 路由，配置备用/自建 RSSHub；若仍失败则替换源。"
        return

    if error_type == "网络超时":
        row["建议处理方式"] = row.get("建议处理方式") or "保留观察；降低并发或稍后复测，连续失败后替换。"
        return

    if error_type == "空内容":
        row["建议处理方式"] = row.get("建议处理方式") or "保留观察；若连续空内容则降权或替换。"
        return

    row["建议处理方式"] = row.get("建议处理方式") or "保留观察；累计失败后再降权、替换或废弃。"


def load_status_history() -> dict[str, dict]:
    history: dict[str, dict] = {}
    files = sorted(RAW_RSS_DIR.glob("fetch_status_*.csv"), key=lambda p: p.stat().st_mtime)
    for path in files:
        checked_at = dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        try:
            rows = read_csv(path)
        except Exception as exc:
            append_jsonl(LOG_DIR / "check_feed_health_errors.jsonl", {"file": str(path), "error": repr(exc)})
            continue
        for row in rows:
            name = row.get("源名称", "")
            url = row.get("可抓取RSS链接") or row.get("实际抓取URL") or row.get("原始RSS链接") or ""
            key = normalize_key(name, url)
            stat = history.setdefault(key, {"failures": 0, "last_success": "", "last_status": ""})
            if row.get("状态") == "success":
                stat["last_success"] = checked_at
            else:
                stat["failures"] += 1
            stat["last_status"] = row.get("状态", "")
    return history


def load_cache_keys() -> set[str]:
    keys: set[str] = set()
    files = sorted(RAW_RSS_DIR.glob("folo_items_real*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
    for path in files:
        try:
            rows = read_csv(path)
        except Exception:
            continue
        for row in rows:
            name = row.get("来源名称") or row.get("Folo订阅源名称") or ""
            for url in [row.get("订阅源URL") or "", row.get("原始RSS链接") or "", row.get("实际抓取URL") or ""]:
                if url:
                    keys.add(normalize_key(name, url))
    return keys


def probe_url_with_curl(url: str, timeout: int, max_bytes: int) -> tuple[bool, str, str, str] | None:
    curl = shutil.which("curl")
    if not curl:
        return None
    marker = b"\n__INFORADAR_HTTP_STATUS__:"
    cmd = [
        curl,
        "-L",
        "--silent",
        "--show-error",
        "--max-time",
        str(max(1, timeout)),
        "--connect-timeout",
        str(max(1, min(timeout, 4))),
        "--range",
        f"0-{max_bytes}",
        "-A",
        "InfoRadarFeedHealth/0.3",
        "-H",
        "Accept: application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "-w",
        "\n__INFORADAR_HTTP_STATUS__:%{http_code}",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(2, timeout + 3),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return False, "ERR", "网络超时", f"curl timeout after {timeout}s: {exc!r}"[:220]
    except Exception as exc:
        return None

    raw = proc.stdout or b""
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    content = raw
    status = "ERR"
    if marker in raw:
        content, status_raw = raw.rsplit(marker, 1)
        status = status_raw.decode("ascii", errors="ignore").strip() or "ERR"
    if proc.returncode != 0 and not content:
        return False, status, "", (stderr or f"curl returncode={proc.returncode}")[:220]
    if status.isdigit() and int(status) >= 400:
        return False, status, "", (stderr or f"HTTP {status}")[:220]
    if not content:
        return False, status, "空内容", "empty response"
    try:
        xml_text = decode_response(content[:max_bytes], {"Content-Type": ""})
        item_count = count_feed_items(xml_text)
    except ET.ParseError as exc:
        return False, status, "XML解析失败", repr(exc)[:220]
    except UnicodeError as exc:
        return False, "ERR", "编码错误", repr(exc)[:220]
    except Exception as exc:
        return False, status, "", repr(exc)[:220]
    if item_count <= 0:
        return False, status, "空内容", "0 items"
    return True, status, "", f"{item_count} items"


def probe_url(url: str, timeout: int, max_bytes: int) -> tuple[bool, str, str, str]:
    curl_result = probe_url_with_curl(url, timeout, max_bytes)
    if curl_result is not None:
        return curl_result
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "InfoRadarFeedHealth/0.2",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = str(getattr(resp, "status", 0) or resp.getcode())
            data = resp.read(max_bytes + 1)
            if not data:
                return False, status, "空内容", "empty response"
            xml_text = decode_response(data[:max_bytes], resp.headers)
            item_count = count_feed_items(xml_text)
            if item_count <= 0:
                return False, status, "空内容", "0 items"
            return True, status, "", f"{item_count} items"
    except urllib.error.HTTPError as exc:
        return False, str(exc.code), "", str(exc.reason or exc)
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return False, "ERR", "", repr(exc)[:220]
    except ET.ParseError as exc:
        return False, "200", "XML解析失败", repr(exc)[:220]
    except UnicodeError as exc:
        return False, "ERR", "编码错误", repr(exc)[:220]
    except Exception as exc:
        return False, "ERR", "", repr(exc)[:220]


def probe_source(source: dict, timeout: int, max_bytes: int, history: dict, cache_keys: set[str]) -> dict:
    name = source.get("源名称") or source.get("Folo订阅源名称") or ""
    original = rsshub_tools.original_rss_url(source)
    configured = rsshub_tools.configured_fetch_url(source)
    history_keys = [normalize_key(name, original), normalize_key(name, configured)]
    hist = next((history.get(key, {}) for key in history_keys if history.get(key)), {})
    cache_available = any(key in cache_keys for key in history_keys)
    candidates = rsshub_tools.rsshub_candidates(source)
    first = candidates[0] if candidates else {}
    row = {
        "源名称": name,
        "原始RSS链接": original,
        "实际抓取URL": first.get("实际抓取URL", configured),
        "RSS链接": configured,
        "Folo文件夹路径": source.get("Folo文件夹路径", ""),
        "抓取策略": first.get("抓取策略", rsshub_tools.source_fetch_strategy(source)),
        "是否抓取成功": "否",
        "HTTP状态": "",
        "错误类型": "",
        "错误详情": "",
        "最近成功时间": hist.get("last_success", ""),
        "是否使用缓存": "是" if cache_available else "否",
        "失败次数": hist.get("failures", 0),
        "RSSHub实例": first.get("使用RSSHub实例", ""),
        "是否建议替换": "否",
        "是否建议废弃": "否",
        "建议处理方式": "",
    }

    if not candidates:
        row["错误类型"] = "URL异常"
        row["错误详情"] = "缺少可抓取 HTTP/RSSHub 链接"
        finalize_strategy(source, row)
        return row

    attempts: list[dict] = []
    started = time.time()
    for spec in candidates:
        url = spec.get("实际抓取URL", "")
        ok, http_status, error_type, detail = probe_url(url, timeout, max_bytes)
        attempts.append({**spec, "HTTP状态": http_status, "错误类型": error_type, "错误详情": detail})
        row["实际抓取URL"] = url
        row["RSSHub实例"] = spec.get("使用RSSHub实例", "")
        row["抓取策略"] = spec.get("抓取策略", "")
        row["HTTP状态"] = http_status
        if ok:
            row["是否抓取成功"] = "是"
            row["错误类型"] = ""
            row["错误详情"] = f"{detail}; {round(time.time() - started, 2)}s"
            finalize_strategy(source, row)
            return row

        classified = error_type or classify_error(url, http_status, detail, spec.get("抓取策略", ""))
        row["错误类型"] = classified
        row["错误详情"] = detail

    if attempts:
        last = attempts[-1]
        row["实际抓取URL"] = last.get("实际抓取URL", "")
        row["RSSHub实例"] = last.get("使用RSSHub实例", "")
        row["抓取策略"] = last.get("抓取策略", row.get("抓取策略", ""))
        row["HTTP状态"] = last.get("HTTP状态", "")
        row["错误详情"] = " | ".join(
            f"{item.get('抓取策略')} {item.get('HTTP状态')}: {item.get('错误详情')}" for item in attempts
        )[:500]
        if any(item.get("HTTP状态") == "403" for item in attempts):
            row["错误类型"] = "403访问限制"
        else:
            row["错误类型"] = last.get("错误类型") or classify_error(
                last.get("实际抓取URL", ""),
                last.get("HTTP状态", ""),
                last.get("错误详情", ""),
                last.get("抓取策略", ""),
            )

    finalize_strategy(source, row)
    return row


def strategy_row(source: dict, row: dict) -> dict:
    success = row.get("是否抓取成功") == "是"
    failed_count = int(row.get("失败次数") or 0)
    if success:
        current_status = "success"
        strategy = row.get("抓取策略") or "direct_rss"
    elif row.get("是否使用缓存") == "是":
        current_status = "cache_available"
        strategy = "cache_only"
    else:
        current_status = "failed"
        strategy = row.get("抓取策略") or "replace_needed"

    weight = source_score(source)
    if row.get("是否建议废弃") == "是":
        weight = min(weight, 20)
    elif row.get("是否建议替换") == "是":
        weight = max(20, weight - 10)
    elif success:
        weight = min(100, weight + 5)

    return {
        "源名称": row.get("源名称", ""),
        "RSS链接": row.get("原始RSS链接") or row.get("RSS链接", ""),
        "Folo文件夹路径": row.get("Folo文件夹路径", ""),
        "当前状态": current_status,
        "抓取策略": strategy,
        "推荐权重": weight,
        "最近成功时间": row.get("最近成功时间", ""),
        "连续失败次数": failed_count,
        "建议动作": row.get("建议处理方式", ""),
        "备注": f"HTTP={row.get('HTTP状态')}; 错误={row.get('错误类型')}; 实际抓取URL={row.get('实际抓取URL')}",
    }


def write_markdown(path: Path, rows: list[dict], xlsx_path: Path, strategy_xlsx: Path) -> None:
    total = len(rows)
    success = sum(1 for row in rows if row.get("是否抓取成功") == "是")
    failed = total - success
    by_error: dict[str, int] = {}
    by_strategy: dict[str, int] = {}
    for row in rows:
        by_error[row.get("错误类型") or "成功"] = by_error.get(row.get("错误类型") or "成功", 0) + 1
        by_strategy[row.get("抓取策略") or "未标记"] = by_strategy.get(row.get("抓取策略") or "未标记", 0) + 1

    lines = [
        "# RSS源健康检查",
        "",
        f"生成时间：{now_text()}",
        f"Excel：{xlsx_path}",
        f"源池策略表：{strategy_xlsx}",
        "",
        "## 总览",
        "",
        f"- 源总数：{total}",
        f"- 成功：{success}",
        f"- 失败：{failed}",
        f"- 成功率：{round(success / total, 4) if total else 0}",
        "",
        "## 错误类型分布",
        "",
        "| 错误类型 | 数量 |",
        "|---|---:|",
    ]
    for key, count in sorted(by_error.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## 抓取策略分布", "", "| 抓取策略 | 数量 |", "|---|---:|"])
    for key, count in sorted(by_strategy.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## 建议优先处理的失败源", "", "| 源名称 | 错误类型 | 策略 | 失败次数 | 缓存 | 建议 |", "|---|---|---|---:|---|---|"])
    for row in sorted(rows, key=lambda r: (r.get("是否抓取成功") == "是", -int(r.get("失败次数") or 0), r.get("源名称", "")))[:30]:
        if row.get("是否抓取成功") == "是":
            continue
        lines.append(
            f"| {row.get('源名称')} | {row.get('错误类型')} | {row.get('抓取策略')} | {row.get('失败次数')} | {row.get('是否使用缓存')} | {row.get('建议处理方式')} |"
        )

    lines.extend(["", "## 高价值保留源", "", "| 源名称 | Folo位置 | 策略 | 最近成功时间 | 缓存 |", "|---|---|---|---|---|"])
    for row in rows:
        if row.get("是否抓取成功") == "是":
            lines.append(f"| {row.get('源名称')} | {row.get('Folo文件夹路径')} | {row.get('抓取策略')} | {row.get('最近成功时间')} | {row.get('是否使用缓存')} |")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_governance_report(path: Path, rows: list[dict], strategy_rows: list[dict], url_anomaly_count: int = 0) -> None:
    total = len(rows)
    success = [row for row in rows if row.get("是否抓取成功") == "是"]
    failed = [row for row in rows if row.get("是否抓取成功") != "是"]
    direct_success = sum(1 for row in success if row.get("抓取策略") == "direct_rss")
    rsshub_primary_success = sum(1 for row in success if row.get("抓取策略") == "rsshub_primary")
    rsshub_backup_success = sum(1 for row in success if row.get("抓取策略") == "rsshub_backup")
    forbidden = sum(1 for row in rows if row.get("错误类型") == "403访问限制")
    replace_count = sum(1 for row in rows if row.get("是否建议替换") == "是")
    disabled_count = sum(1 for row in strategy_rows if row.get("抓取策略") == "disabled" or "废弃" in row.get("建议动作", ""))
    manual = [row for row in rows if row.get("抓取策略") in ("official_page", "replace_needed", "disabled") or row.get("是否建议替换") == "是"]

    lines = [
        "# RSSHub备用与403源治理报告",
        "",
        f"生成时间：{now_text()}",
        "",
        "## 核心数字",
        "",
        f"- 总源数：{total}",
        f"- 直接RSS成功数：{direct_success}",
        f"- RSSHub主实例成功数：{rsshub_primary_success}",
        f"- RSSHub备用实例成功数：{rsshub_backup_success}",
        f"- 仍失败数量：{len(failed)}",
        f"- 403数量：{forbidden}",
        f"- 建议替换数量：{replace_count}",
        f"- 建议废弃数量：{disabled_count}",
        f"- URL异常修复/标记数量：{url_anomaly_count}",
        "",
        "## 原则",
        "",
        "- 403 源不硬绕过登录、验证码、付费墙、访问控制或反爬限制。",
        "- RSSHub 源优先尝试配置中的 primary/backups；失败后进入替换、自建或人工核验流程。",
        "- 官方但无稳定 RSS 的源保留为 official_page，后续可做官网监控，不当作可稳定抓取 RSS。",
        "",
        "## 下一步需要人工处理的源清单",
        "",
        "| 源名称 | Folo位置 | 错误类型 | 当前策略 | 建议 |",
        "|---|---|---|---|---|",
    ]
    for row in manual[:50]:
        lines.append(
            f"| {row.get('源名称')} | {row.get('Folo文件夹路径')} | {row.get('错误类型')} | {row.get('抓取策略')} | {row.get('建议处理方式')} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check InfoRadar RSS source health")
    parser.add_argument("--source-pool", default=str(DEFAULT_SOURCE_POOL))
    parser.add_argument("--timeout", type=int, default=6)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-bytes", type=int, default=768 * 1024)
    args = parser.parse_args()

    source_pool = Path(args.source_pool)
    sources = [
        row
        for row in read_csv(source_pool)
        if source_url(row).startswith(("http://", "https://", "rsshub://"))
    ]
    history = load_status_history()
    cache_keys = load_cache_keys()
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = today_stamp()
    xlsx_path = RETURN_DIR / f"RSS源健康检查_{stamp}.xlsx"
    md_path = RETURN_DIR / f"RSS源健康检查_{stamp}.md"
    governance_path = RETURN_DIR / f"RSSHub备用与403源治理报告_{stamp}.md"

    rows: list[dict] = []
    source_by_name_url = {
        normalize_key(row.get("源名称") or row.get("Folo订阅源名称") or "", source_url(row)): row
        for row in sources
    }
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(probe_source, source, args.timeout, args.max_bytes, history, cache_keys): source
            for source in sources
        }
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda row: (row.get("是否抓取成功") != "是", row.get("错误类型", ""), row.get("Folo文件夹路径", ""), row.get("源名称", "")))
    strategy_rows: list[dict] = []
    for row in rows:
        source = source_by_name_url.get(normalize_key(row.get("源名称", ""), row.get("RSS链接", ""))) or {}
        strategy_rows.append(strategy_row(source, row))

    write_xlsx(xlsx_path, HEADERS, rows, sheet_name="RSS源健康检查")
    write_csv(STRATEGY_CSV, STRATEGY_HEADERS, strategy_rows)
    write_xlsx(STRATEGY_XLSX, STRATEGY_HEADERS, strategy_rows, sheet_name="source_pool_strategy")
    write_markdown(md_path, rows, xlsx_path, STRATEGY_XLSX)
    write_governance_report(governance_path, rows, strategy_rows)

    result = {
        "success": True,
        "source_count": len(rows),
        "success_count": sum(1 for row in rows if row.get("是否抓取成功") == "是"),
        "failed_count": sum(1 for row in rows if row.get("是否抓取成功") != "是"),
        "direct_rss_success_count": sum(1 for row in rows if row.get("是否抓取成功") == "是" and row.get("抓取策略") == "direct_rss"),
        "rsshub_primary_success_count": sum(1 for row in rows if row.get("是否抓取成功") == "是" and row.get("抓取策略") == "rsshub_primary"),
        "rsshub_backup_success_count": sum(1 for row in rows if row.get("是否抓取成功") == "是" and row.get("抓取策略") == "rsshub_backup"),
        "forbidden_count": sum(1 for row in rows if row.get("错误类型") == "403访问限制"),
        "replace_needed_count": sum(1 for row in rows if row.get("是否建议替换") == "是"),
        "disabled_count": sum(1 for row in strategy_rows if row.get("抓取策略") == "disabled" or "废弃" in row.get("建议动作", "")),
        "xlsx": str(xlsx_path),
        "markdown": str(md_path),
        "strategy_csv": str(STRATEGY_CSV),
        "strategy_xlsx": str(STRATEGY_XLSX),
        "governance_report": str(governance_path),
        "output_files": [str(xlsx_path), str(md_path), str(STRATEGY_CSV), str(STRATEGY_XLSX), str(governance_path)],
    }
    append_jsonl(LOG_DIR / "run.log", {"task": "check_feed_health", **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
