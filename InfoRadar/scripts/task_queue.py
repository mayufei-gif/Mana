#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT / "data" / "task_queue"
HISTORY_DIR = ROOT / "memory" / "task_history"


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def record_task(event: dict) -> dict:
    event = dict(event)
    event.setdefault("recorded_at", now_text())
    event.setdefault("status", "recorded")
    append_jsonl(QUEUE_DIR / f"free_command_queue_{today()}.jsonl", event)
    append_jsonl(HISTORY_DIR / f"{today()}.jsonl", event)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="InfoRadar lightweight task queue recorder")
    parser.add_argument("--query", default="")
    parser.add_argument("--intent", default="free_command")
    args = parser.parse_args()
    event = record_task({"query": args.query, "intent": args.intent})
    print(json.dumps({"success": True, "event": event}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
