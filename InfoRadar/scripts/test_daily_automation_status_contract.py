#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import run_daily_automation as daily
from web.backend import file_index


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        log_dir = root / "logs"
        return_dir = root / "return"
        payload = {
            "ok": True,
            "status": "success",
            "command": "自动巡检",
            "started_at": "2026-06-11 08:30:00",
            "finished_at": "2026-06-11 08:31:00",
            "commands": [
                {
                    "command": "全域情报",
                    "success": True,
                    "started_at": "2026-06-11 08:30:01",
                    "finished_at": "2026-06-11 08:30:59",
                }
            ],
        }

        daily.LOG_DIR = log_dir
        daily.RUN_LOG = log_dir / "daily_automation.log"
        daily.STATE_JSON = log_dir / "daily_automation_latest.json"
        daily.LATEST_STATUS_JSON = log_dir / "latest_status.json"
        daily.RETURN_LATEST_STATUS_JSON = return_dir / "latest_status.json"
        daily.RETURN_LATEST_STATUS_SUMMARY = return_dir / "latest_status_微信摘要.txt"

        daily.write_daily_status(payload)

        required = [
            daily.STATE_JSON,
            daily.LATEST_STATUS_JSON,
            daily.RETURN_LATEST_STATUS_JSON,
            daily.RETURN_LATEST_STATUS_SUMMARY,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise AssertionError(f"missing status outputs: {missing}")

        internal = json.loads(daily.LATEST_STATUS_JSON.read_text(encoding="utf-8"))
        automation = json.loads(daily.STATE_JSON.read_text(encoding="utf-8"))
        returned = json.loads(daily.RETURN_LATEST_STATUS_JSON.read_text(encoding="utf-8"))

        if internal.get("command") != "自动巡检" or internal.get("status") != "success":
            raise AssertionError(f"bad internal latest_status: {internal}")
        if automation.get("commands", [{}])[0].get("command") != "全域情报":
            raise AssertionError(f"bad automation status: {automation}")
        if returned != internal:
            raise AssertionError("return latest_status must mirror project latest_status")

        summary = daily.RETURN_LATEST_STATUS_SUMMARY.read_text(encoding="utf-8")
        for text in ["InfoRadar 自动巡检", "全域情报", "2026-06-11 08:31:00"]:
            if text not in summary:
                raise AssertionError(f"summary missing {text!r}: {summary}")

        file_index.RETURN_DIR = return_dir
        file_index.LATEST_STATUS_JSON = daily.RETURN_LATEST_STATUS_JSON
        file_index.LATEST_STATUS_SUMMARY = daily.RETURN_LATEST_STATUS_SUMMARY
        file_index.DAILY_AUTOMATION_STATE_JSON = daily.STATE_JSON
        file_index.SEARCH_INDEX_META_JSON = root / "cache" / "search_index_meta.json"
        file_index.SEARCH_INDEX_DB = root / "cache" / "search_index.sqlite"
        file_index.INSPECTION_INTERVAL_STATE_JSON = root / "data" / "inspection_interval.json"
        status = file_index.latest_status()
        health = status.get("health") or {}
        if health.get("daily_automation_command_count") != 1:
            raise AssertionError(f"backend health missed command count: {health}")
        if health.get("daily_automation_failed_count") != 0:
            raise AssertionError(f"backend health reported false failures: {health}")
        if health.get("last_command") != "自动巡检":
            raise AssertionError(f"backend health missed latest command: {health}")

    print({"ok": True, "status_file": "latest_status.json"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
