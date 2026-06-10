#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import csv
import os
import datetime as dt
import os
import hashlib
import os
import json
import os
import re
import os
import subprocess
import os
import sys
import os
from pathlib import Path

import local_search
import os
import task_queue
import os
import web_discovery
import os
from xlsx_writer import write_xlsx


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))

HEADERS = [
    "序号",
    "标题",
    "来源集合",
    "来源类型",
    "主分类",
    "全域分类",
    "原文URL",
    "source_trace_id",
    "dedupe_key",
    "建议动作",
    "摘要片段",
]


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def trace_id(text: str) -> str:
    return "free_" + hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def parse_free_text(text: str) -> tuple[str, str]:
    raw = compact(text)
    for prefix, kind in [
        ("/ir ", "ir"),
        ("/find ", "find"),
        ("/watch ", "watch"),
        ("/collect ", "collect"),
        ("/deep ", "deep"),
    ]:
        if raw.lower().startswith(prefix):
            return kind, raw[len(prefix) :].strip()
    if raw in {"/ir", "/find"}:
        return "ir", ""
    return "ir", raw


def infer_intent(query: str) -> dict:
    hay = query.lower()
    domain = "全域情报"
    if any(word in query for word in ["山西晋中理工", "晋中理工", "学校", "奖学金", "教务", "学工", "团委", "入团"]):
        domain = "我的学校"
    elif any(word in query for word in ["电工证", "低压电工", "高压电工", "证书", "补贴", "报名"]):
        domain = "职业证书"
    elif any(word in query for word in ["招聘", "校招", "岗位", "山西焦煤", "晋能控股"]):
        domain = "就业招聘"
    elif any(word in query for word in ["课程", "付费", "值得买", "网课", "专栏"]):
        domain = "付费资源"
    elif any(word in query for word in ["PLC", "变频器", "电气", "ACS800", "维修"]):
        domain = "专业成长"
    elif any(word in query for word in ["AI", "OpenAI", "Codex", "Folo", "RSSHub", "自动化"]) or "ai" in hay:
        domain = "AI与科技"
    return {
        "intent": "search_information",
        "topic": query,
        "domain": domain,
        "search_scope": ["local", "folo_rss", "manual_inbox", "watch_only", "public_discovery"],
        "output": "wechat_summary",
        "parser": "rule_based",
    }


def parse_json_output(stdout: str) -> dict:
    stdout = (stdout or "").strip()
    if not stdout:
        return {}
    start = stdout.find("{")
    if start < 0:
        return {"stdout": stdout}
    try:
        return json.loads(stdout[start:])
    except Exception:
        return {"stdout": stdout}


