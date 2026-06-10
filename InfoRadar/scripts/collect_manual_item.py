#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import datetime as dt
import os
import hashlib
import os
import json
import os
import re
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
INBOX_DIR = ROOT / "data" / "manual_inbox"
WECHAT_DIR = INBOX_DIR / "wechat"
PROCESSED_DIR = INBOX_DIR / "processed"
ARCHIVE_DIR = INBOX_DIR / "archive"
RAW_DIR = WECHAT_DIR / "raw"
FIXED_SUMMARY = RETURN_DIR / "manual_inbox_微信摘要.txt"

SOURCE_HINTS = {
    "学校": "school_notice",
    "校园": "school_notice",
    "公众号": "wechat_article",
    "微信": "wechat_article",
    "抖音": "douyin",
    "B站": "bilibili",
    "b站": "bilibili",
    "知乎": "zhihu",
    "YouTube": "youtube",
    "youtube": "youtube",
    "购物": "shopping",
    "淘宝": "taobao",
    "拼多多": "pinduoduo",
    "京东": "jd",
    "付费资源": "paid_resource",
    "付费": "paid_resource",
    "课程": "paid_resource",
    "热点": "hot_news",
    "风险": "risk",
}

PLATFORM_RULES = [
    ("wechat_article", ["微信", "公众号", "mp.weixin.qq.com"]),
    ("douyin", ["抖音", "douyin"]),
    ("bilibili", ["B站", "b站", "bilibili", "b23.tv"]),
    ("zhihu", ["知乎", "zhihu"]),
    ("youtube", ["youtube", "youtu.be"]),
    ("taobao", ["淘宝", "taobao"]),
    ("pinduoduo", ["拼多多", "pinduoduo"]),
    ("jd", ["京东", "jd.com", "jd"]),
    ("school_notice", ["学校", "山西晋中理工学院", "晋中理工", "教务", "学工", "团委", "奖学金", "入团", "比赛", "竞赛"]),
    ("paid_resource", ["课程", "付费", "专栏", "知识星球", "网课"]),
]


def now() -> dt.datetime:
    return dt.datetime.now()


def today_stamp() -> str:
    return now().strftime("%Y%m%d")


def time_stamp() -> str:
    return now().strftime("%Y%m%d_%H%M%S")


def now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs() -> None:
    for path in [WECHAT_DIR, PROCESSED_DIR, ARCHIVE_DIR, RAW_DIR, RETURN_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>\"]+", text or "", re.I)
    if not match:
        return ""
    return match.group(0).rstrip("。；;，,、)")


def normalize_text(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"https?://[^\s<>\"]+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def sha1_short(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def split_source_hint(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(maxsplit=1)
    first = parts[0]
    if first in SOURCE_HINTS:
        return first, parts[1] if len(parts) > 1 else ""
    return "", raw


def infer_platform(text: str, explicit_platform: str = "", source_hint: str = "") -> str:
    if explicit_platform:
        return explicit_platform
    if source_hint in SOURCE_HINTS:
        hinted = SOURCE_HINTS[source_hint]
        if hinted != "shopping":
            return hinted
    hay = text or ""
    for platform, words in PLATFORM_RULES:
        if any(word.lower() in hay.lower() for word in words):
            return platform
    if source_hint == "购物":
        return "shopping"
    return "other"


def make_trace_id(raw_text: str) -> str:
    return f"manual_{time_stamp()}_{sha1_short(raw_text + now_text(), 6)}"


def make_record(raw_command_text: str, platform: str, note: str, source_hint_arg: str, from_channel: str) -> dict:
    parsed_hint, content = split_source_hint(raw_command_text)
    source_hint = source_hint_arg or parsed_hint
    raw_text = content or raw_command_text
    url = extract_first_url(raw_text)
    inferred_platform = infer_platform(raw_text, platform, source_hint)
    trace_id = make_trace_id(raw_text)
    dedupe_key = sha1_short(f"{normalize_text(raw_text)}|{url}", 16)
    raw_path = RAW_DIR / today_stamp() / f"{trace_id}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw_text, encoding="utf-8")
    return {
        "source_trace_id": trace_id,
        "dedupe_key": dedupe_key,
        "raw_text": raw_text,
        "url": url,
        "platform": inferred_platform,
        "source_hint": source_hint,
        "user_note": note,
        "collected_at": now_text(),
        "raw_content_path": str(raw_path),
        "attachment_path": "",
        "status": "new",
        "from_channel": from_channel,
    }


def append_record(record: dict) -> Path:
    path = WECHAT_DIR / f"manual_items_{today_stamp()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def write_summary(record: dict, jsonl_path: Path) -> Path:
    summary = RETURN_DIR / f"manual_collect_{record['source_trace_id']}_微信摘要.txt"
    lines = [
        "【InfoRadar 收集成功】",
        "",
        f"追踪ID：{record['source_trace_id']}",
        f"平台：{record['platform']}",
        f"链接：{record['url'] or '-'}",
        f"状态：{record['status']}",
        "",
        f"收集文件：{jsonl_path}",
        f"原文路径：{record['raw_content_path']}",
        "",
        "已保存到 manual_inbox。",
        "可发送：查看收集箱 / 处理收集箱",
    ]
    text = "\n".join(lines)
    summary.write_text(text, encoding="utf-8")
    FIXED_SUMMARY.write_text(text, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a manual InfoRadar inbox item")
    parser.add_argument("--text", required=True)
    parser.add_argument("--platform", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--source-hint", default="")
    parser.add_argument("--from-channel", default="cli")
    args = parser.parse_args()

    ensure_dirs()
    record = make_record(args.text, args.platform, args.note, args.source_hint, args.from_channel)
    jsonl_path = append_record(record)
    summary = write_summary(record, jsonl_path)

    result = {
        "success": True,
        "source_trace_id": record["source_trace_id"],
        "dedupe_key": record["dedupe_key"],
        "platform": record["platform"],
        "url": record["url"],
        "status": record["status"],
        "jsonl": str(jsonl_path),
        "raw_content_path": record["raw_content_path"],
        "return_summary": str(summary),
        "output_files": [str(summary), str(FIXED_SUMMARY), str(jsonl_path), record["raw_content_path"]],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
