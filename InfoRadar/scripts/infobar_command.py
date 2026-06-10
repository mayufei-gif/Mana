#!/usr/bin/env python3
import argparse
import os
import datetime as dt
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


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
COMMAND_MAP = ROOT / "config" / "command_map.yaml"
LATEST_STATUS = ROOT / "logs" / "latest_status.json"
RETURN_LATEST_STATUS = RETURN_DIR / "latest_status.json"
FIXED_SUMMARY = RETURN_DIR / "latest_status_微信摘要.txt"


ALIASES = {
    "今日情报": "生成Folo表格 今日情报",
    "今日技术": "生成Folo表格 技术",
    "今日政策": "生成Folo表格 政策",
    "今日招聘": "生成Folo表格 招聘",
    "今日证书": "生成Folo表格 证书",
    "今日AI": "生成Folo表格 AI",
    "我的学校": "生成Folo表格 我的学校",
    "学校通知": "生成Folo表格 学校通知",
    "本地山西": "生成Folo表格 本地山西",
    "时事热点": "生成Folo表格 时事热点",
    "国际观察": "生成Folo表格 国际观察",
    "科技前沿": "生成Folo表格 科技前沿",
    "开源动态": "生成Folo表格 开源动态",
    "网络安全": "生成Folo表格 网络安全",
    "购物情报": "生成Folo表格 购物情报",
    "数码装备": "生成Folo表格 数码装备",
    "工具软件": "生成Folo表格 工具软件",
    "付费资源": "生成Folo表格 付费资源",
    "法律权益": "生成Folo表格 法律权益",
    "健康医学": "生成Folo表格 健康医学",
    "财经商业": "生成Folo表格 财经商业",
    "学习资源": "生成Folo表格 学习资源",
    "3D打印硬件": "生成Folo表格 3D打印硬件",
    "生活服务": "生成Folo表格 生活服务",
    "文化历史": "生成Folo表格 文化历史",
    "读书影视": "生成Folo表格 读书影视",
    "游戏娱乐": "生成Folo表格 游戏娱乐",
    "体育赛事": "生成Folo表格 体育赛事",
    "风险提醒": "生成Folo表格 风险提醒",
    "风险避坑": "生成Folo表格 风险避坑",
    "虚假招聘": "生成Folo表格 虚假招聘",
    "培训贷": "生成Folo表格 培训贷",
    "账号隐私": "生成Folo表格 账号隐私",
    "全域情报": "生成Folo表格 全域情报",
    "扩展全域源池": "扩展全域源池",
    "核验全域源池": "核验全域源池",
    "生成Folo导入清单": "核验全域源池",
    "查看全域源报告": "查看最新结果",
    "最新结果": "查看最新结果",
    "做源池": "生成源池",
    "导入Folo": "导入Folo订阅",
    "导入Folo订阅": "导入Folo订阅",
    "导入真实Folo": "导入Folo订阅",
    "真实Folo源池": "导入Folo订阅",
    "同步Folo全域源": "导入Folo订阅",
    "Folo导入验收": "Folo导入验收",
    "全域源导入验收": "Folo导入验收",
    "全域情报验收": "全域情报验收",
    "查看收集箱": "查看收集箱",
    "处理收集箱": "处理收集箱",
    "查看收集结果": "查看收集结果",
    "执行监控": "执行监控",
    "查看监控": "查看监控",
    "查看监控更新": "查看监控更新",
    "监控报告": "监控报告",
    "抓取Folo": "抓取Folo更新",
    "抓取Folo更新": "抓取Folo更新",
    "刷新Folo": "抓取Folo更新",
    "刷新Folo内容": "抓取Folo更新",
    "治理RSS源": "治理RSS源",
    "检查RSSHub": "检查RSSHub",
    "修复URL异常": "修复URL异常",
}

FEEDBACK_EXACT_COMMANDS = {
    "这个有用",
    "这个没用",
    "这个值得保存",
    "以后多关注这个",
    "以后少推这个",
    "忽略这类内容",
    "记住这个",
    "以后都这样",
    "这个方向深入",
    "太虚了",
    "营销味太重",
}

