from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.backend.file_index import EXPECTED_AUTOMATION_BEIJING_TIMES, automation_cron_beijing_times


def main() -> int:
    cron = """
@reboot /home/mana/bin/start-workstation >/home/mana/.cache/codex-workstation/startup.log 2>&1
30 0,3,9,13 * * * cd /home/mana/InfoRadar && TZ=Asia/Shanghai /home/mana/inforadar-runtime/venv/bin/python /home/mana/InfoRadar/scripts/run_daily_automation.py >> /home/mana/InfoRadar/logs/daily_automation.cron.log 2>&1 # InfoRadar daily automation Beijing 08:30/11:30/17:30/21:30
"""
    times = automation_cron_beijing_times(cron)
    if times != EXPECTED_AUTOMATION_BEIJING_TIMES:
        raise AssertionError(f"wrong Beijing schedule: {times}")

    incomplete = automation_cron_beijing_times("30 0,3,9 * * * /home/mana/InfoRadar/scripts/run_daily_automation.py")
    missing = [item for item in EXPECTED_AUTOMATION_BEIJING_TIMES if item not in incomplete]
    if missing != ["21:30"]:
        raise AssertionError(f"incomplete schedule should miss 21:30: {incomplete}")

    print({"ok": True, "beijing_times": times})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
