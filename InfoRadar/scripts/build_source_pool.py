#!/usr/bin/env python3
import argparse
import os
import csv
import os
import datetime as dt
import os
import json
import os
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
DEFAULT_INPUT = ROOT / "sources" / "candidate_sources.csv"
DEFAULT_OUTPUT_CSV = ROOT / "sources" / "source_pool.csv"
DEFAULT_OUTPUT_XLSX = ROOT / "sources" / "source_pool.xlsx"
DEFAULT_OUTPUT_OPML = ROOT / "sources" / "opml" / "InfoRadar_source_pool.opml"
VERSIONS_DIR = ROOT / "sources" / "source_pool_versions"


POOL_HEADERS = [
    "序号",
    "源名称",
    "源类型",
    "RSS链接",
    "官网链接",
    "Folo文件夹路径",
    "Folo订阅源名称",
    "主分类",
    "标签",
    "是否已加入Folo",
    "是否建议订阅",
    "订阅优先级",
    "来源权威度",
    "更新频率",
    "最近更新时间",
    "长期价值评分",
    "是否失效",
    "重复源ID",
    "加入时间",
    "最后检查时间",
    "备注",
]


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def source_id(row: dict) -> str:
    return (row.get("源ID") or row.get("重复源ID") or "").strip()


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def score_from_candidate(row: dict) -> int:
    raw = row.get("相关度评分", "")
    try:
        score = int(raw)
    except Exception:
        score = 70
    return max(10, min(score, 100))


def authority_from_candidate(row: dict) -> int:
    raw = row.get("来源权威度", "")
    try:
        return int(raw)
    except Exception:
        return 75


def priority_label(row: dict) -> str:
    score = score_from_candidate(row)
    if score >= 85:
        return "高"
    if score >= 70:
        return "中"
    return "低"


def build_pool_rows(candidate_rows: list[dict], task_id: str) -> list[dict]:
    now = now_text()
    out = []
    for row in candidate_rows:
        if row.get("是否可被Folo添加") != "是":
            continue
        if not row.get("RSS链接", "").strip():
            continue
        pool = {header: "" for header in POOL_HEADERS}
        pool["源名称"] = row.get("源名称", "")
        pool["源类型"] = row.get("源类型", "官网")
        pool["RSS链接"] = row.get("RSS链接", "")
        pool["官网链接"] = row.get("官网链接", "")
        pool["Folo文件夹路径"] = row.get("推荐Folo文件夹", "") or row.get("Folo文件夹路径", "待定位")
        pool["Folo订阅源名称"] = row.get("源名称", "")
        pool["主分类"] = row.get("主分类", "")
        pool["标签"] = row.get("标签", "")
        pool["是否已加入Folo"] = "否"
        pool["是否建议订阅"] = "是"
        pool["订阅优先级"] = priority_label(row)
        pool["来源权威度"] = authority_from_candidate(row)
        pool["更新频率"] = row.get("更新频率", "待观察")
        pool["最近更新时间"] = row.get("最近更新时间", "")
        pool["长期价值评分"] = score_from_candidate(row)
        pool["是否失效"] = "否"
        pool["重复源ID"] = source_id(row)
        pool["加入时间"] = now
        pool["最后检查时间"] = now
        pool["备注"] = row.get("备注", "") or row.get("适合你的原因", "")
        out.append(pool)

    # 按优先级和评分排序，方便后续人工加源。
    out.sort(key=lambda r: ({"高": 0, "中": 1, "低": 2}.get(r["订阅优先级"], 9), -int(r["长期价值评分"])))
    for idx, row in enumerate(out, 1):
        row["序号"] = idx
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=POOL_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def write_opml(path: Path, rows: list[dict], title: str) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row.get("Folo文件夹路径", "待定位") or "待定位"].append(row)

    outlines: list[str] = []
    for folder in sorted(groups):
        children = []
        for row in groups[folder]:
            text = xml_escape(row.get("源名称", ""))
            rss = xml_escape(row.get("RSS链接", ""))
            html = xml_escape(row.get("官网链接", ""))
            children.append(
                f'<outline text="{text}" title="{text}" type="rss" xmlUrl="{rss}" htmlUrl="{html}" />'
            )
        folder_text = xml_escape(folder)
        outlines.append(f'<outline text="{folder_text}" title="{folder_text}">' + "".join(children) + "</outline>")

    created = dt.datetime.now(dt.UTC).isoformat()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<opml version=\"2.0\">"
        "<head>"
        f"<title>{xml_escape(title)}</title>"
        f"<dateCreated>{created}</dateCreated>"
        "</head><body>"
        + "".join(outlines)
        + "</body></opml>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")


def copy_to_return(path: Path, dest_name: str | None = None) -> Path:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    dest = RETURN_DIR / (dest_name or path.name)
    dest.write_bytes(path.read_bytes())
    return dest


def write_summary(path: Path, rows: list[dict], output_opml: Path, output_xlsx: Path) -> None:
    lines = [
        "# InfoRadar 源池摘要",
        "",
        f"生成时间：{now_text()}",
        f"源池数量：{len(rows)}",
        f"OPML：{output_opml}",
        f"Excel：{output_xlsx}",
        "",
        "## 可加入 Folo 的源",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"- {row['序号']}. {row['源名称']}",
                f"  - 文件夹：{row['Folo文件夹路径']}",
                f"  - RSS：{row['RSS链接']}",
                f"  - 优先级：{row['订阅优先级']}",
                f"  - 评分：{row['长期价值评分']}",
                f"  - 备注：{row['备注']}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build source pool from candidate sources")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-xlsx", default=str(DEFAULT_OUTPUT_XLSX))
    parser.add_argument("--output-opml", default=str(DEFAULT_OUTPUT_OPML))
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()

    task_id = args.task_id or f"sourcepool_{stamp()}"
    input_path = Path(args.input)
    candidates = read_rows(input_path)
    pool_rows = build_pool_rows(candidates, task_id)

    output_csv = Path(args.output_csv)
    output_xlsx = Path(args.output_xlsx)
    output_opml = Path(args.output_opml)

    write_csv(output_csv, pool_rows)
    write_xlsx(output_xlsx, POOL_HEADERS, pool_rows, "source_pool")
    write_opml(output_opml, pool_rows, "InfoRadar Source Pool")
    summary = ROOT / "reports" / "source_discovery" / f"{task_id}_源池摘要.md"
    write_summary(summary, pool_rows, output_opml, output_xlsx)

    versions_csv = VERSIONS_DIR / f"source_pool_{task_id}.csv"
    versions_xlsx = VERSIONS_DIR / f"source_pool_{task_id}.xlsx"
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    versions_csv.write_bytes(output_csv.read_bytes())
    versions_xlsx.write_bytes(output_xlsx.read_bytes())

    return_csv = copy_to_return(output_csv, f"source_pool_{task_id}.csv")
    return_xlsx = copy_to_return(output_xlsx, f"source_pool_{task_id}.xlsx")
    return_opml = copy_to_return(output_opml, f"source_pool_{task_id}.opml")
    return_summary = copy_to_return(summary, f"source_pool_{task_id}_源池摘要.md")

    result = {
        "success": True,
        "task_id": task_id,
        "input": str(input_path),
        "source_count": len(pool_rows),
        "csv": str(output_csv),
        "xlsx": str(output_xlsx),
        "opml": str(output_opml),
        "version_csv": str(versions_csv),
        "version_xlsx": str(versions_xlsx),
        "return_csv": str(return_csv),
        "return_xlsx": str(return_xlsx),
        "return_opml": str(return_opml),
        "return_summary": str(return_summary),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