FEEDBACK_PREFIX_COMMANDS = (
    "记录反馈",
    "以后多关注",
    "以后少推",
    "不要再推",
    "忽略",
    "记住",
)


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_compact() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def ensure_dirs() -> None:
    for path in [
        RETURN_DIR,
        ROOT / "logs",
        ROOT / "memory" / "task_history",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def write_latest(data: dict) -> None:
    LATEST_STATUS.parent.mkdir(parents=True, exist_ok=True)
    LATEST_STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    RETURN_LATEST_STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_command(text: str) -> str:
    command = " ".join((text or "").strip().split())
    for prefix in ["/ir", "/find", "/watch", "/collect", "/deep"]:
        if command == prefix or command.startswith(prefix + " "):
            return "自由指令 " + command
    if command.startswith("/inforadar "):
        command = command[len("/inforadar ") :].strip()
    if command == "/inforadar":
        return "查看最新结果"
    deep_match = re.match(r"^深挖\s*(第?\d+条?|#[0-9]+|[0-9]+|[\s\S]+)$", command)
    if deep_match:
        return "深挖条目 " + deep_match.group(1).strip()
    if command in FEEDBACK_EXACT_COMMANDS or command.startswith(FEEDBACK_PREFIX_COMMANDS):
        if command.startswith("记录反馈 "):
            return command
        return "记录反馈 " + command
    if command.startswith("查源 "):
        return "推荐订阅源 " + command[len("查源 ") :].strip()
    if command.startswith("深探源 "):
        return "深度探测订阅源 " + command[len("深探源 ") :].strip()
    if command.startswith("收集 "):
        return command
    return ALIASES.get(command, command)


def load_command_names() -> list[str]:
    if not COMMAND_MAP.exists():
        return []
    names: list[str] = []
    in_commands = False
    for line in COMMAND_MAP.read_text(encoding="utf-8").splitlines():
        if re.match(r"^commands:\s*$", line):
            in_commands = True
            continue
        if not in_commands:
            continue
        match = re.match(r"^\s{2}([^:\s][^:]*):\s*$", line)
        if match:
            names.append(match.group(1).strip())
    return names


def parse_command(text: str) -> tuple[str, str]:
    command = " ".join((text or "").strip().split())
    if not command:
        raise ValueError("命令不能为空")

    known = sorted(load_command_names(), key=len, reverse=True)
    for name in known:
        if command == name:
            return name, ""
        if command.startswith(name + " "):
            return name, command[len(name) :].strip()

    # 兜底支持，避免 command_map 缺项时完全不可用。
    for name in ["自由指令", "推荐订阅源", "深度探测订阅源", "深挖条目", "生成源池", "生成Folo表格", "查看最新结果", "导入Folo订阅", "Folo导入验收", "全域情报验收", "收集", "查看收集箱", "处理收集箱", "查看收集结果", "执行监控", "查看监控", "查看监控更新", "监控报告", "抓取Folo更新", "记录反馈", "治理RSS源", "检查RSSHub", "修复URL异常", "扩展全域源池", "核验全域源池"]:
        if command == name:
            return name, ""
        if command.startswith(name + " "):
            return name, command[len(name) :].strip()
    raise ValueError(f"无法识别命令：{command}")


def run_python(script: Path, args: list[str]) -> dict:
    cmd = [sys.executable, str(script), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    parsed: dict = {}
    stdout = proc.stdout.strip()
    if stdout:
        try:
            parsed = json.loads(stdout[stdout.find("{") :])
        except Exception:
            parsed = {"stdout": stdout}
    parsed["returncode"] = proc.returncode
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    parsed["cmd"] = cmd
    return parsed


def result_files(result: dict) -> list[str]:
    keys = [
        "return_xlsx",
        "return_summary",
        "return_csv",
        "return_opml",
        "xlsx",
        "markdown",
        "wechat_summary",
        "opml",
        "watchlist_xlsx",
        "watchlist_summary",
        "return_watchlist_xlsx",
        "return_watchlist_summary",
        "strategy_csv",
        "strategy_xlsx",
        "governance_report",
        "report",
        "profile_csv",
        "profile_xlsx",
        "candidate_csv",
        "candidate_xlsx",
    ]
    files: list[str] = []
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value and value not in files:
            files.append(value)
    for value in result.get("output_files", []) if isinstance(result.get("output_files"), list) else []:
        if value and value not in files:
            files.append(str(value))
    return files


def important_files(files: list[str], limit: int = 6) -> tuple[list[str], int]:
    preferred: list[str] = []
    secondary: list[str] = []
    for file in files:
        value = str(file)
        if value in preferred or value in secondary:
            continue
        if r"NAS回传\FOLO" in value:
            preferred.append(value)
        else:
            secondary.append(value)
    ordered = preferred + secondary
    return ordered[:limit], max(0, len(ordered) - limit)


def metric_lines(details: dict) -> list[str]:
    if not isinstance(details, dict):
        return []
    labels = {
        "new_candidates": "新增候选源",
        "total_candidates": "候选源总数",
        "addable_candidates": "可直接添加",
        "watchlist_candidates": "需监控候选",
        "item_count": "条目数",
        "total_items": "条目总数",
        "matched_items": "命中条目",
        "input_count": "输入条数",
        "auto_input_count": "自动源条数",
        "manual_input_count": "手动收集条数",
        "output_count": "输出条数",
        "manual_output_count": "进入表格手动条数",
        "manual_enter_today_count": "进入今日情报的手动条数",
        "manual_risk_count": "手动风险提醒条数",
        "manual_school_count": "手动学校信息条数",
        "duplicate_count": "合并重复标题",
        "topic_filtered_count": "主题过滤条目",
        "preference_weight_used": "使用反馈权重",
        "preference_adjusted_count": "反馈权重影响条目",
        "fetch_source_count": "抓取源数",
        "fetch_success_source_count": "抓取成功源数",
        "fetch_failed_source_count": "抓取失败源数",
        "fetch_success_ratio": "抓取成功率",
        "fetch_item_count": "抓取条目数",
        "cache_fallback_used": "启用缓存兜底",
        "cache_fallback_candidate_count": "缓存候选条目",
        "cache_fallback_added_count": "缓存合并新增",
        "url_anomaly_count": "URL异常条目",
        "local_match_count": "本地命中",
        "folo_rss_match_count": "Folo/RSS命中",
        "manual_match_count": "手动收集命中",
        "public_search_count": "公开搜索/候选发现",
        "candidate_source_count": "候选源",
        "external_search_skipped": "已跳过外部搜索",
        "source_count": "源总数",
        "success_count": "成功数",
        "failed_count": "失败数",
        "direct_rss_success_count": "直接RSS成功",
        "rsshub_primary_success_count": "RSSHub主实例成功",
        "rsshub_backup_success_count": "RSSHub备用实例成功",
        "forbidden_count": "403数量",
        "replace_needed_count": "建议替换数量",
        "disabled_count": "建议废弃数量",
        "instance_count": "RSSHub实例数",
        "available_count": "可连接实例数",
        "profile_count": "现有源画像数",
        "candidate_count": "全域候选源数",
        "import_ready_count": "可导入Folo源",
        "manual_review_count": "人工核验源",
        "watch_only_count": "观察源",
        "manual_forward_count": "手动转发源",
        "watch_request_count": "监控请求",
        "checked_source_count": "实际检查源",
        "watch_success_count": "监控成功",
        "watch_failed_count": "监控失败",
        "watch_update_count": "监控新增",
        "opml_source_count": "OPML源数",
        "matched_count": "已在Folo源池",
        "missing_count": "未检测到源",
        "source_pool_count": "当前Folo源池数",
        "source_pool_stale": "源池可能旧于OPML",
        "row_count": "条目数",
        "duplicate_titles_top30": "前30标题重复",
        "url_anomaly_top30": "前30 URL异常",
        "high_risk_top10": "前10高风险",
        "empty_action_top30": "前30建议行动为空",
        "opml_source_item_count": "OPML源条目数",
        "today_count": "今日收集",
        "pending_count": "待处理",
        "processed_count": "已处理",
        "new_count": "新增处理",
        "skipped_count": "重复跳过",
        "high_risk_count": "高风险",
        "school_count": "学校类",
        "shopping_count": "购物类",
        "paid_resource_count": "付费资源",
        "feed_count": "Folo Feed数",
        "list_count": "Folo List数",
        "rsshub_count": "RSSHub源数",
        "http_feed_count": "普通HTTP源数",
        "error_feed_count": "错误/红源数",
        "unknown_count": "未知订阅数",
        "returncode": "返回码",
    }
    lines: list[str] = []
    for key, label in labels.items():
        if key in details and isinstance(details[key], (str, int, float, bool)):
            lines.append(f"- {label}：{details[key]}")
    return lines


def status_summary(status: dict) -> str:
    source = status
    title = "【InfoRadar 任务结果】"
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    if status.get("command_type") == "查看最新结果" and isinstance(details.get("status"), dict):
        source = details["status"]
        title = "【InfoRadar 最新结果】"

    lines = [title, ""]
    if title == "【InfoRadar 最新结果】":
        lines.append(f"最近任务：{source.get('command', '-')}")
    else:
        lines.append(f"命令：{source.get('command', '-')}")
    lines.extend(
        [
            f"状态：{source.get('status', '-')}",
            f"任务ID：{source.get('task_id', '-')}",
            f"完成时间：{source.get('finished_at', '-')}",
        ]
    )
    if source.get("keyword"):
        lines.append(f"关键词：{source.get('keyword')}")
    if source.get("error"):
        lines.extend(["", f"错误：{source.get('error')}"])

    summary_file = source.get("summary_file") or status.get("summary_file")
    if summary_file:
        lines.extend(["", f"摘要文件：{summary_file}"])

    files = source.get("output_files") or status.get("output_files") or []
    display_files, remaining = important_files(files)
    if display_files:
        lines.extend(["", "相关文件："])
        lines.extend([f"- {file}" for file in display_files])
        if remaining:
            lines.append(f"- ……另有 {remaining} 个文件，完整列表见 latest_status.json")

    source_details = source.get("details") if isinstance(source.get("details"), dict) else details
    metrics = metric_lines(source_details)
    if metrics:
        lines.extend(["", "关键数字："])
        lines.extend(metrics)

    lines.extend(["", "下一步：查源 关键词 / 今日情报 / 做源池 / 最新结果"])
    return "\n".join(lines)


def write_command_summary(task_id: str, status: dict) -> Path:
    path = RETURN_DIR / f"infobar_command_{task_id}_微信摘要.txt"
    text = status_summary(status)
    path.write_text(text, encoding="utf-8")
    FIXED_SUMMARY.write_text(text, encoding="utf-8")
    return path


def build_status(task_id: str, command: str, command_type: str, keyword: str, result: dict, started: str) -> dict:
    ok = result.get("returncode", 1) == 0 and result.get("success", True) is not False
    files = result_files(result)
    summary_file = result.get("return_summary") or result.get("wechat_summary") or ""
    status = {
        "task_id": task_id,
        "command": command,
        "command_type": command_type,
        "keyword": keyword,
        "status": "success" if ok else "failed",
        "started_at": started,
        "finished_at": now_text(),
        "output_files": files,
        "summary_file": summary_file,
        "details": {k: v for k, v in result.items() if k not in ("cmd",)},
        "fixed_summary_file": str(FIXED_SUMMARY),
        "error": None if ok else result.get("stderr") or result.get("error") or "命令执行失败",
    }
    command_summary = write_command_summary(task_id, status)
    if str(command_summary) not in status["output_files"]:
        status["output_files"].append(str(command_summary))
    if str(FIXED_SUMMARY) not in status["output_files"]:
        status["output_files"].append(str(FIXED_SUMMARY))
    if not status["summary_file"]:
        status["summary_file"] = str(command_summary)
    return status


def execute(command: str) -> dict:
    ensure_dirs()
    started = now_text()
    task_id = f"cmd_{stamp()}"
    original_command = command
    command = normalize_command(command)
    command_type, keyword = parse_command(command)

    if command_type == "自由指令":
        result = run_python(ROOT / "scripts" / "free_command_router.py", ["--text", keyword or original_command])
    elif command_type == "推荐订阅源":
        args = []
        if keyword:
            args.extend(["--keyword", keyword])
        result = run_python(ROOT / "scripts" / "discover_sources.py", args)
    elif command_type == "深度探测订阅源":
        args = ["--probe", "--timeout", "3", "--max-probe-sources", "8", "--max-feed-candidates", "4"]
        if keyword:
            args.extend(["--keyword", keyword])
        result = run_python(ROOT / "scripts" / "discover_sources.py", args)
    elif command_type == "深挖条目":
        args = []
        if keyword:
            args.extend(["--selector", keyword])
        result = run_python(ROOT / "scripts" / "deep_dive_item.py", args)
    elif command_type == "生成源池":
        result = run_python(ROOT / "scripts" / "build_source_pool.py", [])
    elif command_type == "生成Folo表格":
        topic = keyword or "今日"
        fetch_result = run_python(
            ROOT / "scripts" / "fetch_rss_items.py",
            [
                "--topic",
                topic,
                "--limit-sources",
                "40",
                "--max-items-per-feed",
                "8",
                "--timeout",
                "8",
            ],
        )
        fetch_output = fetch_result.get("output") if isinstance(fetch_result, dict) else ""
        if fetch_result.get("returncode", 1) != 0 or not fetch_output:
            result = fetch_result
            result["success"] = False
            result["error"] = result.get("stderr") or result.get("error") or "Folo RSS 抓取失败"
        else:
            result = run_python(ROOT / "scripts" / "inforadar_mvp.py", ["--topic", topic, "--input", str(fetch_output)])
            merged_files = []
            for file in result_files(result) + result_files(fetch_result):
                if file not in merged_files:
                    merged_files.append(file)
            result["output_files"] = merged_files
            result["fetch_source_count"] = fetch_result.get("attempted_source_count", 0)
            result["fetch_success_source_count"] = fetch_result.get("success_source_count", 0)
            result["fetch_failed_source_count"] = fetch_result.get("failed_source_count", 0)
            result["fetch_success_ratio"] = fetch_result.get("success_ratio", 0)
            result["fetch_item_count"] = fetch_result.get("item_count", 0)
            result["cache_fallback_used"] = fetch_result.get("cache_fallback_used", False)
            result["cache_fallback_candidate_count"] = fetch_result.get("cache_fallback_candidate_count", 0)
            result["cache_fallback_added_count"] = fetch_result.get("cache_fallback_added_count", 0)
            result["fetch_summary"] = fetch_result.get("return_summary", "")
            result["fetch_status_csv"] = fetch_result.get("status_csv", "")
    elif command_type == "导入Folo订阅":
        result = run_python(ROOT / "scripts" / "import_folo_subscriptions_json.py", [])
    elif command_type == "Folo导入验收":
        result = run_python(ROOT / "scripts" / "audit_folo_opml_import.py", [])
    elif command_type == "全域情报验收":
        result = run_python(ROOT / "scripts" / "audit_latest_all_domain.py", [])
    elif command_type == "收集":
        result = run_python(ROOT / "scripts" / "collect_manual_item.py", ["--text", keyword, "--from-channel", "wechat"])
    elif command_type == "查看收集箱":
        result = run_python(ROOT / "scripts" / "view_manual_inbox.py", [])
    elif command_type == "处理收集箱":
        result = run_python(ROOT / "scripts" / "process_manual_inbox.py", [])
    elif command_type == "查看收集结果":
        result = run_python(ROOT / "scripts" / "view_manual_results.py", [])
    elif command_type == "执行监控":
        result = run_python(ROOT / "scripts" / "run_watch_tasks.py", [])
    elif command_type == "查看监控":
        result = run_python(ROOT / "scripts" / "view_watch_status.py", ["--mode", "status"])
    elif command_type == "查看监控更新":
        result = run_python(ROOT / "scripts" / "view_watch_status.py", ["--mode", "updates"])
    elif command_type == "监控报告":
        result = run_python(ROOT / "scripts" / "view_watch_status.py", ["--mode", "report"])
    elif command_type == "抓取Folo更新":
        topic = keyword or "今日"
        result = run_python(
            ROOT / "scripts" / "fetch_rss_items.py",
            [
                "--topic",
                topic,
                "--limit-sources",
                "40",
                "--max-items-per-feed",
                "8",
                "--timeout",
                "8",
            ],
        )
    elif command_type == "治理RSS源":
        result = run_python(ROOT / "scripts" / "check_feed_health.py", [])
    elif command_type == "检查RSSHub":
        args = []
        if keyword:
            args.extend(["--route", keyword])
        result = run_python(ROOT / "scripts" / "check_rsshub_instances.py", args)
    elif command_type == "修复URL异常":
        args = []
        if keyword:
            args.extend(["--input", keyword])
        result = run_python(ROOT / "scripts" / "check_url_anomalies.py", args)
    elif command_type == "扩展全域源池":
        result = run_python(ROOT / "scripts" / "expand_all_domain_sources.py", [])
    elif command_type == "核验全域源池":
        result = run_python(ROOT / "scripts" / "verify_all_domain_sources.py", [])
    elif command_type == "记录反馈":
        result = run_python(ROOT / "scripts" / "feedback_collector.py", ["--feedback", keyword or original_command])
        # 反馈是对上一条任务的评价，不应覆盖“最新结果”的业务状态。
        status = build_status(task_id, command, command_type, keyword, result, started)
        status["original_command"] = original_command
        append_audit(status)
        return status
    elif command_type == "查看最新结果":
        result = run_python(ROOT / "scripts" / "read_latest_status.py", [])
        # 查看状态不覆盖 latest_status，避免把真正的最新任务冲掉。
        status = build_status(task_id, command, command_type, keyword, result, started)
        status["original_command"] = original_command
        append_audit(status)
        return status
    else:
        raise ValueError(f"未支持的命令：{command_type}")

    status = build_status(task_id, command, command_type, keyword, result, started)
    status["original_command"] = original_command
    write_latest(status)
    append_audit(status)
    return status


def append_audit(status: dict) -> None:
    append_jsonl(ROOT / "logs" / "command.log", status)
    append_jsonl(ROOT / "memory" / "task_history" / f"{today_compact()}.jsonl", status)
    if status.get("status") == "success":
        append_jsonl(ROOT / "logs" / "run.log", status)
    else:
        append_jsonl(ROOT / "logs" / "error.log", status)


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar command dispatcher")
    parser.add_argument("command", help="例如：推荐订阅源 电工证")
    args = parser.parse_args()

    try:
        status = execute(args.command)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status.get("status") == "success" else 1
    except Exception as exc:
        ensure_dirs()
        task_id = f"cmd_{stamp()}"
        status = {
            "task_id": task_id,
            "command": args.command,
            "status": "failed",
            "started_at": now_text(),
            "finished_at": now_text(),
            "output_files": [],
            "summary_file": "",
            "details": {},
            "error": repr(exc),
        }
        summary = write_command_summary(task_id, status)
        status["summary_file"] = str(summary)
        status["output_files"].append(str(summary))
        write_latest(status)
        append_audit(status)
        print(json.dumps(status, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
