#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

import rsshub_tools
import all_domain_rules


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_POOL = ROOT / "sources" / "source_pool_from_folo.csv"
RAW_DIR = ROOT / "data" / "raw" / "rss_items"
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
LOG_DIR = ROOT / "logs"


ITEM_HEADERS = [
    "标题",
    "来源名称",
    "原文URL",
    "订阅源URL",
    "原始RSS链接",
    "实际抓取URL",
    "使用RSSHub实例",
    "抓取策略",
    "Folo文件夹路径",
    "Folo订阅源名称",
    "发布时间",
    "摘要",
]


STATUS_HEADERS = [
    "序号",
    "源名称",
    "可抓取RSS链接",
    "原始RSS链接",
    "实际抓取URL",
    "使用RSSHub实例",
    "抓取策略",
    "Folo文件夹路径",
    "状态",
    "条目数",
    "耗时秒",
    "错误",
]


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


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


def clean_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(elem: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(elem):
        if local_name(child.tag) in wanted:
            return clean_text("".join(child.itertext()))
    return ""


def atom_link(elem: ET.Element) -> str:
    fallback = ""
    for child in list(elem):
        if local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "").strip().lower()
        if href and rel in ("", "alternate"):
            return href
        if href and not fallback:
            fallback = href
    return fallback


def normalize_date(value: str) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed:
            return parsed.date().isoformat()
    except Exception:
        pass
    normalized = raw.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(normalized[:25]).date().isoformat()
    except Exception:
        pass
    match = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", raw)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return raw[:30]


def topic_keywords(topic: str) -> list[str]:
    topic = (topic or "").strip()
    mapping = {
        "技术": ["技术", "PLC", "变频器", "电气", "自动化", "机器人", "CAD", "EPLAN", "维修"],
        "政策": ["政策", "证书", "补贴", "人社", "电工证", "政府", "gov.cn", "国务院", "时政", "新华网", "人民网", "中新网"],
        "招聘": ["招聘", "校招", "实习", "岗位", "就业", "山西焦煤", "霍州煤电", "晋能控股"],
        "证书": ["证书", "电工证", "低压电工", "高压电工", "职业技能", "技能等级", "技能补贴", "计算机等级", "CAD证书", "考试", "报名"],
        "AI": ["AI", "OpenAI", "ChatGPT", "Codex", "GitHub", "RSSHub", "Folo", "Claude", "Agent"],
    }
    mapping.update(all_domain_rules.TOPIC_KEYWORDS)
    if topic in ("", "今日", "今日情报", "全域情报", "全部"):
        return []
    return mapping.get(topic, [topic])


