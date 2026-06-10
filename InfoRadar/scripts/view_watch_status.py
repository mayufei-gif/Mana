#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
WATCH_REQUESTS = ROOT / "sources" / "watch_only_requests.csv"
UPDATE_DIR = ROOT / "data" / "watch" / "updates"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def latest_updates_path() -> Path | None:
    paths = sorted(UPDATE_DIR.glob("watch_updates_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


def write_summary(mode: str, lines: list[str]) -> Path:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    path = RETURN_DIR / f"watch_{mode}_微信摘要.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="View InfoRadar watch status")
    parser.add_argument("--mode", choices=["status", "updates", "report"], default="status")
    args = parser.parse_args()
    requests = read_csv(WATCH_REQUESTS)
    latest_updates = latest_updates_path()
    updates = read_jsonl(latest_updates) if latest_updates else []
    if args.mode == "status":
        lines = ["【InfoRadar 监控状态】", "", f"监控请求：{len(requests)} 个", "", "最近请求："]
        for row in requests[-10:]:
            lines.append(f"- {row.get('关键词')} | {row.get('状态')} | {row.get('创建时间')}")
        summary = write_summary("status", lines)
        result = {"success": True, "watch_request_count": len(requests), "return_summary": str(summary), "return_csv": str(WATCH_REQUESTS), "output_files": [str(WATCH_REQUESTS), str(summary)]}
    elif args.mode == "updates":
        lines = ["【InfoRadar 监控更新】", "", f"最新更新文件：{latest_updates or '-'}", f"更新数量：{len(updates)}", "", "前10条："]
        for idx, row in enumerate(updates[:10], 1):
            lines.append(f"{idx}. {row.get('title')} | {row.get('source_name')}")
        summary = write_summary("updates", lines)
        result = {"success": True, "watch_update_count": len(updates), "return_summary": str(summary), "updates_file": str(latest_updates or ""), "output_files": [str(summary), str(latest_updates or "")]}
    else:
        reports = sorted(RETURN_DIR.glob("watch_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        report = reports[0] if reports else None
        lines = ["【InfoRadar 监控报告】", "", f"最近报告：{report or '-'}"]
        summary = write_summary("report", lines)
        result = {"success": True, "report": str(report or ""), "return_summary": str(summary), "output_files": [str(summary), str(report or "")]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
