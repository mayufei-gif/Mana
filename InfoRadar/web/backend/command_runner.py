from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .file_index import LATEST_STATUS_JSON, LATEST_STATUS_SUMMARY, RETURN_DIR, list_return_files, read_json, read_text


ROOT = Path(__file__).resolve().parents[2]
INFOBAR = ROOT / "scripts" / "infobar_command.py"
COMMAND_TIMEOUT_SECONDS = 300

ALLOWED_EXACT = {
    "今日情报",
    "全域情报",
    "今日AI",
    "今日技术",
    "今日政策",
    "今日招聘",
    "今日证书",
    "我的学校",
    "购物情报",
    "付费资源",
    "风险提醒",
    "本地山西",
    "时事热点",
    "国际观察",
    "科技前沿",
    "开源动态",
    "网络安全",
    "法律权益",
    "健康医学",
    "财经商业",
    "学习资源",
    "最新结果",
    "处理收集箱",
    "查看收集箱",
    "查看收集结果",
    "执行监控",
    "查看监控",
    "查看监控更新",
    "监控报告",
    "生成源池",
    "生成Folo导入清单",
    "导入Folo",
    "导入Folo订阅",
    "同步Folo全域源",
    "Folo导入验收",
    "全域源导入验收",
    "全域情报验收",
    "抓取Folo",
    "抓取Folo更新",
    "刷新Folo",
    "刷新Folo内容",
    "治理RSS源",
    "检查RSSHub",
    "扩展全域源池",
    "核验全域源池",
    "/ir",
    "/find",
    "/watch",
    "/collect",
    "/deep",
}

ALLOWED_PREFIXES = (
    "/ir ",
    "/find ",
    "/watch ",
    "/collect ",
    "/deep ",
    "收集 ",
    "查源 ",
    "深挖",
    "以后多关注",
    "以后少推",
    "不要再推",
    "忽略",
    "记住",
    "记录反馈 ",
    "这个有用",
    "这个没用",
)

SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(token[\"'\s:=]+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(cookie[\"'\s:=]+)[^\s,;]{8,}"),
    re.compile(r"(?i)(api[_-]?key[\"'\s:=]+)[A-Za-z0-9._~+/=-]{8,}"),
]


def sanitize(text: str) -> str:
    value = text or ""
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(r"\1[REDACTED]", value)
    return value


def normalize_command(command: str) -> str:
    return " ".join((command or "").strip().split())


def is_allowed_command(command: str) -> bool:
    value = normalize_command(command)
    if value in ALLOWED_EXACT:
        return True
    return any(value.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def output_files_from_status(status: dict) -> list[str]:
    files = status.get("output_files") if isinstance(status, dict) else []
    if not isinstance(files, list):
        files = []
    recent = [entry["path"] for entry in list_return_files(12)]
    merged: list[str] = []
    for file in [*files, *recent]:
        if isinstance(file, str) and file and file not in merged:
            merged.append(file)
    return merged[:30]


def run_inforadar_command(command: str) -> dict:
    normalized = normalize_command(command)
    if not normalized:
        return {"ok": False, "command": command, "status": "failed", "error": "命令不能为空"}
    if not is_allowed_command(normalized):
        return {
            "ok": False,
            "command": normalized,
            "status": "blocked",
            "error": "该命令不在 Web 控制台白名单内",
        }

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, str(INFOBAR), normalized],
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "command": normalized,
            "status": "timeout",
            "summary": "",
            "output_files": [],
            "latest_status": read_json(LATEST_STATUS_JSON),
            "stdout": sanitize(exc.stdout or ""),
            "stderr": sanitize(exc.stderr or ""),
            "error": f"命令超过 {COMMAND_TIMEOUT_SECONDS} 秒未完成",
        }

    status = read_json(LATEST_STATUS_JSON)
    summary = read_text(LATEST_STATUS_SUMMARY)
    ok = proc.returncode == 0 and status.get("status", "success") != "failed"
    return {
        "ok": ok,
        "command": normalized,
        "status": "success" if ok else "failed",
        "summary": sanitize(summary),
        "output_files": output_files_from_status(status),
        "latest_status": status,
        "stdout": sanitize(proc.stdout[-8000:]),
        "stderr": sanitize(proc.stderr[-8000:]),
        "error": "" if ok else sanitize(status.get("error") or proc.stderr or "命令执行失败"),
    }
