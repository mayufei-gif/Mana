#!/usr/bin/env python3
import argparse
import os
import datetime as dt
import os
import json
import os
import re
import os
import zipfile
import os
import xml.etree.ElementTree as ET
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
LATEST_STATUS = ROOT / "logs" / "latest_status.json"
DEEP_DIR = ROOT / "reports" / "deep_research"


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def cell_col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref or "")
    if not letters:
        return 1
    value = 0
    for ch in letters.group(1):
        value = value * 26 + (ord(ch) - 64)
    return value


def parse_inline_xlsx(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        xml = z.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(xml)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    table: list[list[str]] = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        cells: dict[int, str] = {}
        for cell in row.findall("m:c", ns):
            ref = cell.attrib.get("r", "")
            idx = cell_col_index(ref)
            texts = [t.text or "" for t in cell.findall(".//m:t", ns)]
            cells[idx] = "".join(texts)
        if not cells:
            continue
        max_idx = max(cells)
        table.append([cells.get(i, "") for i in range(1, max_idx + 1)])
    if not table:
        return []
    headers = table[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in table[1:]]


def latest_xlsx() -> Path:
    status = read_json(LATEST_STATUS)
    candidates: list[str] = []
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    for value in [details.get("xlsx"), status.get("summary_file"), *(status.get("output_files") or [])]:
        if isinstance(value, str):
            candidates.append(value)
    for value in candidates:
        if value.lower().endswith(".xlsx") and "FOLO_" in Path(value).name:
            path = Path(value)
            if path.exists():
                return path
    raise FileNotFoundError("未找到最近一次 Folo 表格。请先运行：今日情报 / 今日政策 / 今日AI")


def normalize_selector(selector: str) -> str:
    text = " ".join((selector or "").strip().split())
    text = re.sub(r"^第", "", text)
    text = re.sub(r"条$", "", text)
    text = text.lstrip("#")
    return text.strip()


def select_row(rows: list[dict], selector: str) -> dict:
    normalized = normalize_selector(selector or "1")
    if normalized.isdigit():
        wanted = int(normalized)
        for row in rows:
            if str(row.get("序号", "")).strip() == str(wanted):
                return row
        if 1 <= wanted <= len(rows):
            return rows[wanted - 1]
        raise IndexError(f"表格中没有第 {wanted} 条")
    needle = normalized.lower()
    matches = [
        row
        for row in rows
        if needle in str(row.get("标题", "")).lower()
        or needle in str(row.get("来源名称", "")).lower()
        or needle in str(row.get("标签", "")).lower()
    ]
    if not matches:
        raise LookupError(f"没有找到匹配条目：{selector}")
    return matches[0]


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", text).strip("_")[:60] or "item"


def value(row: dict, key: str, default: str = "-") -> str:
    text = str(row.get(key, "")).strip()
    return text if text else default


def make_report(row: dict, selector: str, xlsx_path: Path) -> tuple[Path, Path]:
    title = value(row, "标题")
    base = f"deep_dive_{safe_name(selector)}_{stamp()}"
    report_path = DEEP_DIR / f"{base}.md"
    return_report = RETURN_DIR / f"{base}.md"
    summary_path = RETURN_DIR / f"{base}_微信摘要.txt"
    for path in [DEEP_DIR, RETURN_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    lines = [
        "# InfoRadar 深挖报告",
        "",
        f"生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"来源表格：{xlsx_path}",
        "",
        "## 一、信息本体",
        "",
        f"- 标题：{title}",
        f"- 来源：{value(row, '来源名称')}",
        f"- 发布时间：{value(row, '发布时间')}",
        f"- Folo 位置：{value(row, 'Folo文件夹路径')}",
        f"- Folo 订阅源：{value(row, 'Folo订阅源名称')}",
        f"- 原文链接：{value(row, '原文URL')}",
        f"- 订阅源 URL：{value(row, '订阅源URL')}",
        "",
        "## 二、分类与评分",
        "",
        f"- 主分类：{value(row, '主分类')}",
        f"- 标签：{value(row, '标签')}",
        f"- 相关度评分：{value(row, '相关度评分')}",
        f"- 来源权威度：{value(row, '来源权威度')}",
        f"- 行动价值：{value(row, '行动价值')}",
        f"- 机会价值：{value(row, '机会价值')}",
        f"- 风险等级：{value(row, '风险等级')}",
        "",
        "## 三、为什么与你有关",
        "",
        value(row, "为什么与你有关"),
        "",
        "## 四、可能影响你的决策",
        "",
        f"- 决策影响类型：{value(row, '决策影响类型')}",
        f"- 信息差说明：{value(row, '决策影响/信息差说明')}",
        "",
        "## 五、建议行动",
        "",
        value(row, "建议行动"),
        "",
        "## 六、核验与风险",
        "",
        f"- 是否需要官方核验：{value(row, '是否需要官方核验')}",
        f"- 核验状态：{value(row, '核验状态')}",
        f"- 官方原文链接：{value(row, '官方原文链接')}",
        f"- 重复来源/备用链接：{value(row, '重复来源/备用链接')}",
        "",
        "## 七、下一步",
        "",
        "1. 先在 Folo 对应文件夹打开该条内容，确认上下文。",
        "2. 如果涉及招聘、证书、补贴或政策，以官网原文为准。",
        "3. 如果判断有用，可在微信继续发送：这个有用 / 以后多关注 关键词。",
    ]
    text = "\n".join(lines)
    report_path.write_text(text, encoding="utf-8")
    return_report.write_text(text, encoding="utf-8")

    summary_lines = [
        "【InfoRadar 深挖】",
        "",
        f"标题：{title}",
        f"来源：{value(row, '来源名称')}",
        f"Folo位置：{value(row, 'Folo文件夹路径')}",
        f"分类：{value(row, '主分类')} / {value(row, '标签')}",
        f"评分：{value(row, '相关度评分')}",
        "",
        f"为什么与你有关：{value(row, '为什么与你有关')}",
        "",
        f"建议行动：{value(row, '建议行动')}",
        "",
        f"完整报告：{return_report}",
    ]
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    return return_report, summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar deep dive for latest Folo item")
    parser.add_argument("--selector", default="1", help="第1条 / 1 / 标题关键词")
    args = parser.parse_args()

    try:
        xlsx_path = latest_xlsx()
        rows = parse_inline_xlsx(xlsx_path)
        row = select_row(rows, args.selector)
        report, summary = make_report(row, args.selector, xlsx_path)
        result = {
            "success": True,
            "selector": args.selector,
            "xlsx": str(xlsx_path),
            "report": str(report),
            "return_summary": str(summary),
            "output_files": [str(report), str(summary)],
            "title": row.get("标题", ""),
            "source": row.get("来源名称", ""),
            "folo_folder": row.get("Folo文件夹路径", ""),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result = {
            "success": False,
            "error": repr(exc),
            "output_files": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
