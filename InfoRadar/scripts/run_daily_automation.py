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
        "started_at": started,
        "finished_at": now_text(),
        "commands": results,
    }
    append_jsonl(RUN_LOG, payload)
    STATE_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
