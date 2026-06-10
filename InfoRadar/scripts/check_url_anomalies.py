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
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
DEDUPED_DIR = ROOT / "data" / "deduped"
RAW_RSS_DIR = ROOT / "data" / "raw" / "rss_items"
LOG_DIR = ROOT / "logs"

HEADERS = [
    "序号",
    "标题",
    "来源名称",
    "原文URL",
    "订阅源URL",
    "Folo文件夹路径",
    "异常类型",
    "建议修复URL",
    "处理建议",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def latest_input() -> Path:
    candidates: list[Path] = []
    candidates.extend(DEDUPED_DIR.glob("FOLO_*.csv"))
    candidates.extend(RAW_RSS_DIR.glob("folo_items_real_latest.csv"))
    candidates.extend(RAW_RSS_DIR.glob("folo_items_real_*.csv"))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        raise FileNotFoundError("没有找到可检查的 FOLO CSV")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit((value or "").strip())
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def classify_url(url: str, feed_url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    feed = (feed_url or "").strip()
    if not raw:
        return "原文URL为空", ""
    if re.search(r"[\x00-\x1f<>\"{}|\\^`\s]", raw):
        return "URL包含非法字符", ""
    if raw.startswith(("/", "./", "../")):
        fixed = urljoin(feed, raw) if is_http_url(feed) else ""
        return "原文URL是相对路径", fixed
    if not is_http_url(raw):
        return "原文URL不是http/https", ""
    try:
        parsed = urlsplit(raw)
    except Exception:
        return "URL无法解析", ""
    if not parsed.scheme or not parsed.netloc:
        return "URL无法解析", ""
    if feed and raw.rstrip("/") == feed.rstrip("/"):
        return "原文URL等于订阅源URL", ""
    return "", ""


def advice(anomaly_type: str, fixed_url: str) -> str:
    if not anomaly_type:
        return ""
    if fixed_url:
        return "可按建议修复URL补全；修复前不应进入微信前10。"
    if anomaly_type == "原文URL等于订阅源URL":
        return "需要从 Feed 条目重新提取文章页链接；暂不置顶。"
    if anomaly_type == "原文URL为空":
        return "需要回源重新抓取或只作为缓存线索；暂不置顶。"
    return "需要替换或修复 URL；暂不置顶。"


def write_markdown(path: Path, rows: list[dict], source_path: Path, xlsx_path: Path) -> None:
    lines = [
        "# URL异常治理报告",
        "",
        f"生成时间：{now_text()}",
        f"检查输入：{source_path}",
        f"异常表：{xlsx_path}",
        "",
        "## 总览",
        "",
        f"- URL异常数量：{len(rows)}",
        "",
        "## 异常类型分布",
        "",
        "| 异常类型 | 数量 |",
        "|---|---:|",
    ]
    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row["异常类型"]] = by_type.get(row["异常类型"], 0) + 1
    for key, count in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {key} | {count} |")

    lines.extend(["", "## 前30条异常", "", "| 序号 | 标题 | 来源 | 异常 | 建议 |", "|---:|---|---|---|---|"])
    for row in rows[:30]:
        title = (row.get("标题") or "").replace("|", "｜")
        lines.append(f"| {row.get('序号')} | {title} | {row.get('来源名称')} | {row.get('异常类型')} | {row.get('处理建议')} |")

    lines.extend(
        [
            "",
            "## 处理规则",
            "",
            "- 能补全的相对路径只给出建议修复 URL，不盲写原始数据。",
            "- 不能解析、为空、等于订阅源 URL 的条目，生成表格时应标记 URL异常并降权。",
            "- 高权威来源若 URL 异常仍保留为线索，但必须备注说明，不默认进入前10。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check URL anomalies in latest InfoRadar FOLO table")
    parser.add_argument("--input", default="")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else latest_input()
    rows = read_csv(input_path)
    anomalies: list[dict] = []
    for idx, row in enumerate(rows, 1):
        anomaly_type, fixed_url = classify_url(row.get("原文URL", ""), row.get("订阅源URL", ""))
        if not anomaly_type:
            continue
        anomalies.append(
            {
                "序号": row.get("序号") or idx,
                "标题": row.get("标题", ""),
                "来源名称": row.get("来源名称", ""),
                "原文URL": row.get("原文URL", ""),
                "订阅源URL": row.get("订阅源URL", ""),
                "Folo文件夹路径": row.get("Folo文件夹路径", ""),
                "异常类型": anomaly_type,
                "建议修复URL": fixed_url,
                "处理建议": advice(anomaly_type, fixed_url),
            }
        )

    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = today_stamp()
    xlsx_path = RETURN_DIR / f"URL异常治理_{stamp}.xlsx"
    md_path = RETURN_DIR / f"URL异常治理报告_{stamp}.md"
    write_xlsx(xlsx_path, HEADERS, anomalies, sheet_name="URL异常治理")
    write_markdown(md_path, anomalies, input_path, xlsx_path)
    result = {
        "success": True,
        "input": str(input_path),
        "url_anomaly_count": len(anomalies),
        "xlsx": str(xlsx_path),
        "markdown": str(md_path),
        "output_files": [str(xlsx_path), str(md_path)],
    }
    append_jsonl(LOG_DIR / "run.log", {"task": "check_url_anomalies", **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
