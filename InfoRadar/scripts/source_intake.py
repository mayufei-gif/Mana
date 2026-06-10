#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import datetime as dt
import os
import html
import os
import json
import os
import re
import os
from pathlib import Path

from local_search import query_terms, score_text
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))

HEADERS = ["序号", "源名称", "URL", "RSS链接", "主分类", "推荐Folo文件夹", "接入策略", "状态", "source_trace_id", "备注"]


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def classify_strategy(row: dict) -> str:
    rss = (row.get("RSS链接") or "").strip()
    addable = (row.get("是否可被Folo添加") or "").strip()
    if rss.startswith(("http://", "https://", "rsshub://")) or addable == "是":
        return "import_ready"
    if row.get("官网链接"):
        return "watch_only"
    if row.get("平台") in {"公众号", "抖音", "视频号", "小红书"}:
        return "manual_forward"
    return "manual_review"


def normalize_rows(query: str, candidate_csv: Path, watchlist_csv: Path, limit: int = 50) -> list[dict]:
    terms = query_terms(query)
    raw_rows = read_csv(candidate_csv) + read_csv(watchlist_csv)
    rows: list[dict] = []
    seen: set[str] = set()
    for raw in raw_rows:
        text = " ".join(str(value) for value in raw.values() if value)
        score, _ = score_text(query, terms, text)
        if query and score <= 0:
            continue
        name = raw.get("源名称") or raw.get("name") or "未命名源"
        url = raw.get("官网链接") or raw.get("URL") or raw.get("RSS链接") or ""
        key = raw.get("源ID") or f"{name}|{url}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "序号": len(rows) + 1,
                "源名称": name,
                "URL": url,
                "RSS链接": raw.get("RSS链接", ""),
                "主分类": raw.get("主分类", ""),
                "推荐Folo文件夹": raw.get("推荐Folo文件夹", ""),
                "接入策略": classify_strategy(raw),
                "状态": raw.get("状态", ""),
                "source_trace_id": raw.get("源ID", ""),
                "备注": raw.get("备注") or raw.get("推荐原因") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def write_opml(path: Path, rows: list[dict]) -> int:
    import_ready = [row for row in rows if row.get("接入策略") == "import_ready" and row.get("RSS链接")]
    outlines = []
    for row in import_ready:
        title = html.escape(row.get("源名称", "未命名源"))
        url = html.escape(row.get("RSS链接", ""))
        outlines.append(f'    <outline text="{title}" title="{title}" type="rss" xmlUrl="{url}" />')
    content = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head><title>InfoRadar free command import ready</title></head>",
        "  <body>",
        *outlines,
        "  </body>",
        "</opml>",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(content), encoding="utf-8")
    return len(import_ready)


def summarize_source_intake(query: str, candidate_csv: str = "", watchlist_csv: str = "") -> dict:
    task_stamp = stamp()
    candidate_path = Path(candidate_csv) if candidate_csv else ROOT / "sources" / "candidate_sources.csv"
    watchlist_path = Path(watchlist_csv) if watchlist_csv else ROOT / "sources" / "source_watchlist.csv"
    rows = normalize_rows(query, candidate_path, watchlist_path)
    csv_path = RETURN_DIR / f"source_intake_{task_stamp}.csv"
    xlsx_path = RETURN_DIR / f"source_intake_{task_stamp}.xlsx"
    md_path = RETURN_DIR / f"source_intake_{task_stamp}.md"
    opml_path = RETURN_DIR / f"source_intake_import_ready_{task_stamp}.opml"
    write_csv(csv_path, rows)
    write_xlsx(xlsx_path, HEADERS, rows, "source_intake")
    import_ready_count = write_opml(opml_path, rows)
    lines = ["# InfoRadar 源接入建议", "", f"指令：{query}", f"候选源：{len(rows)}", f"可导入 Folo：{import_ready_count}", ""]
    for row in rows[:10]:
        lines.append(f"- {row.get('源名称')} | {row.get('接入策略')} | {row.get('URL') or row.get('RSS链接')}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "source_intake_count": len(rows),
        "candidate_source_count": len(rows),
        "import_ready_count": import_ready_count,
        "watch_only_count": sum(1 for row in rows if row.get("接入策略") == "watch_only"),
        "manual_review_count": sum(1 for row in rows if row.get("接入策略") == "manual_review"),
        "return_csv": str(csv_path),
        "return_xlsx": str(xlsx_path),
        "return_opml": str(opml_path),
        "markdown": str(md_path),
        "output_files": [str(csv_path), str(xlsx_path), str(md_path), str(opml_path)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize InfoRadar candidate source intake")
    parser.add_argument("--query", default="")
    parser.add_argument("--candidate-csv", default="")
    parser.add_argument("--watchlist-csv", default="")
    args = parser.parse_args()
    result = {"success": True, "query": args.query, **summarize_source_intake(args.query, args.candidate_csv, args.watchlist_csv)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
