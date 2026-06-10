#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOLO_LINK_DIR = Path(os.environ.get("INFORADAR_FOLO_LINK_DIR", str(ROOT / "data" / "raw" / "folo_article_links")))
FOLO_LINK_JSONL = FOLO_LINK_DIR / "folo_article_links.jsonl"
NORMALIZED_DIR = ROOT / "data" / "normalized"

OUTPUT_HEADERS = [
    "标题",
    "摘要",
    "来源名称",
    "订阅源URL",
    "原文URL",
    "Folo文件夹路径",
    "发布时间",
    "input_source",
    "source_type",
    "source_trace_id",
    "dedupe_key",
    "平台",
    "主分类",
    "broad_category",
    "source_layer",
    "decision_scope",
    "是否一手信息",
    "是否需要核验",
    "价值等级",
    "风险等级",
    "为什么与你有关",
    "建议行动",
    "原始内容保存路径",
    "用户备注",
    "是否进入今日情报",
    "是否进入长期知识库",
    "备注",
]


def compact(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\r", " ").replace("\n", " ")).strip()


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def normalize_date(value: object) -> str:
    text = compact(value)
    if not text:
        return ""
    text = text.replace("T", " ")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def platform_for(row: dict) -> str:
    hay = " ".join(compact(row.get(key)) for key in ("source", "original_url", "folo_article_url", "summary")).lower()
    if "youtube.com" in hay or "youtu.be" in hay:
        return "YouTube"
    if "bilibili.com" in hay or "b23.tv" in hay:
        return "B站"
    if "x.com" in hay or "twitter.com" in hay:
        return "X/Twitter"
    if "wechat" in hay or "mp.weixin.qq.com" in hay:
        return "微信公众号"
    return "Folo"


def category_for(row: dict) -> str:
    raw = compact(row.get("folo_category") or row.get("category"))
    if raw:
        return raw
    view = compact(row.get("folo_view") or row.get("view")).lower()
    if view in {"videos", "video", "3"}:
        return "影音视频"
    if view in {"social", "1"}:
        return "社媒热榜"
    return "Folo回流"


def normalize_row(row: dict) -> dict:
    title = compact(row.get("title") or row.get("标题"))
    source = compact(row.get("source") or row.get("来源名称")) or "Folo回流"
    entry_id = compact(row.get("entryId") or row.get("entry_id"))
    feed_id = compact(row.get("feedId") or row.get("feed_id"))
    original_url = compact(row.get("original_url") or row.get("url") or row.get("article_url"))
    folo_url = compact(row.get("folo_article_url"))
    summary = compact(row.get("summary") or row.get("description") or row.get("content"))
    published = normalize_date(row.get("published_at") or row.get("published") or row.get("created_at"))
    platform = platform_for(row)
    category = category_for(row)
    trace_id = entry_id or compact(row.get("source_trace_id")) or compact(row.get("created_at"))
    dedupe_key = "|".join(part for part in [feed_id, entry_id] if part) or original_url or title
    return {
        "标题": title or original_url or "未命名 Folo 条目",
        "摘要": summary,
        "来源名称": source,
        "订阅源URL": f"folo://feeds/{feed_id}" if feed_id else "folo://unknown",
        "原文URL": original_url or folo_url,
        "Folo文件夹路径": f"folo_webhook/{category}",
        "发布时间": published,
        "input_source": "folo_article_links",
        "source_type": "folo_webhook",
        "source_trace_id": trace_id,
        "dedupe_key": dedupe_key,
        "平台": platform,
        "主分类": category,
        "broad_category": category,
        "source_layer": "B_observe",
        "decision_scope": "环境判断",
        "是否一手信息": "否",
        "是否需要核验": "是",
        "价值等级": "中",
        "风险等级": "低",
        "为什么与你有关": "这是 Folo 已订阅源回流的真实条目，可用于日常信息雷达和后续核验。",
        "建议行动": "先阅读摘要和原文；重要内容再追溯官方原文或发布者主页。",
        "原始内容保存路径": str(FOLO_LINK_JSONL),
        "用户备注": folo_url,
        "是否进入今日情报": "pending",
        "是否进入长期知识库": "pending",
        "备注": "来自 Folo Actions/CLI 回流；含真实 feedId/entryId 时可打开 Folo 原条。",
    }


def load_folo_link_items(topic: str = "", limit: int = 500) -> list[dict]:
    topic_text = compact(topic).lower()
    rows = read_jsonl(FOLO_LINK_JSONL)
    out: list[dict] = []
    seen: set[str] = set()
    for row in reversed(rows):
        item = normalize_row(row)
        key = item.get("dedupe_key") or item.get("标题")
        if key in seen:
            continue
        hay = " ".join(str(value or "") for value in item.values()).lower()
        if topic_text and topic_text not in {"全域情报", "今日情报", "今日"} and topic_text not in hay:
            continue
        seen.add(key)
        out.append(item)
        if limit and len(out) >= limit:
            break
    return list(reversed(out))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Folo article links as normalized InfoRadar items")
    parser.add_argument("--topic", default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output", default=str(NORMALIZED_DIR / "folo_link_items_latest.csv"))
    args = parser.parse_args()
    rows = load_folo_link_items(args.topic, args.limit)
    output = Path(args.output)
    write_csv(output, rows)
    print(json.dumps({"success": True, "input": str(FOLO_LINK_JSONL), "output": str(output), "count": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
