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
COMMAND_LOG = ROOT / "logs" / "command.log"
FEEDBACK_LOG = ROOT / "memory" / "feedback_log.jsonl"
PREFERENCE_LOG = ROOT / "memory" / "preference_memory.jsonl"
WEIGHTS_FILE = ROOT / "config" / "interest_weights.yaml"


DEFAULT_WEIGHTS = {
    "vfd_repair": 98,
    "job_recruitment": 95,
    "local_policy": 92,
    "certificate": 90,
    "ai_automation": 88,
    "plc": 85,
    "industrial_robot": 78,
    "autocad": 72,
    "nas_automation": 70,
    "school_notice": 68,
    "3d_printing": 60,
    "general_news": 35,
    "vague_side_hustle": 5,
    "entertainment": 5,
}

DOMAIN_RULES = [
    ("vfd_repair", ["变频器", "ACS800", "ACS880", "ABB", "故障代码"]),
    ("job_recruitment", ["招聘", "就业", "岗位", "校招", "实习", "投递", "山西焦煤", "晋能控股"]),
    ("local_policy", ["政策", "山西", "人社", "政府", "补贴", "工信", "教育厅"]),
    ("certificate", ["证书", "电工证", "低压电工", "高压电工", "职业技能等级"]),
    ("ai_automation", ["AI", "ChatGPT", "Codex", "OpenAI", "Folo", "Follow", "RSS", "RSSHub"]),
    ("plc", ["PLC", "西门子", "三菱", "汇川", "梯形图"]),
    ("industrial_robot", ["工业机器人", "机器人", "ABB机器人", "发那科", "安川"]),
    ("autocad", ["AutoCAD", "CAD", "EPLAN", "电气图"]),
    ("nas_automation", ["NAS", "Tailscale", "RustDesk", "OpenClaw", "微信自动化"]),
    ("school_notice", ["学校", "山西机电", "教务", "毕业", "实习材料"]),
    ("3d_printing", ["3D打印", "建模", "创客"]),
    ("vague_side_hustle", ["副业", "赚钱", "接单", "月入", "风口"]),
]


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def latest_non_feedback_status() -> dict:
    latest = load_json(LATEST_STATUS)
    if latest and latest.get("command_type") != "记录反馈":
        return latest
    if not COMMAND_LOG.exists():
        return latest
    for line in reversed(COMMAND_LOG.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("command_type") != "记录反馈":
            return item
    return latest


def feedback_type(text: str) -> str:
    negative_words = ["没用", "少推", "不要再推", "忽略", "太虚", "营销味", "别推"]
    positive_words = ["有用", "多关注", "值得保存", "记住", "以后都这样", "方向深入"]
    if any(word in text for word in negative_words):
        return "negative"
    if any(word in text for word in positive_words):
        return "positive"
    return "neutral"


def learning_level(text: str) -> str:
    strong_words = ["记住", "以后都这样", "以后多关注", "以后少推", "不要再推", "忽略这类"]
    if any(word in text for word in strong_words):
        return "strong"
    if any(word in text for word in ["这个有用", "这个没用", "值得保存", "方向深入"]):
        return "medium"
    return "weak"


def load_weights() -> dict[str, int]:
    weights = dict(DEFAULT_WEIGHTS)
    if not WEIGHTS_FILE.exists():
        return weights
    for line in WEIGHTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*([^:#][^:]*)\s*:\s*(-?\d+)\s*$", line)
        if match:
            weights[match.group(1).strip()] = int(match.group(2))
    return weights


def clamp_weight(key: str, value: int) -> int:
    if key.startswith(("source__", "category__", "keyword__")):
        return max(-30, min(30, value))
    return max(0, min(100, value))


def safe_key_part(text: str) -> str:
    text = re.sub(r"\s+", "_", (text or "").strip())
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text)
    return text.strip("_")[:80] or "unknown"


def make_weight_key(kind: str, value: str) -> str:
    return f"{kind}__{safe_key_part(value)}"


def apply_weight_delta(weights: dict[str, int], key: str, delta: int) -> dict:
    old = int(weights.get(key, 0))
    new = clamp_weight(key, old + delta)
    weights[key] = new
    return {"domain": key, "old": old, "new": new, "delta": new - old}


def write_weights(weights: dict[str, int]) -> None:
    WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}: {clamp_weight(key, int(value))}" for key, value in weights.items()]
    WEIGHTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def infer_domains(feedback: str, target: dict) -> list[str]:
    target_details = target.get("details") if isinstance(target.get("details"), dict) else {}
    hay = " ".join(
        str(value)
        for value in [
            feedback,
            target.get("command", ""),
            target.get("keyword", ""),
            target.get("summary_file", ""),
            target_details.get("input", ""),
            target_details.get("xlsx", ""),
            target_details.get("fetch_summary", ""),
        ]
    )
    domains = []
    for domain, words in DOMAIN_RULES:
        if any(word.lower() in hay.lower() for word in words):
            domains.append(domain)
    if not domains:
        domains.append("general_news")
    return domains[:3]


def update_weights(weights: dict[str, int], domains: list[str], kind: str, level: str) -> list[dict]:
    if kind == "neutral":
        return []
    base_delta = {"strong": 5, "medium": 3, "weak": 1}.get(level, 1)
    delta = base_delta if kind == "positive" else -base_delta
    changes = []
    for domain in domains:
        old = int(weights.get(domain, DEFAULT_WEIGHTS.get(domain, 50)))
        new = max(0, min(100, old + delta))
        weights[domain] = new
        changes.append({"domain": domain, "old": old, "new": new, "delta": new - old})
    return changes


def parse_inline_xlsx(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        xml = z.read("xl/worksheets/sheet1.xml")
    root = ET.fromstring(xml)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    table = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        values = []
        for cell in row.findall("m:c", ns):
            text = ""
            inline = cell.find("m:is/m:t", ns)
            value = cell.find("m:v", ns)
            if inline is not None and inline.text is not None:
                text = inline.text
            elif value is not None and value.text is not None:
                text = value.text
            values.append(text)
        table.append(values)
    if not table:
        return []
    headers = table[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in table[1:]]


def latest_target_row(target: dict) -> dict:
    details = target.get("details") if isinstance(target.get("details"), dict) else {}
    row = {
        "标题": details.get("title", ""),
        "来源名称": details.get("source", ""),
        "主分类": details.get("category", ""),
        "标签": details.get("tags", ""),
    }
    xlsx = details.get("xlsx", "")
    if not xlsx:
        for value in [target.get("summary_file"), *(target.get("output_files") or [])]:
            if isinstance(value, str) and value.lower().endswith(".xlsx") and "FOLO_" in Path(value).name:
                xlsx = value
                break
    if xlsx and Path(xlsx).exists():
        try:
            rows = parse_inline_xlsx(Path(xlsx))
            if rows:
                first = rows[0]
                for key in ["标题", "来源名称", "主分类", "标签"]:
                    row[key] = first.get(key, row.get(key, ""))
        except Exception:
            pass
    return row


def explicit_keyword_feedback(feedback: str) -> tuple[str, int] | None:
    more = re.match(r"^以后多关注\s+(.+)$", feedback)
    less = re.match(r"^以后少推\s+(.+)$", feedback)
    if more:
        return more.group(1).strip(), 10
    if less:
        return less.group(1).strip(), -10
    return None


def update_granular_weights(weights: dict[str, int], feedback: str, kind: str, target: dict) -> list[dict]:
    changes: list[dict] = []
    explicit = explicit_keyword_feedback(feedback)
    if explicit:
        keyword, delta = explicit
        changes.append(apply_weight_delta(weights, make_weight_key("keyword", keyword), delta))
        return changes

    row = latest_target_row(target)
    source = row.get("来源名称", "")
    category = row.get("主分类", "")
    keyword = target.get("keyword", "")
    if kind == "positive" and "有用" in feedback:
        if source:
            changes.append(apply_weight_delta(weights, make_weight_key("source", source), 5))
        if category:
            changes.append(apply_weight_delta(weights, make_weight_key("category", category), 3))
        if keyword:
            changes.append(apply_weight_delta(weights, make_weight_key("keyword", keyword), 3))
    elif kind == "negative" and "没用" in feedback:
        if source:
            changes.append(apply_weight_delta(weights, make_weight_key("source", source), -5))
        if category:
            changes.append(apply_weight_delta(weights, make_weight_key("category", category), -2))
    return changes


def write_summary(path: Path, event: dict) -> None:
    changes = event.get("weight_changes") or []
    lines = [
        "【InfoRadar 反馈已记录】",
        "",
        f"反馈：{event['feedback']}",
        f"类型：{event['feedback_type']}",
        f"学习等级：{event['learning_level']}",
        "",
        f"关联任务：{event.get('target_command') or '-'}",
        f"关联任务ID：{event.get('target_task_id') or '-'}",
    ]
    if changes:
        lines.extend(["", "关注权重变化："])
        for change in changes:
            lines.append(f"- {change['domain']}：{change['old']} -> {change['new']}")
    else:
        lines.extend(["", "关注权重变化：未调整，仅记录反馈。"])
    lines.extend(
        [
            "",
            f"反馈日志：{FEEDBACK_LOG}",
            f"偏好记忆：{PREFERENCE_LOG}",
            f"权重文件：{WEIGHTS_FILE}",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar feedback collector")
    parser.add_argument("--feedback", default="", help="例如：这个有用 / 以后多关注 PLC")
    args = parser.parse_args()

    feedback = " ".join((args.feedback or "").strip().split())
    if not feedback:
        feedback = "未命名反馈"

    target = latest_non_feedback_status()
    kind = feedback_type(feedback)
    level = learning_level(feedback)
    domains = infer_domains(feedback, target)
    weights = load_weights()
    changes = update_weights(weights, domains, kind, level)
    changes.extend(update_granular_weights(weights, feedback, kind, target))
    write_weights(weights)

    event = {
        "time": now_text(),
        "feedback": feedback,
        "feedback_type": kind,
        "learning_level": level,
        "inferred_domains": domains,
        "weight_changes": changes,
        "target_task_id": target.get("task_id"),
        "target_command": target.get("command"),
        "target_keyword": target.get("keyword"),
        "target_summary_file": target.get("summary_file"),
    }
    append_jsonl(FEEDBACK_LOG, event)
    append_jsonl(PREFERENCE_LOG, event)

    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    summary = RETURN_DIR / f"feedback_{stamp()}_微信摘要.txt"
    write_summary(summary, event)

    result = {
        "success": True,
        "return_summary": str(summary),
        "output_files": [str(summary), str(FEEDBACK_LOG), str(PREFERENCE_LOG), str(WEIGHTS_FILE)],
        "feedback_type": kind,
        "learning_level": level,
        "weight_change_count": len(changes),
        "target_task_id": target.get("task_id"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
