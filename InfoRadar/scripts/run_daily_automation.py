#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RETURN_DIR = Path(r"G:\E盘\工作项目文件\NAS回传\FOLO") if os.name == "nt" else Path("/home/mana/inforadar-return/FOLO")
LOG_DIR = ROOT / "logs"
RUN_LOG = LOG_DIR / "daily_automation.log"
STATE_JSON = LOG_DIR / "daily_automation_latest.json"
LATEST_STATUS_JSON = LOG_DIR / "latest_status.json"
RETURN_LATEST_STATUS_JSON = DEFAULT_RETURN_DIR / "latest_status.json"
RETURN_LATEST_STATUS_SUMMARY = DEFAULT_RETURN_DIR / "latest_status_微信摘要.txt"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


COMMANDS = [
    "处理收集箱",
    "执行监控",
    "全域情报",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def automation_env() -> dict:
    env = os.environ.copy()
    env.setdefault("INFORADAR_RETURN_DIR", str(DEFAULT_RETURN_DIR))
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_command(command: str) -> dict:
    started = now_text()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "infobar_command.py"), command],
        cwd=str(ROOT),
        env=automation_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
    )
    return {
        "command": command,
        "started_at": started,
        "finished_at": now_text(),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "success": proc.returncode == 0,
    }


def rebuild_search_index() -> dict:
    started = now_text()
    try:
        from web.backend.file_index import build_search_index

        result = build_search_index(force=True)
        return {
            "command": "重建搜索索引",
            "started_at": started,
            "finished_at": now_text(),
            "returncode": 0 if result.get("ok") else 1,
            "stdout_tail": json.dumps(result, ensure_ascii=False)[-4000:],
            "stderr_tail": "",
            "success": bool(result.get("ok")),
        }
    except Exception as exc:
        return {
            "command": "重建搜索索引",
            "started_at": started,
            "finished_at": now_text(),
            "returncode": 1,
            "stdout_tail": "",
            "stderr_tail": repr(exc),
            "success": False,
        }


def sync_wechat_sources() -> dict:
    started = now_text()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_wechat_electronic_textbooks.py")],
        cwd=str(ROOT),
        env=automation_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    return {
        "command": "同步微信公众号源",
        "started_at": started,
        "finished_at": now_text(),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "success": proc.returncode == 0,
    }


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def automation_summary(payload: dict) -> str:
    commands = payload.get("commands") if isinstance(payload.get("commands"), list) else []
    failed = [item for item in commands if isinstance(item, dict) and not item.get("success")]
    lines = [
        "【InfoRadar 自动巡检】",
        "",
        f"命令：{payload.get('command') or '自动巡检'}",
        f"状态：{payload.get('status') or ('success' if payload.get('ok') else 'failed')}",
        f"开始时间：{payload.get('started_at') or '-'}",
        f"完成时间：{payload.get('finished_at') or '-'}",
        f"步骤：{len(commands)} 个，成功 {len(commands) - len(failed)} 个，失败 {len(failed)} 个",
    ]
    if commands:
        lines.extend(["", "执行步骤："])
        for item in commands:
            if not isinstance(item, dict):
                continue
            mark = "OK" if item.get("success") else "FAIL"
            lines.append(f"- [{mark}] {item.get('command') or '未命名步骤'}")
    if failed:
        lines.extend(["", "失败步骤："])
        for item in failed[:6]:
            error = item.get("stderr_tail") or item.get("stdout_tail") or "未记录错误"
            lines.append(f"- {item.get('command') or '未命名步骤'}：{str(error).strip()[:240]}")
    return "\n".join(lines)


def write_daily_status(payload: dict) -> dict:
    status = {
        **payload,
        "command": payload.get("command") or "自动巡检",
        "status": payload.get("status") or ("success" if payload.get("ok") else "failed"),
    }
    for path in [STATE_JSON, LATEST_STATUS_JSON, RETURN_LATEST_STATUS_JSON]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    RETURN_LATEST_STATUS_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    RETURN_LATEST_STATUS_SUMMARY.write_text(automation_summary(status), encoding="utf-8")
    append_jsonl(RUN_LOG, status)
    return status


def main() -> int:
    os.environ.setdefault("INFORADAR_RETURN_DIR", str(DEFAULT_RETURN_DIR))
    os.environ.setdefault("LANG", "C.UTF-8")
    os.environ.setdefault("LC_ALL", "C.UTF-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"
    DEFAULT_RETURN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    started = now_text()
    results = [run_command(command) for command in COMMANDS]
    results.append(sync_wechat_sources())
    results.append(rebuild_search_index())
    ok = all(item["success"] for item in results)
    payload = {
        "ok": ok,
        "command": "自动巡检",
        "status": "success" if ok else "failed",
        "started_at": started,
        "finished_at": now_text(),
        "commands": results,
    }
    status = write_daily_status(payload)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
