#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIRS = [
    ROOT / "data" / "raw" / "folo_export",
    ROOT / "data" / "raw" / "rss_items",
    ROOT / "data" / "raw" / "manual_clip",
]
NORMALIZED_DIR = ROOT / "data" / "normalized"


STANDARD_FIELDS = [
    "标题",
    "来源名称",
    "原文URL",
    "订阅源URL",
    "Folo文件夹路径",
    "Folo订阅源名称",
    "发布时间",
    "摘要",
]


FIELD_ALIASES = {
    "title": "标题",
    "标题": "标题",
    "name": "标题",
    "source": "来源名称",
    "来源": "来源名称",
    "来源名称": "来源名称",
    "url": "原文URL",
    "link": "原文URL",
    "原文URL": "原文URL",
    "feed": "订阅源URL",
    "feed_url": "订阅源URL",
    "订阅源URL": "订阅源URL",
    "folder": "Folo文件夹路径",
    "Folo文件夹路径": "Folo文件夹路径",
    "published": "发布时间",
    "date": "发布时间",
    "发布时间": "发布时间",
    "summary": "摘要",
    "摘要": "摘要",
    "content": "摘要",
}


def normalize_record(record: dict) -> dict:
    out = {field: "" for field in STANDARD_FIELDS}
    for key, value in record.items():
        mapped = FIELD_ALIASES.get(str(key).strip(), str(key).strip())
        if mapped in out:
            out[mapped] = "" if value is None else str(value).strip()
    if not out["Folo订阅源名称"]:
        out["Folo订阅源名称"] = out["来源名称"]
    if not out["Folo文件夹路径"]:
        out["Folo文件夹路径"] = "待定位"
    return out


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [normalize_record(row) for row in csv.DictReader(f)]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="\n") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(normalize_record(json.loads(line)))
    return rows


def collect_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    if inputs:
        paths = [Path(p) for p in inputs]
    else:
        paths = DEFAULT_INPUT_DIRS
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.glob("*.csv")))
            files.extend(sorted(path.glob("*.jsonl")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Folo/RSS/manual exported items")
    parser.add_argument("--input", action="append", help="input file or directory; can repeat")
    parser.add_argument("--output", default=str(NORMALIZED_DIR / "folo_items_normalized.csv"))
    args = parser.parse_args()

    rows: list[dict] = []
    for file in collect_files(args.input or []):
        if file.suffix.lower() == ".csv":
            rows.extend(read_csv(file))
        elif file.suffix.lower() == ".jsonl":
            rows.extend(read_jsonl(file))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"success": True, "output": str(output), "rows": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
