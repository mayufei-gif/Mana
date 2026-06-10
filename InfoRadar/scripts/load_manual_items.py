#!/usr/bin/env python3
from __future__ import annotations

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
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
PROCESSED_DIR = ROOT / "data" / "manual_inbox" / "processed"
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


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def date_from_path(path: Path) -> str:
    match = re.search(r"(20\d{6})", path.name)
    return match.group(1) if match else ""


def latest_processed_path(date_text: str = "") -> Path | None:
    if date_text:
        candidates = [
            PROCESSED_DIR / f"manual_processed_{date_text}.jsonl",
            RETURN_DIR / f"manual_collected_items_{date_text}.csv",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None
    paths = list(PROCESSED_DIR.glob("manual_processed_*.jsonl")) + list(RETURN_DIR.glob("manual_collected_items_*.csv"))
    paths = [path for path in paths if date_from_path(path)]
    if not paths:
        return None
    return max(paths, key=lambda path: (date_from_path(path), path.stat().st_mtime))


def load_source_rows(date_text: str = "") -> tuple[list[dict], str]:
    path = latest_processed_path(date_text)
    if not path:
        return [], ""
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path), str(path)
    return read_csv(path), str(path)


def publish_date(row: dict) -> str:
    raw = compact(row.get("收集时间", ""))
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return ""


def manual_folder(row: dict) -> str:
    broad = compact(row.get("broad_category", "")) or compact(row.get("主分类", "")) or "待分类"
    broad = re.sub(r"[\\/:*?\"<>|]+", "_", broad).strip("_") or "待分类"
    return f"manual_inbox/{broad}"


def source_name(row: dict) -> str:
    raw = compact(row.get("来源名称", "")) or "手动收集"
    if "手动收集" in raw:
        return raw
    return f"{raw}（手动收集）"


def topic_allows(row: dict, topic: str) -> bool:
    topic = compact(topic)
    enter_today = compact(row.get("是否进入今日情报", "")).lower()
    if topic in {"今日", "今日情报"} and enter_today == "no":
        return False
    return True


def normalize_row(row: dict) -> dict:
    title = compact(row.get("标题", ""))
    raw_text = compact(row.get("原始内容", ""))
    if not title:
        title = raw_text[:40] or "未命名手动收集"
    return {
        "标题": title,
        "摘要": raw_text,
        "来源名称": source_name(row),
        "订阅源URL": "manual://manual_inbox",
        "原文URL": compact(row.get("链接", "")),
        "Folo文件夹路径": manual_folder(row),
        "发布时间": publish_date(row),
        "input_source": "manual_inbox",
        "source_type": "manual_collected",
        "source_trace_id": compact(row.get("source_trace_id", "")),
        "dedupe_key": compact(row.get("dedupe_key", "")),
        "平台": compact(row.get("平台", "")),
        "主分类": compact(row.get("主分类", "")),
        "broad_category": compact(row.get("broad_category", "")),
        "source_layer": compact(row.get("source_layer", "")),
        "decision_scope": compact(row.get("decision_scope", "")),
        "是否一手信息": compact(row.get("是否一手信息", "")),
        "是否需要核验": compact(row.get("是否需要核验", "")),
        "价值等级": compact(row.get("价值等级", "")),
        "风险等级": compact(row.get("风险等级", "")),
        "为什么与你有关": compact(row.get("为什么与你有关", "")),
        "建议行动": compact(row.get("建议行动", "")),
        "原始内容保存路径": compact(row.get("原始内容保存路径", "")),
        "用户备注": compact(row.get("用户备注", "")),
        "是否进入今日情报": compact(row.get("是否进入今日情报", "")),
        "是否进入长期知识库": compact(row.get("是否进入长期知识库", "")),
        "备注": compact(row.get("备注", "")),
    }


def load_manual_items(topic: str = "", date_text: str = "") -> list[dict]:
    rows, _ = load_source_rows(date_text)
    normalized: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not topic_allows(row, topic):
            continue
        item = normalize_row(row)
        key = item.get("dedupe_key") or item.get("source_trace_id") or item.get("标题")
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Load processed manual InfoRadar items as normalized report input")
    parser.add_argument("--topic", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--output", default=str(NORMALIZED_DIR / "manual_items_latest.csv"))
    args = parser.parse_args()

    rows, source_path = load_source_rows(args.date)
    items = load_manual_items(args.topic, args.date)
    output = Path(args.output)
    write_csv(output, items)
    result = {
        "success": True,
        "source_path": source_path,
        "source_row_count": len(rows),
        "manual_item_count": len(items),
        "topic": args.topic,
        "return_csv": str(output),
        "output_files": [str(output)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
