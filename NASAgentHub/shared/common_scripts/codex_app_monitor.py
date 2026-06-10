from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_AGENT_MAP = {
    "codex-main": ["微信直连codex"],
    "codex-app1": ["微信直连codex app1", "微信直连codexapp1"],
    "codex-app2": ["微信直连codex app2", "微信直连codexapp2"],
    "codex-app3": ["微信直连codex app3", "微信直连codexapp3"],
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|bearer|cookie|token|secret|password|passwd|口令|密钥)\s*[:=]\s*\S+"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def iso_from_epoch(value: int | float | None) -> str:
    if not value:
        return ""
    raw = float(value)
    if raw > 10_000_000_000:
        raw = raw / 1000
    return datetime.fromtimestamp(raw, timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def scrub(text: object, limit: int = 240) -> str:
    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("<redacted>", value)
    value = re.sub(r"\s+", " ", value)
    if len(value) > limit:
        value = value[:limit].rstrip() + "..."
    return value


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def find_agenthub_root(start: Path) -> Path:
    candidates = [start, *start.parents]
    candidates.extend(
        [
            Path("G:/E盘/工作项目文件/NAS/NASAgentHub"),
            Path.home() / "NASAgentHub",
            Path("/home/mana/NASAgentHub"),
        ]
    )
    for candidate in candidates:
        if (candidate / "coordination").exists():
            return candidate
    raise SystemExit("Cannot find NASAgentHub root")


def load_session_index(codex_root: Path) -> dict[str, dict]:
    path = codex_root / "session_index.jsonl"
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        thread_id = item.get("id")
        if thread_id:
            rows[thread_id] = item
    return rows


def load_threads(codex_root: Path) -> list[dict]:
    db_path = codex_root / "state_5.sqlite"
    if not db_path.exists():
        return []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select
              id, rollout_path, created_at, updated_at, created_at_ms, updated_at_ms,
              source, thread_source, cwd, title, preview, first_user_message,
              agent_nickname, agent_role, agent_path, tokens_used, archived
            from threads
            order by coalesce(updated_at_ms, updated_at, created_at_ms, created_at) desc
            """
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def thread_updated_iso(row: dict) -> str:
    return iso_from_epoch(row.get("updated_at_ms") or row.get("updated_at"))


def session_updated_iso(index_row: dict) -> str:
    return str(index_row.get("updated_at") or "")


def find_rollout_path(codex_root: Path, row: dict) -> Path | None:
    raw = row.get("rollout_path")
    if raw:
        path = Path(str(raw))
        if path.exists():
            return path
        path = codex_root / str(raw)
        if path.exists():
            return path
    thread_id = row.get("id")
    if not thread_id:
        return None
    sessions_dir = codex_root / "sessions"
    if not sessions_dir.exists():
        return None
    matches = sorted(sessions_dir.rglob(f"*{thread_id}.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def extract_recent_messages(path: Path | None, limit: int = 8) -> list[dict]:
    if not path or not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        timestamp = obj.get("timestamp") or ""
        if obj.get("type") == "event_msg" and payload_type == "user_message":
            text = scrub(payload.get("message"), 220)
            if text:
                rows.append({"at": timestamp, "kind": "user", "phase": "user", "text": text})
        elif obj.get("type") == "event_msg" and payload_type == "agent_message":
            text = scrub(payload.get("message"), 220)
            if text:
                rows.append({"at": timestamp, "kind": "assistant", "phase": payload.get("phase") or "", "text": text})
        elif obj.get("type") == "event_msg" and payload_type in {"task_started", "task_complete"}:
            label = "任务开始" if payload_type == "task_started" else "任务完成"
            rows.append({"at": timestamp, "kind": "event", "phase": payload_type, "text": label})
    return rows[-limit:]


def choose_threads(threads: list[dict], session_index: dict[str, dict], agent_map: dict[str, list[str]]) -> list[dict]:
    selected = []
    used_ids: set[str] = set()
    for agent_id, names in agent_map.items():
        normalized_names = [normalize_name(name) for name in names]
        matches = []
        for row in threads:
            index_row = session_index.get(row.get("id"), {})
            search_text = normalize_name(
                " ".join(
                    [
                        str(index_row.get("thread_name") or ""),
                        str(row.get("title") or ""),
                        str(row.get("cwd") or ""),
                        str(row.get("agent_path") or ""),
                    ]
                )
            )
            if any(name and name in search_text for name in normalized_names):
                matches.append(row)
        if not matches and agent_id == "codex-main":
            matches = [
                row
                for row in threads
                if "微信直连codex" in normalize_name(str(session_index.get(row.get("id"), {}).get("thread_name") or ""))
                and all(f"app{i}" not in normalize_name(str(session_index.get(row.get("id"), {}).get("thread_name") or "")) for i in [1, 2, 3])
            ]
        if matches:
            match = sorted(matches, key=lambda row: row.get("updated_at_ms") or row.get("updated_at") or 0, reverse=True)[0]
            used_ids.add(match.get("id", ""))
            selected.append({"agent_id": agent_id, "row": match, "match_source": "mapped_name"})
        else:
            selected.append({"agent_id": agent_id, "row": None, "match_source": "not_found"})
    return selected


def build_payload(codex_root: Path, agenthub_root: Path, max_messages: int) -> dict:
    session_index = load_session_index(codex_root)
    threads = load_threads(codex_root)
    selected = choose_threads(threads, session_index, DEFAULT_AGENT_MAP)
    generated_at = now_iso()
    now_dt = datetime.now(timezone.utc)
    items = []
    for selected_item in selected:
        agent_id = selected_item["agent_id"]
        row = selected_item["row"]
        if not row:
            items.append(
                {
                    "agent_id": agent_id,
                    "status": "not_found",
                    "source": "codex_app_local",
                    "monitor_checked_at": generated_at,
                    "message": "未在本机 Codex App 会话索引中找到匹配会话",
                }
            )
            continue
        index_row = session_index.get(row.get("id"), {})
        updated_at = thread_updated_iso(row) or session_updated_iso(index_row)
        updated_dt = parse_iso(updated_at)
        age_seconds = int((now_dt - updated_dt).total_seconds()) if updated_dt else None
        status = "active" if age_seconds is not None and age_seconds <= 1800 else "stale"
        if row.get("archived"):
            status = "archived"
        rollout_path = find_rollout_path(codex_root, row)
        items.append(
            {
                "agent_id": agent_id,
                "status": status,
                "thread_id": row.get("id") or "",
                "session_thread_name": scrub(index_row.get("thread_name") or "", 120),
                "title": scrub(row.get("title") or index_row.get("thread_name") or "", 160),
                "preview": scrub(row.get("preview") or row.get("first_user_message") or "", 240),
                "cwd": scrub(str(row.get("cwd") or ""), 260),
                "source": "codex_app_local",
                "thread_source": row.get("thread_source") or "",
                "app_source": row.get("source") or "",
                "updated_at": updated_at,
                "updated_age_seconds": age_seconds,
                "tokens_used": row.get("tokens_used") or 0,
                "archived": bool(row.get("archived")),
                "rollout_path": scrub(str(rollout_path or ""), 300),
                "recent_messages": extract_recent_messages(rollout_path, limit=max_messages),
                "monitor_checked_at": generated_at,
                "privacy_mode": "summary_only",
            }
        )
    return {
        "version": "1.0",
        "updated_at": generated_at,
        "source": "codex_app_local_monitor",
        "privacy_mode": "summary_only",
        "codex_root": str(codex_root),
        "agenthub_root": str(agenthub_root),
        "items": items,
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_heartbeats(agenthub_root: Path, payload: dict) -> None:
    path = agenthub_root / "coordination" / "AGENT_HEARTBEATS.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"version": "1.0", "max_age_seconds": 300, "items": []}
    items = [item for item in data.get("items", []) if item.get("agent_id") not in {row.get("agent_id") for row in payload.get("items", [])}]
    for row in payload.get("items", []):
        items.append(
            {
                "agent_id": row.get("agent_id"),
                "heartbeat_at": payload.get("updated_at"),
                "source": "codex_app_monitor",
                "current_thread": row.get("session_thread_name") or row.get("title") or "",
                "thread_id": row.get("thread_id") or "",
                "thread_updated_at": row.get("updated_at") or "",
                "note": row.get("preview") or row.get("message") or "",
            }
        )
    data["updated_at"] = payload.get("updated_at")
    data["items"] = sorted(items, key=lambda item: item.get("agent_id") or "")
    atomic_write_json(path, data)


def copy_to_remote(local_path: Path, remote_target: str) -> None:
    if not remote_target:
        return
    scp = shutil.which("scp")
    if not scp:
        raise RuntimeError("scp not found; cannot sync remote target")
    result = subprocess.run([scp, str(local_path), remote_target], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode != 0:
        raise RuntimeError(scrub(result.stderr or result.stdout or f"scp failed: {result.returncode}", 500))


def run_once(args: argparse.Namespace) -> Path:
    codex_root = Path(args.codex_root).expanduser().resolve()
    agenthub_root = Path(args.agenthub_root).expanduser().resolve() if args.agenthub_root else find_agenthub_root(Path.cwd().resolve())
    payload = build_payload(codex_root, agenthub_root, args.max_messages)
    output_path = agenthub_root / "coordination" / "CODEX_APP_THREADS.json"
    atomic_write_json(output_path, payload)
    update_heartbeats(agenthub_root, payload)
    if args.remote:
        copy_to_remote(output_path, args.remote)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Read local Codex App thread summaries into NASAgentHub.")
    parser.add_argument("--codex-root", default=str(Path.home() / ".codex"))
    parser.add_argument("--agenthub-root", default="")
    parser.add_argument("--remote", default="", help="Optional scp target, for example ubuntu-vm:/home/mana/NASAgentHub/coordination/CODEX_APP_THREADS.json")
    parser.add_argument("--max-messages", type=int, default=8)
    parser.add_argument("--watch", type=int, default=0, help="Run every N seconds. 0 means one-shot.")
    args = parser.parse_args()

    if args.watch:
        while True:
            try:
                output_path = run_once(args)
                print(f"codex app threads updated: {output_path}")
            except Exception as exc:
                print(f"codex app monitor error: {exc}")
            time.sleep(max(5, args.watch))
    else:
        output_path = run_once(args)
        print(f"codex app threads updated: {output_path}")


if __name__ == "__main__":
    main()
