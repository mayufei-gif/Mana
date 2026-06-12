#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import datetime as dt
import hashlib
import os
import json
import os
import re
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
UPDATE_DIR = ROOT / "data" / "watch" / "updates"
SNAPSHOT_DIR = ROOT / "data" / "watch" / "snapshots"
NORMALIZED_DIR = ROOT / "data" / "normalized"

HEADERS = [
    "标题",
    "摘要",
    "来源名称",
    "订阅源URL",
    "原文URL",
    "Folo文件夹路径",
    "发布时间",
    "input_source",
    "source_type",
    "school_category",
    "detected_at",
    "last_seen_at",
    "is_new",
    "source_trace_id",
    "dedupe_key",
    "平台",
    "主分类",
    "broad_category",
    "source_layer",
    "decision_scope",
    "是否需要核验",
    "风险等级",
    "为什么与你有关",
    "建议行动",
    "是否进入今日情报",
    "是否进入长期知识库",
    "备注",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def sha(text: str, length: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:length]


def visible_date_from_title(title: str) -> str:
    text = compact(title)
    match = re.search(r"^\s*(\d{1,2})\s+(20\d{2})[./-](\d{1,2})\b", text)
    if match:
        day, year, month = match.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            return ""
    match = re.search(r"\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            return ""
    return ""


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


def latest_update_path(date_text: str = "") -> Path | None:
    if date_text:
        path = UPDATE_DIR / f"watch_updates_{date_text}.jsonl"
        return path if path.exists() else None
    paths = sorted(UPDATE_DIR.glob("watch_updates_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0] if paths else None


PRIMARY_SCHOOL_TERMS = ["山西晋中理工", "晋中理工", "sxjzit.edu.cn"]


def is_primary_school_text(text: str) -> bool:
    return any(term in text for term in PRIMARY_SCHOOL_TERMS)


def infer_broad_from_text(text: str) -> str:
    if is_primary_school_text(text):
        return "我的学校"
    if any(word in text for word in ["招聘", "校招", "实习", "岗位", "就业", "山西焦煤", "霍州煤电", "晋能控股", "太重", "潞安"]):
        return "就业招聘"
    if any(word in text for word in ["电工证", "证书", "补贴", "报名", "考试", "职业技能"]):
        return "职业证书"
    if any(word in text for word in ["PLC", "变频器", "ACS800", "ABB", "工业机器人", "AutoCAD", "EPLAN", "电气维修", "控制柜"]):
        return "工业技术"
    if any(word in text for word in ["政策", "人社", "教育", "工信", "政府"]):
        return "政策风向"
    return "长期观察"


def infer_school_category(text: str) -> str:
    hay = compact(text)
    rules = [
        ("奖学金助学金", ["奖学金", "助学金", "资助", "国家励志", "困难补助"]),
        ("入团团员竞选", ["入团", "团员", "团支部", "团籍", "团课"]),
        ("团委通知", ["团委", "共青团", "青年大学习", "学生会"]),
        ("评优评先", ["评优", "评先", "优秀学生", "先进个人", "先进集体", "三好学生"]),
        ("比赛竞赛", ["比赛", "竞赛", "创新创业", "挑战杯", "互联网+", "大赛", "获奖"]),
        ("校园招聘", ["招聘", "宣讲", "就业", "岗位", "双选会", "校园直聘", "毕业生"]),
        ("毕业相关", ["毕业", "离校", "档案", "论文", "答辩", "毕业设计"]),
        ("实习实践", ["实习", "实践", "实训", "见习"]),
        ("教务通知", ["教务", "考试", "课程", "选课", "补考", "重修", "学籍"]),
        ("学工通知", ["学工", "学生处", "辅导员", "宿舍", "班级", "学生工作"]),
    ]
    for category, keywords in rules:
        if any(word in hay for word in keywords):
            return category
    return "其他学校事务"


def read_snapshot_rows(limit: int = 200) -> list[dict]:
    if not SNAPSHOT_DIR.exists():
        return []
    rows: list[dict] = []
    paths = sorted(SNAPSHOT_DIR.glob("*_latest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        watch_id = compact(data.get("watch_id", "")) or path.stem.replace("_latest", "")
        keyword = compact(data.get("watch_keyword", ""))
        source_name = compact(data.get("source_name", ""))
        fetched_at = compact(data.get("fetched_at", ""))
        source_url = compact(data.get("source_url", ""))
        for item in data.get("items", [])[:30]:
            title = compact(item.get("title", ""))
            url = compact(item.get("url", "")) or source_url
            if not title:
                continue
            broad = infer_broad_from_text(f"{keyword} {source_name} {title} {url}")
            trace = sha(f"{watch_id}|{title}|{url}", 20)
            rows.append(
                {
                    "update_id": f"watch_snapshot_{trace}",
                    "watch_id": watch_id,
                    "watch_keyword": keyword,
                    "source_name": source_name,
                    "title": title,
                    "url": url,
                    "published_at": compact(item.get("published_at", "")),
                    "detected_at": fetched_at,
                    "last_seen_at": fetched_at,
                    "broad_category": broad,
                    "source_layer": "A_core" if broad in {"我的学校", "就业招聘", "职业证书", "政策风向"} else "B_observe",
                    "decision_scope": "学校行动" if broad == "我的学校" else ("职业成长" if broad in {"就业招聘", "职业证书", "工业技术"} else "环境判断"),
                    "risk_level": "低",
                    "why_relevant": "这是 watch_only 官网观察源的当前公开条目；因为该源没有稳定 RSS，所以按官网快照进入 InfoRadar，需要打开原文核验发布时间和适用条件。",
                    "suggested_action": "打开公开原文核验发布时间、截止时间和适用范围；重要事项再加入今日行动或深挖。",
                    "status": "current_snapshot",
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def main_category(broad: str) -> str:
    if broad == "我的学校":
        return "我的学校"
    if broad == "就业招聘":
        return "就业招聘"
    if broad == "职业证书":
        return "职业证书"
    if broad == "政策风向":
        return "地方政策"
    return broad or "长期观察"


def matches_topic(row: dict, topic: str = "") -> bool:
    topic = compact(topic)
    if topic in {"", "今日", "今日情报", "全域情报", "全部", "样例"}:
        return True
    hay = " ".join(str(row.get(key, "")) for key in ["标题", "摘要", "来源名称", "原文URL", "Folo文件夹路径", "主分类", "broad_category"])
    broad = row.get("broad_category", "")
    category = row.get("主分类", "")
    if topic == "我的学校":
        return is_primary_school_text(hay)
    if topic == "招聘":
        return broad == "就业招聘" or category == "就业招聘" or any(word in hay for word in ["招聘", "校招", "实习", "岗位", "就业"])
    if topic == "证书":
        return broad == "职业证书" or category == "职业证书" or any(word in hay for word in ["证书", "电工证", "技能补贴", "报名", "考试"])
    if topic == "技术":
        return broad == "工业技术" or any(word in hay for word in ["PLC", "变频器", "ACS800", "工业机器人", "AutoCAD", "EPLAN", "电气维修", "控制柜"])
    return topic in hay


def normalize(row: dict) -> dict:
    broad = compact(row.get("broad_category", ""))
    title = compact(row.get("title", ""))
    source_name = compact(row.get("source_name", ""))
    url = compact(row.get("url", ""))
    school_identity_text = f"{title} {source_name} {url}"
    if broad == "我的学校" and not is_primary_school_text(school_identity_text):
        broad = infer_broad_from_text(school_identity_text)
    detected_at = compact(row.get("detected_at", ""))
    last_seen_at = compact(row.get("last_seen_at", "")) or detected_at
    status = compact(row.get("status", ""))
    is_new = "yes" if status in {"new", "initial_detected"} else "no"
    school_category = infer_school_category(f"{title} {source_name}") if broad == "我的学校" else ""
    return {
        "标题": title or "未命名监控更新",
        "摘要": compact(row.get("why_relevant", "")),
        "来源名称": source_name or "watch_only观察源",
        "订阅源URL": "watch://watch_only",
        "原文URL": url,
        "Folo文件夹路径": f"watch_updates/{broad or '长期观察'}",
        "发布时间": compact(row.get("published_at", "")) or visible_date_from_title(title),
        "input_source": "watch_updates",
        "source_type": "watch_update",
        "school_category": school_category,
        "detected_at": detected_at,
        "last_seen_at": last_seen_at,
        "is_new": is_new,
        "source_trace_id": compact(row.get("update_id", "")),
        "dedupe_key": compact(row.get("update_id", "")),
        "平台": "官网观察",
        "主分类": main_category(broad),
        "broad_category": broad,
        "source_layer": compact(row.get("source_layer", "")),
        "decision_scope": compact(row.get("decision_scope", "")),
        "是否需要核验": "是",
        "风险等级": compact(row.get("risk_level", "")) or "低",
        "为什么与你有关": compact(row.get("why_relevant", "")),
        "建议行动": compact(row.get("suggested_action", "")),
        "是否进入今日情报": "yes",
        "是否进入长期知识库": "pending",
        "备注": f"watch_id={compact(row.get('watch_id', ''))}; status={status}; school_category={school_category}" if school_category else f"watch_id={compact(row.get('watch_id', ''))}; status={status}",
    }


def load_watch_updates(topic: str = "", date_text: str = "", limit: int = 200) -> list[dict]:
    path = latest_update_path(date_text)
    raw_rows = read_jsonl(path) if path else []
    raw_rows.extend(read_snapshot_rows(limit=limit))
    rows = [normalize(row) for row in raw_rows]
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        if not matches_topic(row, topic):
            continue
        key = row.get("原文URL") or row.get("dedupe_key") or row.get("标题")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load watch updates as normalized InfoRadar input")
    parser.add_argument("--topic", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--output", default=str(NORMALIZED_DIR / "watch_updates_latest.csv"))
    args = parser.parse_args()
    rows = load_watch_updates(topic=args.topic, date_text=args.date)
    output = Path(args.output)
    write_csv(output, rows)
    result = {"success": True, "watch_update_count": len(rows), "return_csv": str(output), "output_files": [str(output)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
