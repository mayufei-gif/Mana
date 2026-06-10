from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def find_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "coordination" / "AGENT_STATUS.json").exists():
            return candidate
    raise SystemExit("Cannot find NASAgentHub root from current path")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update NASAgentHub agent heartbeat")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--source", default="codex-desktop")
    parser.add_argument("--thread", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    root = find_root(Path.cwd().resolve())
    path = root / "coordination" / "AGENT_HEARTBEATS.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"version": "1.0", "max_age_seconds": 300, "items": []}

    heartbeat_at = now_iso()
    items = [item for item in data.get("items", []) if item.get("agent_id") != args.agent_id]
    items.append(
        {
            "agent_id": args.agent_id,
            "heartbeat_at": heartbeat_at,
            "source": args.source,
            "current_thread": args.thread,
            "note": args.note,
        }
    )
    data["updated_at"] = heartbeat_at
    data["items"] = sorted(items, key=lambda item: item.get("agent_id", ""))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"heartbeat updated: {args.agent_id} at {heartbeat_at}")


if __name__ == "__main__":
    main()
