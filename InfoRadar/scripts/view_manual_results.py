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
PROCESSED_DIR = ROOT / "data" / "manual_inbox" / "processed"
SUMMARY_TXT = RETURN_DIR / "manual_collected_items_微信摘要.txt"


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


def latest_processed_file() -> Path | None:
    files = [path for path in PROCESSED_DIR.glob("manual_processed_*.jsonl") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def brief(row: dict, max_len: int = 42) -> str:
    text = row.get("标题") or row.get("原始内容") or ""
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or "(空内容)"


def main() -> int:
    parser = argparse.ArgumentParser(description="View processed manual InfoRadar results")
    parser.add_argument("--date", default=today_stamp())
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    target = PROCESSED_DIR / f"manual_processed_{args.date}.jsonl"
    if not target.exists():
        target = latest_processed_file() or target
    rows = read_jsonl(target)
    platforms = Counter(row.get("平台") or "unknown" for row in rows)
    risks = Counter(row.get("风险等级") or "未标记" for row in rows)
    recent = list(reversed(rows))[: args.limit]

    lines = [
        "【InfoRadar 收集结果】",
        "",
        f"已处理：{len(rows)} 条",
        f"高风险：{sum(1 for row in rows if row.get('风险等级') == '高')} 条",
        "",
        "平台统计：",
    ]
    if platforms:
        for name, count in platforms.most_common():
            lines.append(f"- {name}：{count}")
    else:
        lines.append("- 暂无")
    lines.extend(["", "风险统计："])
    if risks:
        for name, count in risks.most_common():
            lines.append(f"- {name}：{count}")
    else:
        lines.append("- 暂无")
    lines.extend(["", f"最近{args.limit}条："])
    if recent:
        for idx, row in enumerate(recent, 1):
            lines.append(f"{idx}. [{row.get('平台')}] {brief(row)} | {row.get('价值等级')} | 风险：{row.get('风险等级')}")
    else:
        lines.append("暂无处理结果")
    lines.extend(["", f"processed：{target}"])
    SUMMARY_TXT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")

    result = {
        "success": True,
        "processed_count": len(rows),
        "high_risk_count": sum(1 for row in rows if row.get("风险等级") == "高"),
        "platform_counts": dict(platforms),
        "processed_file": str(target),
        "return_summary": str(SUMMARY_TXT),
        "output_files": [str(SUMMARY_TXT), str(target)] if target.exists() else [str(SUMMARY_TXT)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
