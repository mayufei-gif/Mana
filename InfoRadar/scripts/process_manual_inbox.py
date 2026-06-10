#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import datetime as dt
import os
import json
import os
import re
import os
from pathlib import Path

from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
WECHAT_DIR = ROOT / "data" / "manual_inbox" / "wechat"
PROCESSED_DIR = ROOT / "data" / "manual_inbox" / "processed"
SUMMARY_TXT = RETURN_DIR / "manual_collected_items_微信摘要.txt"

HEADERS = [
    "序号",
    "source_trace_id",
    "dedupe_key",
    "标题",
    "平台",
    "链接",
    "来源名称",
    "内容类型",
    "主分类",
    "broad_category",
    "source_layer",
    "decision_scope",
    "是否一手信息",
    "是否需要核验",
    "价值等级",
    "风险等级",
    "为什么与你有关",
    "建议行动",
    "原始内容",
    "原始内容保存路径",
    "附件路径",
    "用户备注",
    "收集时间",
    "处理状态",
    "是否进入今日情报",
    "是否进入长期知识库",
    "备注",
]

RISK_TERMS = [
    "破解版",
    "学习版",
    "免激活",
    "注册机",
    "破解",
    "盗版",
    "刷单",
    "灰产",
    "培训贷",
    "低价API",
    "低价api",
    "代充",
    "薅羊毛",
    "绕过付费",
    "资源倒卖",
]


def today_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def strip_url(text: str) -> str:
    return re.sub(r"https?://[^\s<>\"]+", "", text or "", flags=re.I).strip()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


def has_any(text: str, terms: list[str]) -> bool:
    lower = (text or "").lower()
    return any(term.lower() in lower for term in terms)


def extract_title(row: dict) -> str:
    raw = compact(strip_url(row.get("raw_text", "")))
    platform = row.get("platform", "")
    if not raw:
        return row.get("url") or "未命名手动收集"
    if platform == "school_notice":
        for key in ["奖学金", "比赛", "竞赛", "入团", "评优", "通知", "教务", "学工", "团委"]:
            if key in raw:
                return raw[:60]
    if platform in {"taobao", "pinduoduo", "jd", "shopping"}:
        return raw[:60]
    if platform == "paid_resource":
        return raw[:60]
    return raw[:40]


def classify_wechat(raw: str) -> tuple[str, str, str, str, str, str, str]:
    if has_any(raw, ["政策", "补贴", "人社", "证书", "报名"]):
        return "政策线索", "政策风向", "B_observe", "环境判断", "B", "是", "作为线索，重要内容追溯官方来源。"
    if has_any(raw, ["学习", "教程", "课程", "技能", "PLC", "电工", "变频器"]):
        return "学习资源", "学习资源", "B_observe", "学习成长", "B", "是", "先保存为学习线索，后续结合来源质量判断是否深入。"
    if has_any(raw, ["风险", "骗局", "避坑", "培训贷", "虚假招聘"]):
        return "风险提醒", "风险避坑", "D_risk", "风险规避", "D", "是", "保留为风险样本，不建议直接行动。"
    return "内容线索", "热点新闻", "B_observe", "长期观察", "C", "是", "作为线索观察，重要信息需要追溯原始来源。"


