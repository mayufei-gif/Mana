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
UPDATE_DIR = ROOT / "data" / "watch" / "updates"
NORMALIZED_DIR = ROOT / "data" / "normalized"

HEADERS = [
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
    "是否需要核验",
    "风险等级",
    "为什么与你有关",
    "建议行动",
    "是否进入今日情报",
    "是否进入长期知识库",
    "备注",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def read_jsonl(path: Path) -> list[dict]:
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
    return rows


def latest_update_path(date_text: str = "") -> Path | None:
    if date_text:
        path = UPDATE_DIR / f"watch_updates_{date_text}.jsonl"
        return path if path.exists() else None
    paths = sorted(UPDATE_DIR.glob("watch_updates_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def main_category(broad: str) -> str:
    if broad == "我的学校":
        return "我的学校"
    if broad == "就业招聘":
        return "就业招聘"
    if broad == "职业证书":
        return "职业证书"
    if broad == "政策风向":
        return "地方政策"
    return broad or "长期观察"


def normalize(row: dict) -> dict:
    broad = compact(row.get("broad_category", ""))
    title = compact(row.get("title", ""))
    return {
        "标题": title or "未命名监控更新",
        "摘要": compact(row.get("why_relevant", "")),
        "来源名称": compact(row.get("source_name", "")) or "watch_only观察源",
        "订阅源URL": "watch://watch_only",
        "原文URL": compact(row.get("url", "")),
        "Folo文件夹路径": f"watch_updates/{broad or '长期观察'}",
        "发布时间": compact(row.get("published_at", "")) or compact(row.get("detected_at", ""))[:10],
        "input_source": "watch_updates",
        "source_type": "watch_update",
        "source_trace_id": compact(row.get("update_id", "")),
        "dedupe_key": compact(row.get("update_id", "")),
        "平台": "官网观察",
        "主分类": main_category(broad),
        "broad_category": broad,
        "source_layer": compact(row.get("source_layer", "")),
        "decision_scope": compact(row.get("decision_scope", "")),
        "是否需要核验": "是",
        "风险等级": compact(row.get("risk_level", "")) or "低",
        "为什么与你有关": compact(row.get("why_relevant", "")),
        "建议行动": compact(row.get("suggested_action", "")),
        "是否进入今日情报": "yes",
        "是否进入长期知识库": "pending",
        "备注": f"watch_id={compact(row.get('watch_id', ''))}; status={compact(row.get('status', ''))}",
    }


def load_watch_updates(topic: str = "", date_text: str = "") -> list[dict]:
    path = latest_update_path(date_text)
    if not path:
        return []
    rows = [normalize(row) for row in read_jsonl(path)]
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        key = row.get("dedupe_key") or row.get("标题")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load watch updates as normalized InfoRadar input")
    parser.add_argument("--date", default="")
    parser.add_argument("--output", default=str(NORMALIZED_DIR / "watch_updates_latest.csv"))
    args = parser.parse_args()
    rows = load_watch_updates(date_text=args.date)
    output = Path(args.output)
    write_csv(output, rows)
    result = {"success": True, "watch_update_count": len(rows), "return_csv": str(output), "output_files": [str(output)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
