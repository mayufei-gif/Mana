#!/usr/bin/env python3
"""Windows Codex App bridge for AgentHub session messages.

This bridge deliberately avoids blind mouse/keyboard automation. Until a real
Codex App app-server/thread API is bound, pending messages are converted into
handoff files and marked as manual-handoff in AgentHub.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from codex_app_discovery import (
    capabilities as codex_capabilities,
    dry_run_send as codex_dry_run_send,
    generate_discovery_files,
    load_thread_tree,
)


DEFAULT_SERVER_URL = "https://inforadar.mana-mana.top/mcp"
DEFAULT_SESSION_ID = "session-win-api-agenthub-001"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_AGENTHUB_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_OUTBOX = SCRIPT_DIR / "outbox"
DEFAULT_STATE = SCRIPT_DIR / "bridge_state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def scrub_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe_query = [(key, "<redacted>" if "token" in key.lower() else value) for key, value in query]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(safe_query), parsed.fragment))


def derive_api_base_and_token(server_url: str, explicit_token: str = "") -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(server_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    token = explicit_token or query.get("access_token") or query.get("token") or os.environ.get("AGENTHUB_TOKEN", "")
    path = parsed.path.rstrip("/")
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")]
    base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))
    return base.rstrip("/"), token


class AgentHubClient:
    def __init__(self, server_url: str, token: str = "", timeout: float = 30.0) -> None:
        self.server_url = server_url
        self.base_url, self.token = derive_api_base_and_token(server_url, token)
        self.timeout = timeout

    def url(self, path: str, params: dict | None = None) -> str:
        url = f"{self.base_url}{path}"
        merged = dict(params or {})
        if self.token:
            merged.setdefault("access_token", self.token)
        if merged:
            url = f"{url}?{urllib.parse.urlencode(merged)}"
        return url

    def request(self, method: str, path: str, payload: dict | None = None, params: dict | None = None) -> dict:
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentHubWindowsBridge/0.1",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url(path, params), data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AgentHub HTTP {exc.code}: {raw[:800]}") from exc
        return json.loads(raw or "{}")

    def get(self, path: str, params: dict | None = None) -> dict:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict) -> dict:
        return self.request("POST", path, payload=payload)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": "1.0", "processed_message_ids": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "1.0", "processed_message_ids": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_handoff_body(message: dict, bridge_id: str) -> str:
    message_id = str(message.get("message_id") or "message")
    task_id = str(message.get("task_id") or "")
    session_id = str(message.get("session_id") or "")
    return f"""# AgentHub -> Windows Codex App Handoff

bridge_id: {bridge_id}
message_id: {message_id}
task_id: {task_id}
session_id: {session_id}
agent_id: {message.get("agent_id") or ""}
created_at: {message.get("created_at") or ""}
handoff_created_at: {now_iso()}

## 投递说明

当前没有可用的 Codex App app-server/thread API，因此本 Bridge 不做鼠标键盘盲投递。

请把下面的任务内容复制到对应的 Windows Codex App 会话中。该会话应匹配：

- session_id: {session_id}
- agent_id: {message.get("agent_id") or ""}
- task_id: {task_id}

## 任务内容

```text
{message.get("content") or ""}
```

## 回复回填

Codex App 回复后，把回复保存为文本文件，然后运行：