def run_script(script: str, args: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result = parse_json_output(proc.stdout)
    result["returncode"] = proc.returncode
    if proc.stderr.strip():
        result["stderr"] = proc.stderr.strip()
    return result


def handle_collect(query: str, task_id: str) -> dict:
    result = run_script("collect_manual_item.py", ["--text", query, "--from-channel", "wechat"])
    return {
        "success": result.get("returncode") == 0 and bool(result.get("success", True)),
        "mode": "collect",
        "query": query,
        "local_match_count": 0,
        "public_search_count": 0,
        "candidate_source_count": 0,
        "output_files": result.get("output_files", []),
        "return_summary": result.get("return_summary", ""),
        "collect_result": result,
    }


def handle_deep(query: str, task_id: str) -> dict:
    result = run_script("deep_dive_item.py", ["--selector", query])
    return {
        "success": result.get("returncode") == 0 and bool(result.get("success", True)),
        "mode": "deep",
        "query": query,
        "local_match_count": 0,
        "public_search_count": 0,
        "candidate_source_count": 0,
        "output_files": result.get("output_files", []),
        "return_summary": result.get("return_summary", ""),
        "deep_result": result,
    }


def handle_watch(query: str, task_id: str) -> dict:
    path = ROOT / "sources" / "watch_only_requests.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "关键词", "状态", "创建时间", "备注"])
        if not exists:
            writer.writeheader()
        writer.writerow({"task_id": task_id, "关键词": query, "状态": "new", "创建时间": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "备注": "free_command_watch"})
    summary = RETURN_DIR / f"free_command_watch_{stamp()}_微信摘要.txt"
    summary.write_text(f"【InfoRadar 加入监控】\n\n关键词：{query}\n状态：new\n文件：{path}", encoding="utf-8")
    return {
        "success": True,
        "mode": "watch",
        "query": query,
        "local_match_count": 0,
        "public_search_count": 0,
        "candidate_source_count": 0,
        "return_csv": str(path),
        "return_summary": str(summary),
        "output_files": [str(path), str(summary)],
    }


def action_for(row: dict) -> str:
    collection = row.get("来源集合", "")
    if collection == "manual_collected_items":
        return "可发送：处理收集箱 / 全域情报 / 深挖第N条"
    if collection == "source_pool":
        return "可发送：导入Folo / 治理RSS源 / 加入监控"
    if collection == "folo_report_table":
        return "可发送：深挖第N条 / 这个有用 / 这个没用"
    return "可保存观察，重要信息继续核验原始来源"


def write_free_outputs(task_id: str, query: str, intent: dict, local_rows: list[dict], discovery: dict, external_skipped: bool) -> dict:
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    task_stamp = stamp()
    csv_path = RETURN_DIR / f"free_command_results_{task_stamp}.csv"
    xlsx_path = RETURN_DIR / f"free_command_results_{task_stamp}.xlsx"
    md_path = RETURN_DIR / f"free_command_report_{task_stamp}.md"
    summary_path = RETURN_DIR / f"free_command_{task_stamp}_微信摘要.txt"
    rows: list[dict] = []
    for source in local_rows[:20]:
        rows.append(
            {
                "序号": len(rows) + 1,
                "标题": source.get("标题", ""),
                "来源集合": source.get("来源集合", ""),
                "来源类型": source.get("来源类型", ""),
                "主分类": source.get("主分类", ""),
                "全域分类": source.get("全域分类", ""),
                "原文URL": source.get("原文URL", ""),
                "source_trace_id": source.get("source_trace_id", ""),
                "dedupe_key": source.get("dedupe_key", ""),
                "建议动作": action_for(source),
                "摘要片段": source.get("摘要片段", ""),
            }
        )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    write_xlsx(xlsx_path, HEADERS, rows, "free_command")

    public_count = int(discovery.get("public_search_count", 0) or 0)
    candidate_count = int(discovery.get("candidate_source_count", 0) or 0)
    lines = [
        "# InfoRadar 自由指令报告",
        "",
        f"任务ID：{task_id}",
        f"指令：{query}",
        "",
        "## 意图",
        "",
        f"- intent：{intent.get('intent')}",
        f"- domain：{intent.get('domain')}",
        f"- parser：{intent.get('parser')}",
        "",
        "## 检索结果",
        "",
        f"- 本地检索：{len(local_rows)} 条",
        f"- 公开搜索/候选源发现：{public_count} 条",
        f"- 候选源：{candidate_count} 个",
        f"- 是否跳过外部搜索：{external_skipped}",
        "",
        "## 前10条",
        "",
    ]
    for row in rows[:10]:
        lines.append(f"- {row.get('序号')}. {row.get('标题')} | {row.get('来源集合')} | {row.get('建议动作')}")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    summary = [
        "【InfoRadar 自由指令】",
        "",
        f"指令：{query}",
        f"意图：{intent.get('domain')}",
        f"本地检索：找到 {len(local_rows)} 条",
        f"Folo/RSS：找到 {sum(1 for row in local_rows if row.get('来源集合') == 'folo_report_table')} 条",
        f"手动收集：找到 {sum(1 for row in local_rows if row.get('来源集合') == 'manual_collected_items' or row.get('来源类型') == 'manual_collected')} 条",
        f"公开搜索：找到 {public_count} 条",
        f"候选源：{candidate_count} 个",
        "",
        "结论：",
    ]
    if local_rows:
        summary.append("本地已有相关信息，已优先返回；如仍不够，可继续发：深挖第1条 / 查源 关键词 / 加入监控。")
    elif candidate_count:
        summary.append("本地资料不足，已进入候选源发现；请查看候选源和 watch_only 清单。")
    else:
        summary.append("暂未找到足够结果，建议缩小关键词或添加来源线索。")
    summary.extend(["", "前5条："])
    if rows:
        for row in rows[:5]:
            summary.append(f"{row.get('序号')}. {row.get('标题')}")
            summary.append(f"   来源：{row.get('来源集合')} / {row.get('主分类') or row.get('全域分类') or '-'}")
    else:
        summary.append("- 暂无本地结果")
    summary.extend(["", "下一步：导入Folo / 深挖第1条 / 加入监控 / 收集到知识库"])
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    output_files = [str(csv_path), str(xlsx_path), str(md_path), str(summary_path)]
    output_files.extend(discovery.get("output_files", []))
    return {
        "return_csv": str(csv_path),
        "return_xlsx": str(xlsx_path),
        "report": str(md_path),
        "return_summary": str(summary_path),
        "output_files": output_files,
    }


def handle_search(query: str, task_id: str) -> dict:
    intent = infer_intent(query)
    local_rows = local_search.search_local(query, limit=30)
    enough_local = len(local_rows) >= 3 or any(int(row.get("匹配分数", 0)) >= 24 for row in local_rows)
    discovery: dict = {"success": True, "public_search_count": 0, "candidate_source_count": 0, "output_files": []}
    if not enough_local:
        discovery = web_discovery.run_public_discovery(query)
    outputs = write_free_outputs(task_id, query, intent, local_rows, discovery, enough_local)
    task_queue.record_task(
        {
            "task_id": task_id,
            "command_type": "free_command",
            "query": query,
            "intent": intent,
            "local_match_count": len(local_rows),
            "external_search_skipped": enough_local,
            "candidate_source_count": discovery.get("candidate_source_count", 0),
            "output_files": outputs.get("output_files", []),
        }
    )
    return {
        "success": True,
        "mode": "search",
        "task_id": task_id,
        "query": query,
        "intent": intent,
        "local_match_count": len(local_rows),
        "folo_rss_match_count": sum(1 for row in local_rows if row.get("来源集合") == "folo_report_table"),
        "manual_match_count": sum(1 for row in local_rows if row.get("来源集合") == "manual_collected_items" or row.get("来源类型") == "manual_collected"),
        "public_search_count": discovery.get("public_search_count", 0),
        "candidate_source_count": discovery.get("candidate_source_count", 0),
        "import_ready_count": discovery.get("import_ready_count", 0),
        "watch_only_count": discovery.get("watch_only_count", 0),
        "external_search_skipped": enough_local,
        **outputs,
    }


def route(text: str) -> dict:
    task_id = f"free_{stamp()}"
    kind, query = parse_free_text(text)
    if not query:
        query = "今日情报"
    if kind == "collect":
        result = handle_collect(query, task_id)
    elif kind == "deep":
        result = handle_deep(query, task_id)
    elif kind == "watch":
        result = handle_watch(query, task_id)
    else:
        result = handle_search(query, task_id)
    result.setdefault("task_id", task_id)
    result.setdefault("source_trace_id", trace_id(text))
    task_queue.record_task({"task_id": task_id, "command_type": "free_command_done", "raw_text": text, "result": result})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar free command router")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    result = route(args.text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
