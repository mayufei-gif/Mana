#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
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

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))

HEADERS = [
    "序号",
    "标题",
    "发布时间",
    "匹配分数",
    "来源集合",
    "来源类型",
    "主分类",
    "全域分类",
    "原文URL",
    "source_trace_id",
    "dedupe_key",
    "来源文件",
    "匹配原因",
    "摘要片段",
]

KEY_TERMS = [
    "山西晋中理工",
    "晋中理工",
    "山西机电",
    "奖学金",
    "入团",
    "教务",
    "学工",
    "团委",
    "比赛",
    "竞赛",
    "低压电工",
    "高压电工",
    "电工证",
    "技能补贴",
    "证书",
    "报名",
    "招聘",
    "山西焦煤",
    "晋能控股",
    "霍州煤电",
    "PLC",
    "变频器",
    "ACS800",
    "课程",
    "付费",
    "值得买",
    "AI",
    "OpenAI",
    "Codex",
    "Folo",
    "RSSHub",
    "自动化",
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def source_trace(text: str) -> str:
    return "local_" + hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def parse_datetime(value: str) -> dt.datetime | None:
    raw = compact(str(value or ""))
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    normalized = re.sub(r"年|月", "-", normalized).replace("日", "")
    normalized = normalized.replace("/", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        normalized = f"{normalized} 00:00:00"
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d_%H%M%S_%f",
        "%Y%m%d_%H%M%S",
        "%Y%m%d",
    ]:
        try:
            return dt.datetime.strptime(normalized[:26], fmt)
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def row_published_at(row: dict, fallback_path: Path | None = None) -> str:
    for key in [
        "发布时间",
        "发布日期",
        "发布于",
        "pubDate",
        "published",
        "published_at",
        "date",
        "发现时间",
        "created_at",
        "updated_at",
        "modified_at",
    ]:
        value = compact(str(row.get(key, "")))
        if value:
            return value
    if fallback_path is not None:
        try:
            return dt.datetime.fromtimestamp(fallback_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return ""
    return ""


def sort_timestamp(row: dict) -> float:
    published = parse_datetime(str(row.get("发布时间", "")))
    if published is not None:
        return published.timestamp()
    source_file = row.get("来源文件", "")
    if source_file:
        try:
            return Path(str(source_file)).stat().st_mtime
        except OSError:
            pass
    return 0.0


def query_terms(query: str) -> list[str]:
    raw = compact(query)
    terms: list[str] = []
    for term in KEY_TERMS:
        if term.lower() in raw.lower():
            terms.append(term)
    for part in re.split(r"[^\w\u4e00-\u9fff+#.]+", raw):
        part = part.strip()
        if len(part) >= 2:
            terms.append(part)
    if raw and raw not in terms:
        terms.append(raw)
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def score_text(query: str, terms: list[str], text: str) -> tuple[int, list[str]]:
    hay = text.lower()
    score = 0
    reasons: list[str] = []
    if query and query.lower() in hay:
        score += 30
        reasons.append("完整指令命中")
    for term in terms:
        if term.lower() not in hay:
            continue
        score += 6 if len(term) >= 4 else 3
        reasons.append(term)
    return score, reasons[:8]


def snippet(text: str, terms: list[str]) -> str:
    plain = compact(text)
    lower = plain.lower()
    pos = -1
    for term in terms:
        pos = lower.find(term.lower())
        if pos >= 0:
            break
    if pos < 0:
        return plain[:180]
    start = max(0, pos - 60)
    return plain[start : start + 220]


def collection_for(path: Path) -> str:
    value = str(path)
    if "manual_collected_items" in path.name:
        return "manual_collected_items"
    if "data\\deduped" in value or "data/deduped" in value or path.name.startswith("FOLO_"):
        return "folo_report_table"
    if "sources" in value:
        return "source_pool"
    if "task_history" in value:
        return "task_history"
    if "reports" in value:
        return "reports"
    if "NAS回传" in value:
        return "return_folo"
    return "local_file"


def iter_csv_paths() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted((ROOT / "data" / "deduped").glob("FOLO_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:20])
    paths.extend(sorted(RETURN_DIR.glob("manual_collected_items_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:5])
    for name in [
        "source_pool_from_folo.csv",
        "source_pool_strategy.csv",
        "candidate_sources.csv",
        "source_watchlist.csv",
        "all_domain_candidate_sources.csv",
        "all_domain_source_profile.csv",
    ]:
        path = ROOT / "sources" / name
        if path.exists():
            paths.append(path)
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def iter_text_paths() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted((ROOT / "reports").glob("**/*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:120])
    paths.extend(sorted(RETURN_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:80])
    paths.extend(sorted((ROOT / "memory" / "task_history").glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:20])
    return [path for path in paths if path.is_file()]


def row_title(row: dict) -> str:
    for key in ["标题", "源名称", "title", "name", "command", "最近任务"]:
        value = compact(str(row.get(key, "")))
        if value:
            return value
    return "未命名记录"


def row_url(row: dict) -> str:
    for key in ["原文URL", "链接", "RSS链接", "官网链接", "url", "xlsx", "markdown", "summary_file"]:
        value = compact(str(row.get(key, "")))
        if value:
            return value
    return ""


def search_csv_file(path: Path, query: str, terms: list[str], limit_per_file: int = 5000) -> list[dict]:
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if idx >= limit_per_file:
                    break
                text = " ".join(str(value) for value in row.values() if value)
                score, reasons = score_text(query, terms, text)
                if score <= 0:
                    continue
                title = row_title(row)
                trace = compact(row.get("source_trace_id", "")) or compact(row.get("源ID", "")) or source_trace(f"{path}:{idx}:{title}")
                rows.append(
                    {
                        "标题": title,
                        "发布时间": row_published_at(row, path),
                        "匹配分数": score,
                        "来源集合": collection_for(path),
                        "来源类型": row.get("来源类型") or row.get("源类型") or collection_for(path),
                        "主分类": row.get("主分类", ""),
                        "全域分类": row.get("全域分类") or row.get("broad_category", ""),
                        "原文URL": row_url(row),
                        "source_trace_id": trace,
                        "dedupe_key": row.get("dedupe_key", ""),
                        "来源文件": str(path),
                        "匹配原因": "、".join(reasons),
                        "摘要片段": snippet(text, terms),
                    }
                )
    except Exception:
        return []
    return rows


def search_text_file(path: Path, query: str, terms: list[str]) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:250000]
    except Exception:
        return []
    score, reasons = score_text(query, terms, text)
    if score <= 0:
        return []
    title = path.stem
    return [
        {
            "标题": title,
            "发布时间": row_published_at({}, path),
            "匹配分数": score,
            "来源集合": collection_for(path),
            "来源类型": collection_for(path),
            "主分类": "",
            "全域分类": "",
            "原文URL": str(path),
            "source_trace_id": source_trace(str(path)),
            "dedupe_key": "",
            "来源文件": str(path),
            "匹配原因": "、".join(reasons),
            "摘要片段": snippet(text, terms),
        }
    ]


def search_local(query: str, limit: int = 30) -> list[dict]:
    terms = query_terms(query)
    matches: list[dict] = []
    for path in iter_csv_paths():
        matches.extend(search_csv_file(path, query, terms))
    for path in iter_text_paths():
        matches.extend(search_text_file(path, query, terms))
    matches.sort(key=lambda row: (sort_timestamp(row), int(row.get("匹配分数", 0))), reverse=True)
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in matches:
        key = row.get("source_trace_id") or f"{row.get('标题')}|{row.get('来源文件')}"
        if key in seen:
            continue
        seen.add(key)
        row["序号"] = len(deduped) + 1
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def write_outputs(query: str, rows: list[dict], stamp: str) -> dict:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RETURN_DIR / f"local_search_{stamp}.csv"
    xlsx_path = RETURN_DIR / f"local_search_{stamp}.xlsx"
    md_path = RETURN_DIR / f"local_search_{stamp}.md"
    summary_path = RETURN_DIR / f"local_search_{stamp}_微信摘要.txt"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    write_xlsx(xlsx_path, HEADERS, rows, "local_search")
    lines = ["# InfoRadar 本地优先检索", "", f"指令：{query}", f"匹配数量：{len(rows)}", "", "## 前10条", ""]
    for row in rows[:10]:
        lines.append(f"- {row.get('序号')}. {row.get('标题')} | {row.get('发布时间') or '时间未知'} | {row.get('来源集合')} | 分数 {row.get('匹配分数')}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    summary = ["【InfoRadar 本地检索】", "", f"指令：{query}", f"本地找到：{len(rows)} 条", "", "前5条："]
    if rows:
        for row in rows[:5]:
            summary.append(f"{row.get('序号')}. {row.get('标题')}")
            summary.append(f"   时间：{row.get('发布时间') or '时间未知'}")
            summary.append(f"   来源：{row.get('来源集合')} / {row.get('主分类') or row.get('全域分类') or '-'}")
    else:
        summary.append("- 暂无匹配")
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    return {
        "return_csv": str(csv_path),
        "return_xlsx": str(xlsx_path),
        "markdown": str(md_path),
        "return_summary": str(summary_path),
        "output_files": [str(csv_path), str(xlsx_path), str(md_path), str(summary_path)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar local-first search")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    stamp = now_stamp()
    rows = search_local(args.query, args.limit)
    outputs = write_outputs(args.query, rows, stamp)
    result = {
        "success": True,
        "query": args.query,
        "local_match_count": len(rows),
        "folo_rss_match_count": sum(1 for row in rows if row.get("来源集合") == "folo_report_table"),
        "manual_match_count": sum(1 for row in rows if row.get("来源集合") == "manual_collected_items" or row.get("来源类型") == "manual_collected"),
        **outputs,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
