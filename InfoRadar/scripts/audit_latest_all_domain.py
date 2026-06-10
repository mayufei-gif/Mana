#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import datetime as dt
import os
import json
import os
import re
import os
import xml.etree.ElementTree as ET
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
DEDUPED_DIR = ROOT / "data" / "deduped"
OPML_FILE = RETURN_DIR / "all_domain_folo_import_ready.opml"
SUMMARY_TXT = RETURN_DIR / "mvp2_7_all_domain_quality_微信摘要.txt"
LOG_DIR = ROOT / "logs"


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


def latest_all_domain_csv() -> Path | None:
    files = [path for path in DEDUPED_DIR.glob("FOLO_全域情报_*.csv") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def latest_all_domain_xlsx() -> Path | None:
    files = [path for path in RETURN_DIR.glob("FOLO_全域情报_*.xlsx") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def parse_opml_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    root = ET.parse(path).getroot()
    names: set[str] = set()
    for elem in root.iter():
        if not elem.tag.lower().endswith("outline"):
            continue
        if elem.attrib.get("xmlUrl") or elem.attrib.get("xmlurl"):
            name = (elem.attrib.get("text") or elem.attrib.get("title") or "").strip()
            if name:
                names.add(name)
    return names


def duplicates(rows: list[dict], key: str) -> int:
    seen: set[str] = set()
    dupes = 0
    for row in rows:
        value = (row.get(key) or "").strip().lower()
        if not value:
            continue
        if value in seen:
            dupes += 1
        seen.add(value)
    return dupes


def high_risk(row: dict) -> bool:
    hay = " ".join(str(row.get(key, "")) for key in ["标题", "主分类", "标签", "风险等级", "备注"])
    return row.get("风险等级") == "高" or any(term in hay for term in ["破解版", "注册机", "免激活", "盗版", "灰产", "培训贷", "虚假招聘"])


def count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = row.get(key) or "未标记"
        out[value] = out.get(value, 0) + 1
    return out


def write_report(path: Path, csv_path: Path, xlsx_path: Path | None, rows: list[dict], opml_names: set[str]) -> dict:
    top10 = rows[:10]
    top30 = rows[:30]
    duplicate_titles_top30 = duplicates(top30, "标题")
    url_anomaly_top30 = sum(1 for row in top30 if row.get("URL异常") == "是" or not row.get("原文URL", "").strip())
    high_risk_top10 = sum(1 for row in top10 if high_risk(row))
    empty_action_top30 = sum(1 for row in top30 if not row.get("建议行动", "").strip())
    imported_source_rows = [row for row in rows if row.get("来源名称") in opml_names or row.get("Folo订阅源名称") in opml_names]
    by_section = count_by(rows, "全域栏目")
    by_layer = count_by(rows, "源层级")
    by_platform = count_by(rows, "平台")

    metrics = {
        "row_count": len(rows),
        "duplicate_titles_top30": duplicate_titles_top30,
        "url_anomaly_top30": url_anomaly_top30,
        "high_risk_top10": high_risk_top10,
        "empty_action_top30": empty_action_top30,
        "opml_source_count": len(opml_names),
        "opml_source_item_count": len(imported_source_rows),
    }

    lines = [
        "# InfoRadar MVP-2.7 全域情报导入后质量验收",
        "",
        f"生成时间：{now_text()}",
        f"CSV：{csv_path}",
        f"Excel：{xlsx_path or ''}",
        f"OPML：{OPML_FILE}",
        "",
        "## 总览",
        "",
        f"- 全域情报条目数：{len(rows)}",
        f"- 前30标题重复：{duplicate_titles_top30}",
        f"- 前30 URL异常：{url_anomaly_top30}",
        f"- 前10高风险：{high_risk_top10}",
        f"- 前30建议行动为空：{empty_action_top30}",
        f"- OPML源数量：{len(opml_names)}",
        f"- 来自OPML源的条目数：{len(imported_source_rows)}",
        "",
        "## 栏目分布",
        "",
    ]
    for name, count in sorted(by_section.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}：{count}")
    lines.extend(["", "## 源层级分布", ""])
    for name, count in sorted(by_layer.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {name}：{count}")
    lines.extend(["", "## 平台分布 TOP10", ""])
    for name, count in sorted(by_platform.items(), key=lambda item: (-item[1], item[0]))[:10]:
        lines.append(f"- {name}：{count}")
    lines.extend(["", "## 前10条", ""])
    for row in top10:
        lines.append(f"- {row.get('标题')} | {row.get('全域栏目')} | {row.get('来源名称')} | 风险：{row.get('风险等级')}")
    lines.extend(["", "## 结论", ""])
    if duplicate_titles_top30 == 0 and url_anomaly_top30 == 0 and high_risk_top10 == 0:
        lines.append("基础质量验收通过：前30无标题重复，前30无 URL 异常，前10无高风险内容。")
    else:
        lines.append("基础质量验收未完全通过，需要按异常项继续治理排序、URL 或风险规则。")
    if not imported_source_rows:
        lines.append("当前全域情报中暂未检测到来自本轮 OPML 可导入源的条目；可能是 Folo 尚未导入/刷新，或这些源暂时无新内容。")
    path.write_text("\n".join(lines), encoding="utf-8")
    return metrics


def write_summary(path: Path, report_path: Path, metrics: dict) -> None:
    lines = [
        "【InfoRadar MVP-2.7 全域情报质量验收】",
        "",
        f"条目数：{metrics.get('row_count')}",
        f"前30标题重复：{metrics.get('duplicate_titles_top30')}",
        f"前30 URL异常：{metrics.get('url_anomaly_top30')}",
        f"前10高风险：{metrics.get('high_risk_top10')}",
        f"OPML源条目数：{metrics.get('opml_source_item_count')}",
        "",
        f"报告：{report_path}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    csv_path = latest_all_domain_csv()
    if not csv_path:
        result = {"success": False, "error": "没有找到 FOLO_全域情报_*.csv", "output_files": []}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    xlsx_path = latest_all_domain_xlsx()
    rows = read_csv(csv_path)
    opml_names = parse_opml_names(OPML_FILE)
    report_path = RETURN_DIR / f"InfoRadar_MVP2_7_全域情报导入后质量验收_{today_stamp()}.md"
    metrics = write_report(report_path, csv_path, xlsx_path, rows, opml_names)
    write_summary(SUMMARY_TXT, report_path, metrics)
    result = {
        "success": True,
        "csv": str(csv_path),
        "xlsx": str(xlsx_path) if xlsx_path else "",
        "report": str(report_path),
        "return_summary": str(SUMMARY_TXT),
        "output_files": [str(report_path), str(SUMMARY_TXT)],
        **metrics,
    }
    append_jsonl(LOG_DIR / "mvp2_7_all_domain_quality.jsonl", {"time": now_text(), **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
