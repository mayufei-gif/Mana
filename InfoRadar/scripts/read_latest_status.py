#!/usr/bin/env python3
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETURN_DIR = Path(os.environ.get("INFORADAR_RETURN_DIR", r"G:\E盘\工作项目文件\NAS回传\FOLO"))
LATEST_STATUS = ROOT / "logs" / "latest_status.json"


def main() -> int:
    if not LATEST_STATUS.exists():
        result = {
            "success": False,
            "error": "latest_status.json 不存在",
            "output_files": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    status = json.loads(LATEST_STATUS.read_text(encoding="utf-8-sig"))
    lines = [
        "【InfoRadar 最新结果】",
        "",
        f"命令：{status.get('command', '-')}",
        f"状态：{status.get('status', '-')}",
        f"任务ID：{status.get('task_id', '-')}",
        f"完成时间：{status.get('finished_at', '-')}",
    ]
    if status.get("error"):
        lines.extend(["", f"错误：{status.get('error')}"])
    files = status.get("output_files") or []
    if files:
        lines.extend(["", "输出文件："])
        lines.extend([f"- {file}" for file in files])

    RETURN_DIR.mkdir(parents=True, exist_ok=True)
    summary = RETURN_DIR / "latest_status_微信摘要.txt"
    summary.write_text("\n".join(lines), encoding="utf-8")

    result = {
        "success": True,
        "latest_status": str(LATEST_STATUS),
        "return_summary": str(summary),
        "output_files": [str(summary), *files],
        "status": status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
