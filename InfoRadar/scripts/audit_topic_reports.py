#!/usr/bin/env python3
import csv
import os
import datetime as dt
import os
import json
import os
import re
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
DEDUPED_DIR = ROOT / "data" / "deduped"
LOG_DIR = ROOT / "logs"
SOURCE_POOL = ROOT / "sources" / "source_pool_from_folo.csv"
SOURCE_STRATEGY = ROOT / "sources" / "source_pool_strategy.csv"

TOPICS = ["AI", "政策", "招聘", "技术", "证书", "今日情报"]

TECH_CATEGORIES = {"PLC自动化", "变频器维修", "工业机器人", "AutoCAD/EPLAN", "电气维修"}
POLICY_CATEGORIES = {"国家政策", "地方政策", "学校通知", "职业证书", "技能补贴"}
AI_CATEGORIES = {"AI工具", "NAS与远程控制"}


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_topic(topic: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", topic).strip("_") or "unknown"


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def latest_csv_for_topic(topic: str) -> Path | None:
    pattern = f"FOLO_{safe_topic(topic)}_*.csv"
    files = [path for path in DEDUPED_DIR.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def latest_xlsx_for_topic(topic: str) -> Path | None:
    pattern = f"FOLO_{safe_topic(topic)}_*.xlsx"
    files = [path for path in RETURN_DIR.glob(pattern) if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def row_text(row: dict) -> str:
    return " ".join(str(row.get(key, "")) for key in ["标题", "主分类", "标签", "来源名称", "Folo文件夹路径", "备注", "建议行动"])


def has_any(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def obvious_misclassified(topic: str, row: dict) -> bool:
    category = row.get("主分类", "")
    hay = row_text(row)
    if topic == "AI":
        return category in {"国家政策", "地方政策", "学校通知", "就业招聘"}
    if topic == "政策":
        return category in AI_CATEGORIES or category == "就业招聘"
    if topic == "招聘":
        return category in AI_CATEGORIES or category in TECH_CATEGORIES or category in {"国家政策", "地方政策", "职业证书", "技能补贴"}
    if topic == "技术":
        return category not in TECH_CATEGORIES and not has_any(hay, ["PLC", "变频器", "ACS800", "ACS880", "电气", "机器人", "CAD", "EPLAN", "维修", "控制柜"])
    if topic == "证书":
        return category not in {"职业证书", "技能补贴"} and not has_any(hay, ["证书", "电工证", "技能等级", "职业技能", "补贴", "考试", "报名"])
    return False


def high_risk(row: dict) -> bool:
    hay = row_text(row)
    return row.get("风险等级") == "高" or has_any(hay, ["破解版", "学习版", "注册机", "免激活", "高风险", "盗版"])


def audit_topic(topic: str) -> dict:
    csv_path = latest_csv_for_topic(topic)
    xlsx_path = latest_xlsx_for_topic(topic)
    if not csv_path:
        return {
            "topic": topic,
            "status": "missing",
            "csv": "",
            "xlsx": str(xlsx_path) if xlsx_path else "",
            "row_count": 0,
        }
    rows = read_csv(csv_path)
    top30 = rows[:30]
    top10 = rows[:10]
    duplicate_titles = sum(1 for group in _duplicates(top30, "标题") if group)
    url_anomaly = sum(1 for row in top30 if row.get("URL异常") == "是" or not row.get("原文URL", "").strip())
    high_risk_top10 = sum(1 for row in top10 if high_risk(row))
    misclassified = sum(1 for row in top30 if obvious_misclassified(topic, row))
    empty_action = sum(1 for row in top30 if not row.get("建议行动", "").strip())
    empty_folder = sum(1 for row in top30 if not row.get("Folo文件夹路径", "").strip())
    empty_url = sum(1 for row in top30 if not row.get("原文URL", "").strip())
    not_worth_top10 = sum(
        1
        for row in top10
        if high_risk(row) or row.get("URL异常") == "是" or not row.get("建议行动", "").strip() or not row.get("原文URL", "").strip()
    )
    return {
        "topic": topic,
        "status": "ok",
        "csv": str(csv_path),
        "xlsx": str(xlsx_path) if xlsx_path else "",
        "row_count": len(rows),
        "duplicate_titles_top30": duplicate_titles,
        "url_anomaly_top30": url_anomaly,
        "high_risk_top10": high_risk_top10,
        "misclassified_top30": misclassified,
        "empty_action_top30": empty_action,
        "empty_folder_top30": empty_folder,
        "empty_url_top30": empty_url,
        "not_worth_wechat_top10": not_worth_top10,
    }


def _duplicates(rows: list[dict], key: str) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        value = (row.get(key) or "").strip().lower()
        if not value:
            continue
        grouped.setdefault(value, []).append(row)
    return [items for items in grouped.values() if len(items) > 1]


def load_latest_command_details() -> dict[str, dict]:
    path = LOG_DIR / "command.log"
    latest: dict[str, dict] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("command_type") != "生成Folo表格":
            continue
        keyword = item.get("keyword") or ""
        if keyword in ("今日",):
            keyword = "今日情报"
        if keyword in TOPICS:
            latest[keyword] = item.get("details") or {}
    return latest


def theme_for_source(source: dict, strategy: dict) -> str:
    hay = " ".join(str(source.get(key, "")) for key in ["源名称", "主分类", "标签", "Folo文件夹路径", "备注"])
    category = source.get("主分类", "")
    strategy_name = strategy.get("抓取策略", "")
    if strategy_name == "disabled" or has_any(hay, ["低价值", "私密", "泄密", "网盘影视", "影视站", "侵权"]):
        return "风险观察源池"
    if category == "新闻时政" or has_any(hay, ["新闻时政", "政策", "人社", "教育厅", "工信", "证书", "补贴", "学校通知"]):
        return "政策证书源池"
    if has_any(hay, ["招聘", "就业", "岗位", "校招", "实习", "山西焦煤", "霍州煤电", "晋能控股"]):
        return "招聘就业源池"
    if category == "技术学习" or has_any(hay, ["技术学习", "PLC", "变频器", "电气", "CAD", "机器人", "建模", "Python", "电路"]):
        return "技术学习源池"
    if category == "AI工具" or has_any(hay, ["AI", "科技开源", "OpenAI", "Codex", "RSSHub", "Folo", "GitHub"]):
        return "AI工具源池"
    return "风险观察源池"


def build_source_theme_report() -> tuple[Path, dict[str, dict]]:
    source_rows = read_csv(SOURCE_POOL) if SOURCE_POOL.exists() else []
    strategy_rows = read_csv(SOURCE_STRATEGY) if SOURCE_STRATEGY.exists() else []
    source_by_name = {row.get("源名称", ""): row for row in source_rows}
    stats: dict[str, dict] = {}
    for strategy in strategy_rows:
        source = source_by_name.get(strategy.get("源名称", ""), {})
        theme = theme_for_source(source, strategy)
        item = stats.setdefault(
            theme,
            {
                "总源数": 0,
                "成功源数": 0,
                "失败源数": 0,
                "403数量": 0,
                "建议替换数量": 0,
                "建议废弃数量": 0,
                "cache_only数量": 0,
                "rsshub策略数量": 0,
                "direct_rss数量": 0,
                "official_page数量": 0,
            },
        )
        item["总源数"] += 1
        status = strategy.get("当前状态", "")
        strategy_name = strategy.get("抓取策略", "")
        note = strategy.get("备注", "")
        action = strategy.get("建议动作", "")
        if status == "success":
            item["成功源数"] += 1
        else:
            item["失败源数"] += 1
        if "403" in note:
            item["403数量"] += 1
        if "替换" in action:
            item["建议替换数量"] += 1
        if "废弃" in action or strategy_name == "disabled":
            item["建议废弃数量"] += 1
        if strategy_name == "cache_only":
            item["cache_only数量"] += 1
        if strategy_name.startswith("rsshub_"):
            item["rsshub策略数量"] += 1
        if strategy_name == "direct_rss":
            item["direct_rss数量"] += 1
        if strategy_name == "official_page":
            item["official_page数量"] += 1

    path = RETURN_DIR / f"主题源池治理报告_{today_stamp()}.md"
    lines = [
        "# 主题源池治理报告",
        "",
        f"生成时间：{now_text()}",
        f"策略表：{SOURCE_STRATEGY}",
        "",
    ]
    for theme in ["AI工具源池", "政策证书源池", "招聘就业源池", "技术学习源池", "风险观察源池"]:
        item = stats.get(theme, {})
        lines.extend(
            [
                f"## {theme}",
                "",
                "| 指标 | 数量 |",
                "|---|---:|",
            ]
        )
        for key in ["总源数", "成功源数", "失败源数", "403数量", "建议替换数量", "建议废弃数量", "cache_only数量", "rsshub策略数量", "direct_rss数量", "official_page数量"]:
            lines.append(f"| {key} | {item.get(key, 0)} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path, stats


def write_audit_report(path: Path, audits: list[dict], command_details: dict[str, dict], source_report: Path) -> None:
    lines = [
        "# InfoRadar MVP-2.5 多主题质量抽检",
        "",
        f"生成时间：{now_text()}",
        f"主题源池治理报告：{source_report}",
        "",
        "## 总览",
        "",
        "| 主题 | 行数 | 前30重复 | 前30URL异常 | 前10高风险 | 前30明显错分 | 前10不建议推送 | 缓存兜底 | 抓取成功率 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for audit in audits:
        topic = audit["topic"]
        details = command_details.get(topic, {})
        lines.append(
            "| {topic} | {row_count} | {dup} | {url} | {risk} | {mis} | {bad} | {cache} | {ratio} |".format(
                topic=topic,
                row_count=audit.get("row_count", 0),
                dup=audit.get("duplicate_titles_top30", "-"),
                url=audit.get("url_anomaly_top30", "-"),
                risk=audit.get("high_risk_top10", "-"),
                mis=audit.get("misclassified_top30", "-"),
                bad=audit.get("not_worth_wechat_top10", "-"),
                cache=details.get("cache_fallback_used", "-"),
                ratio=details.get("fetch_success_ratio", "-"),
            )
        )

    lines.extend(["", "## 主题文件", "", "| 主题 | Excel | CSV |", "|---|---|---|"])
    for audit in audits:
        lines.append(f"| {audit['topic']} | {audit.get('xlsx', '')} | {audit.get('csv', '')} |")

    lines.extend(["", "## 主题缺口", ""])
    for audit in audits:
        if audit.get("row_count", 0) > 0:
            continue
        topic = audit["topic"]
        if topic == "招聘":
            lines.append("- 今日招聘当前没有有效条目：需要补充山西焦煤、霍州煤电、晋能控股、太重、潞安、人社招聘平台、学校就业网等源。")
        elif topic == "技术":
            lines.append("- 今日技术当前没有命中 PLC/变频器/电气维修/工业机器人等条目：现有技术源偏通用学习，需要补充工业自动化/电气维修专门源。")
        elif topic == "证书":
            lines.append("- 今日证书当前没有有效条目：需要补充低压电工证、高压电工证、职业技能等级、计算机等级、CAD证书、技能补贴报名等官方/培训通知源。")
        else:
            lines.append(f"- {topic} 当前没有有效条目：需要补充该主题源池。")

    lines.extend(
        [
            "",
            "## 判断",
            "",
            "- 标题重复、URL异常、高风险前10、明显错分是本轮质量红线。",
            "- 如果某主题行数很少，优先补源池，不应靠放宽分类硬凑数量。",
            "- 今日情报需要继续保持主题配额，不允许单一主题霸榜。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    audits = [audit_topic(topic) for topic in TOPICS]
    command_details = load_latest_command_details()
    source_report, source_stats = build_source_theme_report()
    audit_report = RETURN_DIR / f"InfoRadar_MVP2_5_多主题质量抽检_{today_stamp()}.md"
    write_audit_report(audit_report, audits, command_details, source_report)
    result = {
        "success": True,
        "audit_report": str(audit_report),
        "source_theme_report": str(source_report),
        "topics": audits,
        "source_theme_stats": source_stats,
        "output_files": [str(audit_report), str(source_report)],
    }
    append_jsonl(LOG_DIR / "run.log", {"task": "audit_topic_reports", **result})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
