#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.file_index import search_personal_radar  # noqa: E402


QUERIES = ["学校", "山西晋中理工", "奖学金", "入团", "比赛", "就业"]
SCHOOL_MARKERS = ["山西晋中理工", "晋中理工", "sxjzit.edu.cn", "我的学校", "官网观察源"]


def compact_result(item: dict) -> dict:
    payload = item.get("payload") or {}
    collection_type = item.get("collection_type") or payload.get("collection_type") or ""
    school_category = item.get("school_category") or payload.get("school_category") or ""
    return {
        "title": item.get("title") or "",
        "kind": item.get("kind") or "",
        "meta": item.get("meta") or "",
        "collection_type": collection_type,
        "school_category": school_category,
        "has_folo": bool(item.get("folo_url")),
    }


def is_school_related(item: dict) -> bool:
    payload = item.get("payload") or {}
    text = " ".join(
        str(value or "")
        for value in [
            item.get("title"),
            item.get("meta"),
            item.get("url"),
            item.get("collection_type"),
            item.get("school_category"),
            payload.get("来源名称"),
            payload.get("原文URL"),
            payload.get("collection_type"),
            payload.get("school_category"),
            payload.get("Folo文件夹路径"),
        ]
    )
    return any(marker in text for marker in SCHOOL_MARKERS)


def main() -> int:
    failures: list[str] = []
    rows: list[dict] = []
    for query in QUERIES:
        data = search_personal_radar(query, "all", 30)
        results = data.get("results") or []
        first = results[0] if results else {}
        school_result_exists = any(is_school_related(item) for item in results)
        first_is_school = is_school_related(first) if first else False
        first_payload = first.get("payload") or {}
        first_collection_type = first.get("collection_type") or first_payload.get("collection_type") or ""

        if query in {"学校", "山西晋中理工"} and not first_is_school:
            failures.append(f"{query}: first result is not school related")
        if school_result_exists and not first_is_school:
            failures.append(f"{query}: school related result exists but is not ranked first")
        if first_collection_type == "官网观察源" and first.get("folo_url"):
            failures.append(f"{query}: watch_only result still has folo_url")

        rows.append(
            {
                "query": query,
                "total": data.get("total"),
                "school_result_exists": school_result_exists,
                "first_is_school": first_is_school,
                "first": compact_result(first),
            }
        )

    print(json.dumps({"ok": not failures, "checks": rows, "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
