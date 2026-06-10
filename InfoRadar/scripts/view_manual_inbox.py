#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import datetime as dt
import os
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
WECHAT_DIR = ROOT / "data" / "manual_inbox" / "wechat"
FIXED_SUMMARY = RETURN_DIR / "manual_inbox_微信摘要.txt"


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


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


def latest_inbox_file() -> Path | None:
    files = [path for path in WECHAT_DIR.glob("manual_items_*.jsonl") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def item_brief(row: dict, max_len: int = 46) -> str:
    text = (row.get("raw_text") or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or "(空内容)"


def write_summary(path: Path, rows: list[dict], inbox_path: Path | None, limit: int) -> None:
    today_path = WECHAT_DIR / f"manual_items_{today_stamp()}.jsonl"
    today_rows = read_jsonl(today_path)
    pending = [row for row in today_rows if row.get("status") == "new"]
    platforms = Counter(row.get("platform") or "unknown" for row in today_rows)
    recent = list(reversed(today_rows))[:limit]

    lines = [
        "【InfoRadar 收集箱】",
        "",
        f"今日收集：{len(today_rows)} 条",
        f"待处理：{len(pending)} 条",
        "",
        "平台统计：",
    ]
    if platforms:
        for name, count in platforms.most_common():
            lines.append(f"- {name}：{count}")
    else:
        lines.append("- 暂无")
    lines.extend(["", f"最近{limit}条："])
    if recent:
        for idx, row in enumerate(recent, 1):
            lines.append(f"{idx}. [{row.get('platform') or '-'}] {item_brief(row)}")
    else:
        lines.append("暂无记录")
    lines.extend(["", f"manual_inbox：{inbox_path or today_path}"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="View manual InfoRadar inbox")
    parser.add_argument("--date", default=today_stamp())
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    WECHAT_DIR.mkdir(parents=True, exist_ok=True)
    target = WECHAT_DIR / f"manual_items_{args.date}.jsonl"
    if not target.exists():
        target = latest_inbox_file() or target
    rows = read_jsonl(target)
    today_rows = read_jsonl(WECHAT_DIR / f"manual_items_{today_stamp()}.jsonl")
    pending = [row for row in today_rows if row.get("status") == "new"]
    platforms = Counter(row.get("platform") or "unknown" for row in today_rows)

    write_summary(FIXED_SUMMARY, rows, target if target.exists() else None, args.limit)
    result = {
        "success": True,
        "today_count": len(today_rows),
        "pending_count": len(pending),
        "platform_counts": dict(platforms),
        "inbox_file": str(target),
        "return_summary": str(FIXED_SUMMARY),
        "output_files": [str(FIXED_SUMMARY), str(target)] if target.exists() else [str(FIXED_SUMMARY)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
