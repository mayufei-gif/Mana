#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import datetime as dt
import os
import json
import os
import xml.etree.ElementTree as ET
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
OPML_FILE = RETURN_DIR / "all_domain_folo_import_ready.opml"
SOURCE_POOL = ROOT / "sources" / "source_pool_from_folo.csv"
STATUS_XLSX = RETURN_DIR / "all_domain_folo_import_after_status.xlsx"
SUMMARY_TXT = RETURN_DIR / "mvp2_7_folo_import_smoke_微信摘要.txt"
LOG_DIR = ROOT / "logs"

HEADERS = [
    "序号",
    "OPML源名称",
    "OPML文件夹路径",
    "OPML_RSS链接",
    "OPML官网链接",
    "是否在当前Folo源池",
    "匹配方式",
    "当前Folo源名称",
    "当前Folo文件夹路径",
    "当前源池RSS链接",
    "当前源池官网链接",
    "当前源池是否失效",
    "当前源池错误类型",
    "当前源池最后检查时间",
    "处理建议",
    "备注",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def file_time(path: Path) -> str:
    if not path.exists():
        return ""
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def normalize_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw.rstrip("/").lower()
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def parse_opml(path: Path) -> list[dict]:
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    rows: list[dict] = []

    def walk(elem: ET.Element, folder: list[str]) -> None:
        for child in list(elem):
            if child.tag.lower().endswith("outline"):
                text = child.attrib.get("text") or child.attrib.get("title") or ""
                xml_url = child.attrib.get("xmlUrl") or child.attrib.get("xmlurl") or ""
                if xml_url:
                    rows.append(
                        {
                            "name": text,
                            "folder": "/".join(folder),
                            "rss": xml_url,
                            "html": child.attrib.get("htmlUrl") or child.attrib.get("htmlurl") or "",
                        }
                    )
                else:
                    walk(child, [*folder, text] if text else folder)
            else:
                walk(child, folder)

    body = root.find("body")
    walk(body if body is not None else root, [])
    return rows


def build_indexes(source_rows: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_rss: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for row in source_rows:
        for key in ["RSS链接", "可抓取RSS链接"]:
            url = normalize_url(row.get(key, ""))
            if url:
                by_rss[url] = row
        name = (row.get("源名称") or row.get("Folo订阅源名称") or "").strip().lower()
        if name:
            by_name[name] = row
    return by_rss, by_name


def audit_rows(opml_rows: list[dict], source_rows: list[dict], source_pool_stale: bool) -> list[dict]:
    by_rss, by_name = build_indexes(source_rows)
    rows: list[dict] = []
    for idx, item in enumerate(opml_rows, 1):
        rss_key = normalize_url(item.get("rss", ""))
        name_key = (item.get("name") or "").strip().lower()
        match = by_rss.get(rss_key)
        match_type = "RSS链接"
        if not match and name_key:
            match = by_name.get(name_key)
            match_type = "源名称" if match else ""
        found = bool(match)
        if found:
            suggestion = "已在当前 Folo 源池中；后续观察文章更新质量。"
            note = ""
        elif source_pool_stale:
            suggestion = "当前 Folo 源池早于 OPML 生成时间，可能尚未导入或尚未重新导出 Folo 订阅。"
            note = "请在 Folo 导入 OPML 后，重新导出/同步 folo_subscriptions_current.json，再运行本验收。"
        else:
            suggestion = "未在当前 Folo 源池中发现；需要确认 OPML 是否已导入 Folo。"
            note = "如果已导入，请刷新/重新导出 Folo 订阅数据。"
        rows.append(
            {
                "序号": idx,
                "OPML源名称": item.get("name", ""),
                "OPML文件夹路径": item.get("folder", ""),
                "OPML_RSS链接": item.get("rss", ""),
                "OPML官网链接": item.get("html", ""),
                "是否在当前Folo源池": "是" if found else "否",
                "匹配方式": match_type if found else "",
                "当前Folo源名称": (match or {}).get("源名称", ""),
                "当前Folo文件夹路径": (match or {}).get("Folo文件夹路径", ""),
                "当前源池RSS链接": (match or {}).get("RSS链接", ""),
                "当前源池官网链接": (match or {}).get("官网链接", ""),
                "当前源池是否失效": (match or {}).get("是否失效", ""),
                "当前源池错误类型": (match or {}).get("错误类型", ""),
                "当前源池最后检查时间": (match or {}).get("最后检查时间", ""),
                "处理建议": suggestion,
                "备注": note,
            }
        )
    return rows


def write_report(path: Path, rows: list[dict], source_rows: list[dict], source_pool_stale: bool) -> None:
    total = len(rows)
    matched = sum(1 for row in rows if row.get("是否在当前Folo源池") == "是")
    missing = total - matched
    lines = [
        "# InfoRadar MVP-2.7 Folo 导入后源池状态",
        "",
        f"生成时间：{now_text()}",
        "",
        "## 文件状态",
        "",
        f"- OPML：{OPML_FILE}",
        f"- OPML 修改时间：{file_time(OPML_FILE)}",
        f"- 当前 Folo 源池：{SOURCE_POOL}",
        f"- 当前 Folo 源池修改时间：{file_time(SOURCE_POOL)}",
        f"- 当前 Folo 源池条目数：{len(source_rows)}",
        f"- 源池是否可能旧于 OPML：{'是' if source_pool_stale else '否'}",
        "",
        "## 验收结果",
        "",
        f"- OPML 待导入源：{total}",
        f"- 已在当前 Folo 源池：{matched}",
        f"- 未在当前 Folo 源池：{missing}",
        "",
    ]
    if source_pool_stale:
        lines.extend(
            [
                "## 结论",
                "",
                "当前 `source_pool_from_folo.csv` 的修改时间早于 OPML，说明当前本地 Folo 导出数据大概率还没有反映这次导入。",
                "",
                "下一步：在 Folo 中导入 `all_domain_folo_import_ready.opml` 后，重新导出/同步 Folo 订阅 JSON，再运行 `同步Folo全域源` 和 `Folo导入验收`。",
                "",
            ]
        )
    elif missing:
        lines.extend(
            [
                "## 结论",
                "",
                "部分 OPML 源尚未出现在当前 Folo 源池中，需要确认是否导入成功，或者 Folo 是否已经刷新并导出最新订阅数据。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## 结论",
                "",
                "OPML 中的源已全部出现在当前 Folo 源池中，可以继续运行 `全域情报` 做内容质量验收。",
                "",
            ]
        )

    lines.extend(["## 明细", "", "| 源 | 文件夹 | 是否在Folo源池 | 建议 |", "|---|---|---|---|"])
    for row in rows:
        lines.append(
            f"| {row.get('OPML源名称')} | {row.get('OPML文件夹路径')} | {row.get('是否在当前Folo源池')} | {row.get('处理建议')} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(path: Path, report_path: Path, rows: list[dict], source_pool_stale: bool) -> None:
    total = len(rows)
    matched = sum(1 for row in rows if row.get("是否在当前Folo源池") == "是")
    missing = total - matched
    lines = [
        "【InfoRadar MVP-2.7 Folo导入验收】",
        "",
        f"OPML源：{total}",
        f"已在当前Folo源池：{matched}",
        f"未检测到：{missing}",
        f"源池可能旧于OPML：{'是' if source_pool_stale else '否'}",
        "",
        f"状态表：{STATUS_XLSX}",
        f"报告：{report_path}",
    ]
    if source_pool_stale:
        lines.extend(["", "下一步：先在 Folo 导入 OPML，并重新同步/导出订阅数据。"])
    elif missing:
        lines.extend(["", "下一步：确认 Folo 是否已导入并刷新订阅。"])
    else:
        lines.extend(["", "下一步：运行 全域情报 做质量验收。"])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    opml_rows = parse_opml(OPML_FILE)
    source_rows = read_csv(SOURCE_POOL)
    source_pool_stale = SOURCE_POOL.exists() and OPML_FILE.exists() and SOURCE_POOL.stat().st_mtime < OPML_FILE.stat().st_mtime
    rows = audit_rows(opml_rows, source_rows, source_pool_stale)
    report_path = RETURN_DIR / f"InfoRadar_MVP2_7_Folo导入后源池状态_{today_stamp()}.md"

    write_xlsx(STATUS_XLSX, HEADERS, rows, "mvp2_7_status")
    write_report(report_path, rows, source_rows, source_pool_stale)
    write_summary(SUMMARY_TXT, report_path, rows, source_pool_stale)

    result = {
        "success": True,
        "opml": str(OPML_FILE),
        "source_pool": str(SOURCE_POOL),
        "opml_source_count": len(rows),
        "matched_count": sum(1 for row in rows if row.get("是否在当前Folo源池") == "是"),
        "missing_count": sum(1 for row in rows if row.get("是否在当前Folo源池") != "是"),
        "source_pool_count": len(source_rows),
        "source_pool_stale": source_pool_stale,
        "return_xlsx": str(STATUS_XLSX),
        "return_summary": str(SUMMARY_TXT),
        "report": str(report_path),
        "output_files": [str(STATUS_XLSX), str(report_path), str(SUMMARY_TXT)],
    }
    append_jsonl(LOG_DIR / "mvp2_7_folo_import_smoke.jsonl", {"time": now_text(), **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