```powershell
python "{Path(__file__).resolve()}" reply --session-id "{session_id}" --in-reply-to "{message_id}" --task-id "{task_id}" --file "回复文件路径.txt"
```
"""


def write_handoff(outbox: Path, message: dict, bridge_id: str) -> tuple[Path, str]:
    outbox.mkdir(parents=True, exist_ok=True)
    message_id = str(message.get("message_id") or "message")
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{message_id}.md"
    path = outbox / filename
    body = build_handoff_body(message, bridge_id)
    path.write_text(body, encoding="utf-8")
    return path, body


def cmd_status(args: argparse.Namespace) -> int:
    client = AgentHubClient(args.server_url, args.token, args.timeout)
    codex_root = Path(args.codex_root).expanduser()
    state_db = codex_root / "state_5.sqlite"
    result = {
        "ok": True,
        "bridge_id": args.bridge_id,
        "server_url": scrub_url(args.server_url),
        "api_base": client.base_url,
        "token_configured": bool(client.token),
        "codex_root": str(codex_root),
        "codex_state_db_exists": state_db.exists(),
        "outbox": str(Path(args.outbox).expanduser()),
    }
    try:
        overview = client.get("/api/agenthub/overview")
        result["agenthub_ok"] = bool(overview.get("ok"))
        result["agent_count"] = overview.get("agent_count")
        result["session_count"] = overview.get("session_count")
    except Exception as exc:
        result["agenthub_ok"] = False
        result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("agenthub_ok") else 1


def cmd_sessions(args: argparse.Namespace) -> int:
    client = AgentHubClient(args.server_url, args.token, args.timeout)
    print(json.dumps(client.get("/api/agenthub/sessions"), ensure_ascii=False, indent=2))
    return 0


def poll_once(args: argparse.Namespace) -> int:
    client = AgentHubClient(args.server_url, args.token, args.timeout)
    state_path = Path(args.state).expanduser()
    state = load_state(state_path)
    seen = set(state.get("processed_message_ids") or [])
    pending = client.get(
        "/api/agenthub/bridge/pending",
        {"session_id": args.session_id or "", "limit": str(args.limit)},
    ).get("messages", [])
    handled = []
    for message in pending:
        message_id = str(message.get("message_id") or "")
        if not message_id or message_id in seen:
            continue
        handoff_path, handoff_body = write_handoff(Path(args.outbox).expanduser(), message, args.bridge_id)
        client.post(
            f"/api/agenthub/bridge/messages/{urllib.parse.quote(message_id)}/status",
            {
                "status": "handoff-ready",
                "delivery": "manual-handoff",
                "bridge_status": "handoff-ready",
                "bridge_id": args.bridge_id,
                "handoff_path": str(handoff_path),
                "handoff_content": handoff_body,
                "note": "Windows Bridge generated manual handoff because Codex App app-server/thread API is not bound.",
            },
        )
        seen.add(message_id)
        handled.append({"message_id": message_id, "handoff_path": str(handoff_path)})
    state["processed_message_ids"] = sorted(seen)[-1000:]
    state["updated_at"] = now_iso()
    save_state(state_path, state)
    print(json.dumps({"ok": True, "handled": handled, "handled_count": len(handled)}, ensure_ascii=False, indent=2))
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    if args.watch:
        while True:
            try:
                poll_once(args)
            except Exception as exc:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            time.sleep(max(1.0, args.poll_seconds))
    return poll_once(args)


def cmd_reply(args: argparse.Namespace) -> int:
    client = AgentHubClient(args.server_url, args.token, args.timeout)
    if args.file:
        content = Path(args.file).expanduser().read_text(encoding="utf-8", errors="replace")
    else:
        content = args.content or sys.stdin.read()
    payload = {
        "session_id": args.session_id,
        "content": content,
        "task_id": args.task_id or None,
        "in_reply_to": args.in_reply_to or None,
        "source": args.bridge_id,
        "role": "codex",
        "status": "received",
        "delivery": "manual-reply",
    }
    print(json.dumps(client.post("/api/agenthub/bridge/reply", payload), ensure_ascii=False, indent=2))
    return 0


def cmd_discover_thread_tree(args: argparse.Namespace) -> int:
    result = generate_discovery_files(
        Path(args.codex_root).expanduser(),
        Path(args.agenthub_root).expanduser(),
        args.local_bridge_status_url,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    result = codex_capabilities(Path(args.agenthub_root).expanduser(), args.local_bridge_status_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_thread_tree(args: argparse.Namespace) -> int:
    root = Path(args.agenthub_root).expanduser()
    tree_path = root / "coordination" / "CODEX_APP_THREAD_TREE.json"
    if args.refresh or not tree_path.exists():
        generate_discovery_files(Path(args.codex_root).expanduser(), root, args.local_bridge_status_url)
    print(json.dumps(load_thread_tree(root), ensure_ascii=False, indent=2))
    return 0


def cmd_dry_run_send(args: argparse.Namespace) -> int:
    root = Path(args.agenthub_root).expanduser()
    tree_path = root / "coordination" / "CODEX_APP_THREAD_TREE.json"
    if not tree_path.exists():
        generate_discovery_files(Path(args.codex_root).expanduser(), root, args.local_bridge_status_url)
    result = codex_dry_run_send(
        root,
        session_id=args.session_id,
        thread_ref=args.thread_ref,
        message=args.message,
        bridge_status_url=args.local_bridge_status_url,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows Codex App Bridge for AgentHub")
    parser.add_argument("--server-url", default=os.environ.get("AGENTHUB_SERVER_URL") or os.environ.get("AGENTHUB_MCP_URL") or DEFAULT_SERVER_URL)
    parser.add_argument("--token", default=os.environ.get("AGENTHUB_TOKEN", ""))
    parser.add_argument("--bridge-id", default=os.environ.get("AGENTHUB_WINDOWS_BRIDGE_ID", "windows-codex-app-bridge"))
    parser.add_argument("--session-id", default=os.environ.get("AGENTHUB_SESSION_ID", DEFAULT_SESSION_ID))
    parser.add_argument("--codex-root", default=os.environ.get("CODEX_ROOT", str(Path.home() / ".codex")))
    parser.add_argument("--agenthub-root", default=os.environ.get("AGENTHUB_ROOT", str(DEFAULT_AGENTHUB_ROOT)))
    parser.add_argument("--local-bridge-status-url", default=os.environ.get("CODEX_LOCAL_BRIDGE_STATUS_URL", "http://127.0.0.1:19577/status"))
    parser.add_argument("--outbox", default=os.environ.get("AGENTHUB_BRIDGE_OUTBOX", str(DEFAULT_OUTBOX)))
    parser.add_argument("--state", default=os.environ.get("AGENTHUB_BRIDGE_STATE", str(DEFAULT_STATE)))
    parser.add_argument("--timeout", type=float, default=30.0)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("sessions")
    poll = sub.add_parser("poll")
    poll.add_argument("--limit", type=int, default=20)
    poll.add_argument("--watch", action="store_true")
    poll.add_argument("--poll-seconds", type=float, default=5.0)
    poll.add_argument("--session-id", default=argparse.SUPPRESS)

    reply = sub.add_parser("reply")
    reply.add_argument("--session-id", default=argparse.SUPPRESS)
    reply.add_argument("--content", default="")
    reply.add_argument("--file", default="")
    reply.add_argument("--task-id", default="")
    reply.add_argument("--in-reply-to", default="")

    thread_tree = sub.add_parser("thread-tree")
    thread_tree.add_argument("--refresh", action="store_true")

    sub.add_parser("discover-thread-tree")
    sub.add_parser("capabilities")

    dry_run = sub.add_parser("dry-run-send")
    dry_run.add_argument("--session-id", default=argparse.SUPPRESS)
    dry_run.add_argument("--thread-ref", required=True)
    dry_run.add_argument("--message", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "sessions":
        return cmd_sessions(args)
    if args.command == "poll":
        return cmd_poll(args)
    if args.command == "reply":
        return cmd_reply(args)
    if args.command == "discover-thread-tree":
        return cmd_discover_thread_tree(args)
    if args.command == "capabilities":
        return cmd_capabilities(args)
    if args.command == "thread-tree":
        return cmd_thread_tree(args)
    if args.command == "dry-run-send":
        return cmd_dry_run_send(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