def keyword_matches(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    if re.fullmatch(r"[A-Za-z0-9+#.]{1,4}", keyword):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", text, re.I))
    return keyword.lower() in text.lower()


def matches_topic(row: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    hay = " ".join(
        str(row.get(key, ""))
        for key in ["源名称", "Folo文件夹路径", "主分类", "标签", "备注", "官网链接", "RSS链接"]
    )
    return any(keyword_matches(hay, keyword) for keyword in keywords)


def item_matches_topic(row: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    hay = " ".join(
        str(row.get(key, ""))
        for key in ["标题", "摘要", "来源名称", "Folo文件夹路径", "Folo订阅源名称", "原文URL", "订阅源URL"]
    )
    return any(keyword_matches(hay, keyword) for keyword in keywords)


def is_rsshub_source(row: dict) -> bool:
    return rsshub_tools.source_fetch_strategy(row).startswith("rsshub_")


def load_sources(path: Path, topic: str, include_invalid: bool, limit: int) -> list[dict]:
    keywords = topic_keywords(topic)
    rows = []
    for row in read_csv(path):
        url = (row.get("可抓取RSS链接") or row.get("RSS链接") or "").strip()
        if not url.startswith(("http://", "https://", "rsshub://")):
            continue
        if not include_invalid and (row.get("是否失效") or "").strip() == "是":
            continue
        if (row.get("是否建议保留") or "").strip() == "否":
            continue
        if not matches_topic(row, keywords):
            continue
        row = dict(row)
        row["_fetch_url"] = url
        rows.append(row)
    rows.sort(
        key=lambda r: (
            {"高": 0, "中": 1, "低": 2, "待修复": 3}.get((r.get("订阅优先级") or "").strip(), 9),
            1 if is_rsshub_source(r) else 0,
            -int(str(r.get("长期价值评分") or "0").strip() or 0),
        )
    )
    return rows[:limit] if limit > 0 else rows


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


def fetch_url(url: str, timeout: int, max_bytes: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "InfoRadar/0.2 (+RSS; Windows Codex Bridge)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
        return decode_response(data, resp.headers)


def candidate_specs(source: dict) -> list[dict]:
    return rsshub_tools.rsshub_candidates(source)


def parse_feed(xml_text: str, source: dict, fetch_spec: dict, max_items: int) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    candidates = [elem for elem in root.iter() if local_name(elem.tag) in ("item", "entry")]
    rows: list[dict] = []
    for elem in candidates[:max_items]:
        title = child_text(elem, "title")
        link = child_text(elem, "link") or atom_link(elem)
        published = child_text(elem, "pubDate", "published", "updated", "date")
        summary = child_text(elem, "description", "summary", "content", "encoded")
        if not title:
            continue
        rows.append(
            {
                "标题": title,
                "来源名称": source.get("源名称") or source.get("Folo订阅源名称") or "",
                "原文URL": link,
                "订阅源URL": source.get("RSS链接") or source.get("可抓取RSS链接") or "",
                "原始RSS链接": fetch_spec.get("原始RSS链接", ""),
                "实际抓取URL": fetch_spec.get("实际抓取URL", ""),
                "使用RSSHub实例": fetch_spec.get("使用RSSHub实例", ""),
                "抓取策略": fetch_spec.get("抓取策略", ""),
                "Folo文件夹路径": source.get("Folo文件夹路径") or "待定位",
                "Folo订阅源名称": source.get("Folo订阅源名称") or source.get("源名称") or "",
                "发布时间": normalize_date(published),
                "摘要": summary[:800],
            }
        )
    return rows


def fetch_source(source: dict, timeout: int, max_items: int, max_bytes: int) -> tuple[list[dict], dict]:
    started = time.time()
    status = {
        "源名称": source.get("源名称") or "",
        "可抓取RSS链接": source.get("_fetch_url") or "",
        "原始RSS链接": rsshub_tools.original_rss_url(source),
        "实际抓取URL": "",
        "使用RSSHub实例": "",
        "抓取策略": rsshub_tools.source_fetch_strategy(source),
        "Folo文件夹路径": source.get("Folo文件夹路径") or "",
        "状态": "failed",
        "条目数": 0,
        "耗时秒": 0,
        "错误": "",
    }
    errors: list[str] = []
    try:
        for fetch_spec in candidate_specs(source):
            url = fetch_spec.get("实际抓取URL", "")
            try:
                xml_text = fetch_url(url, timeout=timeout, max_bytes=max_bytes)
                rows = parse_feed(xml_text, source, fetch_spec, max_items=max_items)
                status["状态"] = "success"
                status["条目数"] = len(rows)
                status["可抓取RSS链接"] = url
                status["实际抓取URL"] = url
                status["使用RSSHub实例"] = fetch_spec.get("使用RSSHub实例", "")
                status["抓取策略"] = fetch_spec.get("抓取策略", "")
                return rows, status
            except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
                errors.append(f"{url} => {repr(exc)[:220]}")
            except Exception as exc:
                errors.append(f"{url} => {repr(exc)[:220]}")
        if not errors and not candidate_specs(source):
            errors.append("缺少可抓取 HTTP/RSSHub 链接")
        status["错误"] = " | ".join(errors)[:500]
        return [], status
    finally:
        status["耗时秒"] = round(time.time() - started, 2)


def dedupe_items(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        key = "|".join([row.get("标题", "").strip().lower(), row.get("原文URL", "").strip().lower()])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def recent_item_cache_files(exclude: set[Path]) -> list[Path]:
    files: list[Path] = []
    patterns = [
        "folo_items_real_latest.csv",
        "folo_items_real_fetch_rss_*.csv",
        "folo_items_real_*.csv",
        "folo_items_real.csv",
    ]
    for pattern in patterns:
        for path in RAW_DIR.glob(pattern):
            try:
                resolved = path.resolve()
            except Exception:
                resolved = path
            if resolved in exclude or not path.is_file():
                continue
            if path not in files:
                files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def load_cache_items(topic: str, exclude: set[Path], max_files: int = 8, max_rows: int = 800) -> list[dict]:
    keywords = topic_keywords(topic)
    rows: list[dict] = []
    for path in recent_item_cache_files(exclude)[:max_files]:
        try:
            for row in read_csv(path):
                if item_matches_topic(row, keywords):
                    rows.append(row)
                    if len(rows) >= max_rows:
                        return rows
        except Exception as exc:
            append_jsonl(LOG_DIR / "fetch_rss_items_errors.jsonl", {"cache_file": str(path), "error": repr(exc)})
    return rows


def write_summary(path: Path, result: dict, status_rows: list[dict]) -> None:
    failed = [row for row in status_rows if row.get("状态") != "success"]
    top_failures = failed[:5]
    lines = [
        "【InfoRadar Folo更新抓取】",
        "",
        f"任务ID：{result['task_id']}",
        f"抓取时间：{now_text()}",
        f"尝试源数：{result['attempted_source_count']}",
        f"成功源数：{result['success_source_count']}",
        f"失败源数：{result['failed_source_count']}",
        f"抓到条目：{result['item_count']}",
    "",
    f"条目CSV：{result['output']}",
    f"状态CSV：{result['status_csv']}",
    ]
    if result.get("cache_fallback_used"):
        lines.extend(
            [
                "",
                "缓存兜底：已启用",
                f"缓存候选条目：{result.get('cache_fallback_candidate_count', 0)}",
                f"缓存合并新增：{result.get('cache_fallback_added_count', 0)}",
            ]
        )
    if top_failures:
        lines.extend(["", "前几个失败源："])
        for row in top_failures:
            lines.append(f"- {row.get('源名称')}：{row.get('错误')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch latest RSS/Atom items from InfoRadar Folo source pool")
    parser.add_argument("--source-pool", default=str(DEFAULT_SOURCE_POOL))
    parser.add_argument("--output", default="")
    parser.add_argument("--topic", default="今日")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--limit-sources", type=int, default=40)
    parser.add_argument("--max-items-per-feed", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-bytes", type=int, default=3 * 1024 * 1024)
    parser.add_argument("--include-invalid", action="store_true")
    parser.add_argument("--cache-fallback-min-success-ratio", type=float, default=0.5)
    parser.add_argument("--cache-fallback-min-items", type=int, default=40)
    args = parser.parse_args()

    task_id = args.task_id or f"fetch_rss_{stamp()}"
    source_pool = Path(args.source_pool)
    if not source_pool.exists():
        raise FileNotFoundError(source_pool)

    sources = load_sources(source_pool, args.topic, args.include_invalid, args.limit_sources)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    output = Path(args.output) if args.output else RAW_DIR / "folo_items_real.csv"
    if not args.output:
        output = RAW_DIR / f"folo_items_real_{task_id}.csv"
    latest_output = RAW_DIR / "folo_items_real_latest.csv"
    status_csv = RAW_DIR / f"fetch_status_{task_id}.csv"
    summary = RETURN_DIR / f"fetch_rss_items_{task_id}_微信摘要.txt"

    all_items: list[dict] = []
    status_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(fetch_source, source, args.timeout, args.max_items_per_feed, args.max_bytes): source
            for source in sources
        }
        for future in as_completed(futures):
            rows, status = future.result()
            all_items.extend(rows)
            status_rows.append(status)
            if status.get("状态") != "success":
                append_jsonl(LOG_DIR / "fetch_rss_items_errors.jsonl", {"task_id": task_id, **status})

    all_items = dedupe_items(all_items)
    status_rows.sort(key=lambda r: (r.get("状态") != "success", r.get("Folo文件夹路径", ""), r.get("源名称", "")))
    for idx, row in enumerate(status_rows, 1):
        row["序号"] = idx
    success_count = sum(1 for row in status_rows if row.get("状态") == "success")
    success_ratio = success_count / len(status_rows) if status_rows else 0
    cache_rows: list[dict] = []
    cache_added_count = 0
    should_use_cache = (
        bool(status_rows)
        and (
            success_ratio < args.cache_fallback_min_success_ratio
            or len(all_items) < args.cache_fallback_min_items
        )
    )
    if should_use_cache:
        exclude = {output.resolve(), status_csv.resolve()}
        cache_rows = load_cache_items(args.topic, exclude)
        before_cache_count = len(all_items)
        all_items = dedupe_items(all_items + cache_rows)
        cache_added_count = len(all_items) - before_cache_count

    write_csv(output, ITEM_HEADERS, all_items)
    shutil.copyfile(output, latest_output)
    write_csv(status_csv, STATUS_HEADERS, status_rows)

    result = {
        "success": True,
        "task_id": task_id,
        "source_pool": str(source_pool),
        "source_count": len(sources),
        "attempted_source_count": len(status_rows),
        "success_source_count": success_count,
        "failed_source_count": len(status_rows) - success_count,
        "success_ratio": round(success_ratio, 4),
        "item_count": len(all_items),
        "live_item_count": len(all_items) - cache_added_count,
        "cache_fallback_used": cache_added_count > 0,
        "cache_fallback_candidate_count": len(cache_rows),
        "cache_fallback_added_count": cache_added_count,
        "output": str(output),
        "latest_output": str(latest_output),
        "status_csv": str(status_csv),
        "return_summary": str(summary),
        "output_files": [str(output), str(latest_output), str(status_csv), str(summary)],
    }
    write_summary(summary, result, status_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