def classify(row: dict) -> dict:
    raw = row.get("raw_text", "")
    platform = row.get("platform", "other")
    risk = has_any(raw, RISK_TERMS)
    if risk:
        return {
            "主分类": "风险提醒",
            "broad_category": "风险避坑",
            "source_layer": "D_risk",
            "decision_scope": "风险规避",
            "是否一手信息": "否",
            "是否需要核验": "是",
            "价值等级": "D",
            "风险等级": "高",
            "为什么与你有关": "这类内容可能涉及违规、诈骗、盗版或高风险操作，会影响你的判断和投入。",
            "建议行动": "不建议操作，保留为风险样本，避免投入或传播。",
            "是否进入今日情报": "risk_only",
            "是否进入长期知识库": "pending",
            "备注": "risk_policy=risk_only",
        }

    if platform == "school_notice":
        return {
            "主分类": "我的学校",
            "broad_category": "我的学校",
            "source_layer": "A_core",
            "decision_scope": "学校事务 / 机会提醒",
            "是否一手信息": "待核验",
            "是否需要核验": "是",
            "价值等级": "A",
            "风险等级": "低",
            "为什么与你有关": "学校通知可能影响奖学金、竞赛、入团、评优、就业或毕业事项，需要优先关注。",
            "建议行动": "优先核验学校官网、教务、学工、团委或官方公众号，确认截止时间和材料要求。",
            "是否进入今日情报": "yes",
            "是否进入长期知识库": "pending",
            "备注": "push_frequency=daily",
        }

    if platform in {"taobao", "pinduoduo", "jd", "shopping"}:
        return {
            "主分类": "购物资源",
            "broad_category": "购物资源",
            "source_layer": "E_supplement",
            "decision_scope": "消费决策",
            "是否一手信息": "否",
            "是否需要核验": "是",
            "价值等级": "C",
            "风险等级": "中",
            "为什么与你有关": "购物线索可能影响工具、耗材、学习设备或实习维修用品的购买决策。",
            "建议行动": "对比价格、评价、售后、品牌和替代方案，不要只看低价。",
            "是否进入今日情报": "no",
            "是否进入长期知识库": "no",
            "备注": "push_frequency=on_demand",
        }

    if platform == "paid_resource":
        return {
            "主分类": "付费知识",
            "broad_category": "付费知识",
            "source_layer": "C_opportunity",
            "decision_scope": "学习资源 / 消费决策",
            "是否一手信息": "否",
            "是否需要核验": "是",
            "价值等级": "B",
            "风险等级": "中",
            "为什么与你有关": "付费课程或资料可能影响学习效率和花费，需要判断是否适合当前阶段。",
            "建议行动": "只看公开目录、试看、评价和价格，不抓取付费正文，先判断是否匹配你的专业方向。",
            "是否进入今日情报": "pending",
            "是否进入长期知识库": "pending",
            "备注": "paywall_policy=metadata_only",
        }

    if platform in {"wechat_article", "zhihu", "bilibili", "douyin", "youtube"}:
        main, broad, layer, scope, value, verify, action = classify_wechat(raw)
        return {
            "主分类": main,
            "broad_category": broad,
            "source_layer": layer,
            "decision_scope": scope,
            "是否一手信息": "否",
            "是否需要核验": verify,
            "价值等级": value,
            "风险等级": "低",
            "为什么与你有关": "这类内容可作为信息线索，但需要结合来源可靠性和你的当前目标判断价值。",
            "建议行动": action,
            "是否进入今日情报": "pending",
            "是否进入长期知识库": "pending",
            "备注": "manual_forward_only",
        }

    return {
        "主分类": "待分类",
        "broad_category": "其他",
        "source_layer": "E_supplement",
        "decision_scope": "长期观察",
        "是否一手信息": "否",
        "是否需要核验": "是",
        "价值等级": "C",
        "风险等级": "低",
        "为什么与你有关": "这是手动收集的线索，需要后续处理后判断是否值得进入情报流。",
        "建议行动": "先保留，后续处理时再分类、核验和评分。",
        "是否进入今日情报": "pending",
        "是否进入长期知识库": "pending",
        "备注": "manual_collected",
    }


def content_type(row: dict) -> str:
    if row.get("url"):
        return "link"
    return "text"


def source_name(row: dict) -> str:
    platform = row.get("platform") or "other"
    hint = row.get("source_hint") or ""
    if hint:
        return f"手动收集-{hint}"
    return f"手动收集-{platform}"


def structured_row(idx: int, row: dict) -> dict:
    category = classify(row)
    out = {
        "序号": idx,
        "source_trace_id": row.get("source_trace_id", ""),
        "dedupe_key": row.get("dedupe_key", ""),
        "标题": extract_title(row),
        "平台": row.get("platform", ""),
        "链接": row.get("url", ""),
        "来源名称": source_name(row),
        "内容类型": content_type(row),
        "原始内容": row.get("raw_text", ""),
        "原始内容保存路径": row.get("raw_content_path", ""),
        "附件路径": row.get("attachment_path", ""),
        "用户备注": row.get("user_note", ""),
        "收集时间": row.get("collected_at", ""),
        "处理状态": "processed",
    }
    out.update(category)
    return out


def processed_path(date_text: str) -> Path:
    return PROCESSED_DIR / f"manual_processed_{date_text}.jsonl"


def inbox_path(date_text: str) -> Path:
    return WECHAT_DIR / f"manual_items_{date_text}.jsonl"


