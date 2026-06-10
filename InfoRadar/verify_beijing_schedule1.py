from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_JS = ROOT / "web" / "frontend" / "app.js"
INDEX_HTML = ROOT / "web" / "frontend" / "index.html"


def require(name: str, red: str, green: str, passed: bool) -> None:
    print(name)
    print(f"  RED: {red}")
    print(f"  GREEN: {green}")
    if not passed:
        raise AssertionError(f"{name} 未通过")
    print("  RESULT: GREEN\n")


def main() -> None:
    app_js = APP_JS.read_text(encoding="utf-8", errors="replace")
    index_html = INDEX_HTML.read_text(encoding="utf-8", errors="replace")
    proc = subprocess.run(["crontab", "-l"], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
    cron_text = proc.stdout or ""
    require(
        "SCHEDULE.1 北京时间四次抓取 crontab",
        "crontab 仍是旧的单次 UTC 01:20，或没有 run_daily_automation.py。",
        "crontab 使用 UTC 00:30/03:30/09:30/13:30，对应北京时间 08:30/11:30/17:30/21:30。",
        "30 0,3,9,13 * * *" in cron_text and "run_daily_automation.py" in cron_text and "20 1 * * *" not in cron_text,
    )
    require(
        "SCHEDULE.2 自动化进程使用北京时间",
        "定时命令未设置 TZ=Asia/Shanghai，生成的完成时间继续按 UTC 写。",
        "定时命令包含 TZ=Asia/Shanghai，让自动化输出时间按北京时间生成。",
        "TZ=Asia/Shanghai" in cron_text,
    )
    require(
        "SCHEDULE.3 页面按北京时间巡检窗口显示",
        "页面仍直接显示后端 UTC/旧缓存 inspection_interval_label。",
        "页面包含 Asia/Shanghai、beijingInspectionWindow、当前窗口和下次抓取。",
        all(term in app_js for term in ["Asia/Shanghai", "beijingInspectionWindow", "当前窗口", "下次抓取", "服务器原始时区：UTC"]),
    )
    require(
        "SCHEDULE.4 静态版本已刷新",
        "浏览器仍可能加载旧 JS。",
        "index.html 引用当前合并版本 20260610-coursemind-button-main1。",
        "20260610-coursemind-button-main1" in index_html,
    )
    require(
        "SCHEDULE.5 四次更新文案",
        "页面仍写每天三遍，和四个时间点冲突。",
        "页面写用户级 crontab 每天自动更新四遍 InfoRadar。",
        "每天自动更新四遍 InfoRadar" in app_js and "每天自动更新三遍" not in app_js,
    )
    print("BEIJING_SCHEDULE_ALL_GREEN")


if __name__ == "__main__":
    main()