def load_processed_keys(rows: list[dict]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        key = row.get("dedupe_key") or row.get("source_trace_id")
        if key:
            keys.add(key)
    return keys


def write_markdown(path: Path, rows: list[dict], stats: dict) -> None:
    lines = [
        "# InfoRadar 手动收集箱处理结果",
        "",
        f"生成时间：{now_text()}",
        "",
        "## 总览",
        "",
        f"- 输入：{stats['input_count']} 条",
        f"- 新增处理：{stats['new_count']} 条",
        f"- 重复跳过：{stats['skipped_count']} 条",
        f"- 高风险：{stats['high_risk_count']} 条",
        f"- 学校类：{stats['school_count']} 条",
        f"- 购物类：{stats['shopping_count']} 条",
        f"- 付费资源：{stats['paid_resource_count']} 条",
        "",
        "## 前10条",
        "",
    ]
    for row in rows[:10]:
        lines.append(f"- {row.get('标题')} | {row.get('平台')} | {row.get('价值等级')} | 风险：{row.get('风险等级')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_summary(path: Path, rows: list[dict], stats: dict, xlsx_path: Path) -> None:
    lines = [
        "【InfoRadar 收集箱处理完成】",
        "",
        f"输入：{stats['input_count']} 条",
        f"新增处理：{stats['new_count']} 条",
        f"重复跳过：{stats['skipped_count']} 条",
        f"高风险：{stats['high_risk_count']} 条",
        f"学校类：{stats['school_count']} 条",
        f"购物类：{stats['shopping_count']} 条",
        f"付费资源：{stats['paid_resource_count']} 条",
        "",
        f"输出表格：{xlsx_path}",
        "",
        "前5条：",
    ]
    for idx, row in enumerate(rows[:5], 1):
        lines.append(f"{idx}. {row.get('标题')} [{row.get('平台')}]")
    lines.extend(["", "可继续发送：查看收集结果 / 全域情报"])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Process manual InfoRadar inbox into structured outputs")
    parser.add_argument("--date", default=today_stamp())
    args = parser.parse_args()

    WECHAT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RETURN_DIR.mkdir(parents=True, exist_ok=True)

    source_rows = read_jsonl(inbox_path(args.date))
    existing_rows = read_jsonl(processed_path(args.date))
    processed_keys = load_processed_keys(existing_rows)
    new_rows: list[dict] = []
    skipped_count = 0
    next_idx = len(existing_rows) + 1
    for row in source_rows:
        if row.get("status") != "new":
            continue
        key = row.get("dedupe_key") or row.get("source_trace_id")
        if key in processed_keys:
            skipped_count += 1
            continue
        item = structured_row(next_idx, row)
        new_rows.append(item)
        processed_keys.add(key)
        next_idx += 1

    append_jsonl(processed_path(args.date), new_rows)
    all_rows = read_jsonl(processed_path(args.date))
    for idx, row in enumerate(all_rows, 1):
        row["序号"] = idx

    xlsx_path = RETURN_DIR / f"manual_collected_items_{args.date}.xlsx"
    md_path = RETURN_DIR / f"manual_collected_items_{args.date}.md"
    csv_path = RETURN_DIR / f"manual_collected_items_{args.date}.csv"
    summary_path = RETURN_DIR / f"manual_collected_items_{args.date}_微信摘要.txt"

    write_xlsx(xlsx_path, HEADERS, all_rows, "manual_collected")
    write_csv(csv_path, HEADERS, all_rows)

    stats = {
        "input_count": len(source_rows),
        "new_count": len(new_rows),
        "skipped_count": skipped_count,
        "output_count": len(all_rows),
        "high_risk_count": sum(1 for row in all_rows if row.get("风险等级") == "高"),
        "school_count": sum(1 for row in all_rows if row.get("平台") == "school_notice"),
        "shopping_count": sum(1 for row in all_rows if row.get("平台") in {"taobao", "pinduoduo", "jd", "shopping"}),
        "paid_resource_count": sum(1 for row in all_rows if row.get("平台") == "paid_resource"),
    }
    write_markdown(md_path, all_rows, stats)
    write_summary(summary_path, all_rows, stats, xlsx_path)
    SUMMARY_TXT.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

    result = {
        "success": True,
        **stats,
        "processed_index": str(processed_path(args.date)),
        "return_xlsx": str(xlsx_path),
        "return_csv": str(csv_path),
        "return_summary": str(summary_path),
        "markdown": str(md_path),
        "output_files": [str(xlsx_path), str(md_path), str(summary_path), str(csv_path), str(SUMMARY_TXT), str(processed_path(args.date))],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
