from __future__ import annotations

import json
import os
import socket
import sqlite3
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse


THREAD_TREE_PATH = Path("coordination/CODEX_APP_THREAD_TREE.json")
THREAD_BINDINGS_PATH = Path("coordination/CODEX_APP_THREAD_BINDINGS.json")
DEFAULT_BRIDGE_STATUS_URL = "http://127.0.0.1:19577/status"
WINDOWS_CODEX_AGENT_IDS = {"windows-api-codex-app-agent", "windows-gpt-codex-app-agent"}
DEFAULT_TARGET_WORKSPACE = "G:\\E盘\\工作项目文件\\NAS\\微信直连codex"
DEFAULT_TEST_THREAD_TITLE = "AgentHub 1F 真实投递测试"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def iso_from_epoch(value: int | float | None) -> str:
    if not value:
        return ""
    raw = float(value)
    if raw > 10_000_000_000:
        raw = raw / 1000
    return datetime.fromtimestamp(raw, timezone.utc).astimezone().isoformat(timespec="seconds")


def scrub_text(value: object, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def normalized_title(value: object) -> str:
    return "".join(str(value or "").lower().split())


def test_thread_title() -> str:
    return str(os.environ.get("CODEX_APP_TEST_THREAD_TITLE") or DEFAULT_TEST_THREAD_TITLE).strip()


def title_match_score(title: object, target: str) -> float:
    left = normalized_title(title)
    right = normalized_title(target)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if right in left or left in right:
        return 0.95
    return SequenceMatcher(None, left, right).ratio()


def title_confidence(title: object, target: str) -> tuple[str, float, bool]:
    score = title_match_score(title, target)
    if score >= 0.95:
        return "high", score, True
    if score >= 0.82:
        return "medium", score, False
    return "folder", score, False


def clean_windows_path(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return text.replace("/", "\\").rstrip("\\")


def path_key(value: object) -> str:
    return clean_windows_path(value).casefold()


def folder_name_from_path(value: object) -> str:
    cleaned = clean_windows_path(value)
    if not cleaned:
        return "未绑定工作区"
    name = cleaned.split("\\")[-1] or cleaned
    if name.casefold() == "nasagenthub":
        return "AgentHub"
    return name


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


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
        thread_id = str(item.get("id") or "")
        if thread_id:
            rows[thread_id] = item
    return rows


def sqlite_tables(db_path: Path) -> list[str]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("select name from sqlite_master where type='table' order by name").fetchall()
    finally:
        con.close()
    return [str(row[0]) for row in rows]


def load_threads(codex_root: Path) -> list[dict]:
    db_path = codex_root / "state_5.sqlite"
    if not db_path.exists():
        return []
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in con.execute("pragma table_info(threads)").fetchall()}
        wanted = [
            "id",
            "rollout_path",
            "created_at",
            "updated_at",
            "created_at_ms",
            "updated_at_ms",
            "source",
            "thread_source",
            "cwd",
            "title",
            "preview",
            "first_user_message",
            "agent_nickname",
            "agent_role",
            "agent_path",
            "tokens_used",
            "archived",
        ]
        selected = [name for name in wanted if name in columns]
        rows = con.execute(
            f"""
            select {", ".join(selected)}
            from threads
            order by coalesce(updated_at_ms, updated_at, created_at_ms, created_at) desc
            """
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def message_count_from_rollout(raw_path: object) -> int:
    if not raw_path:
        return 0
    path = Path(str(raw_path))
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = obj.get("payload")
        if isinstance(payload, dict) and payload.get("type") in {"user_message", "agent_message"}:
            count += 1
    return count


def load_bridge_status(url: str = DEFAULT_BRIDGE_STATUS_URL, timeout: float = 3.0) -> dict:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
        if isinstance(payload, dict):
            payload.setdefault("http_status", 200)
            return payload
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}
    return {"ok": False, "error": "Bridge status response is not an object", "url": url}


def can_connect_tcp(url: str, timeout: float = 0.5) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def workspace_roots_from_global_state(global_state: dict) -> list[str]:
    roots: list[str] = []
    for key in ("electron-saved-workspace-roots", "project-order", "active-workspace-roots"):
        value = global_state.get(key)
        if isinstance(value, list):
            roots.extend(str(item) for item in value if item)
    deduped: list[str] = []
    seen: set[str] = set()
    for root in roots:
        key = path_key(root)
        if key and key not in seen:
            seen.add(key)
            deduped.append(clean_windows_path(root))
    return deduped


def thread_workspace(row: dict, global_state: dict) -> str:
    cwd = clean_windows_path(row.get("cwd"))
    if cwd:
        return cwd
    hints = global_state.get("thread-workspace-root-hints")
    if isinstance(hints, dict):
        return clean_windows_path(hints.get(str(row.get("id") or "")))
    return ""


def best_folder_name(workspace: str, roots: list[str]) -> str:
    current = path_key(workspace)
    best = ""
    for root in roots:
        key = path_key(root)
        if key and (current == key or current.startswith(key + "\\")):
            if len(key) > len(path_key(best)):
                best = root
    return folder_name_from_path(best or workspace)


def session_items(agenthub_root: Path) -> list[dict]:
    data = load_json(agenthub_root / "coordination" / "SESSION_REGISTRY.json", {"items": []})
    return list(data.get("items") or [])


def windows_codex_sessions(agenthub_root: Path) -> list[dict]:
    items = []
    for item in session_items(agenthub_root):
        if item.get("agent_id") in WINDOWS_CODEX_AGENT_IDS:
            items.append(item)
    return items


def candidate_sessions_for_workspace(workspace: str, sessions: list[dict]) -> list[str]:
    current = path_key(workspace)
    matches: list[str] = []
    for item in sessions:
        session_workspace = item.get("workspace_path_windows") or ""
        key = path_key(session_workspace)
        if key and current and (current == key or current.startswith(key + "\\")):
            session_id = str(item.get("session_id") or "")
            if session_id:
                matches.append(session_id)
    return matches


def bridge_contexts_by_thread(bridge_status: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    contexts = bridge_status.get("appThreadContexts")
    if not isinstance(contexts, dict):
        return result
    for key, value in contexts.items():
        if isinstance(value, dict):
            thread_id = str(value.get("threadId") or "")
            if thread_id:
                result.setdefault(thread_id, []).append(str(key))
    return result


def target_workspace() -> str:
    return clean_windows_path(os.environ.get("CODEX_APP_TARGET_WORKSPACE") or DEFAULT_TARGET_WORKSPACE)


def is_target_workspace(workspace: str, target: str) -> bool:
    current = path_key(workspace)
    wanted = path_key(target)
    return bool(current and wanted and (current == wanted or current.startswith(wanted + "\\")))


def build_folder_tree(threads: list[dict], session_index: dict[str, dict], global_state: dict, sessions: list[dict], bridge_status: dict) -> list[dict]:
    roots = workspace_roots_from_global_state(global_state)
    context_map = bridge_contexts_by_thread(bridge_status)
    target = target_workspace()
    test_title = test_thread_title()
    folders: dict[tuple[str, str], dict] = {}
    for row in threads:
        thread_id = str(row.get("id") or "")
        if not thread_id:
            continue
        workspace = thread_workspace(row, global_state)
        if not is_target_workspace(workspace, target):
            continue
        folder_name = best_folder_name(workspace, roots)
        key = (folder_name, path_key(workspace))
        folder = folders.setdefault(
            key,
            {
                "folder_name": folder_name,
                "workspace_path": workspace,
                "account_source": "unknown",
                "threads": [],
            },
        )
        index_row = session_index.get(thread_id, {})
        candidate_session_ids = candidate_sessions_for_workspace(workspace, sessions)
        updated_value = row.get("updated_at_ms") or row.get("updated_at")
        title = scrub_text(row.get("title") or index_row.get("thread_name") or row.get("first_user_message") or thread_id, 180)
        confidence, match_score, exact_or_high = title_confidence(title, test_title)
        folder["threads"].append(
            {
                "thread_id": thread_id,
                "thread_ref": thread_id,
                "title": title,
                "last_updated": iso_from_epoch(updated_value),
                "workspace_path": workspace,
                "candidate_session_id": candidate_session_ids[0] if len(candidate_session_ids) == 1 else "",
                "candidate_session_ids": candidate_session_ids,
                "account_source": "unknown",
                "bridge_context_keys": context_map.get(thread_id, []),
                "archived": bool(row.get("archived")),
                "source": row.get("source") or "",
                "thread_source": row.get("thread_source") or "",
                "preview": scrub_text(row.get("preview") or row.get("first_user_message") or "", 240),
                "rollout_path": clean_windows_path(row.get("rollout_path")),
                "message_count": message_count_from_rollout(row.get("rollout_path")),
                "confidence": confidence,
                "title_match_score": round(match_score, 4),
                "matched_test_title": exact_or_high,
            }
        )
    folder_list = list(folders.values())
    for folder in folder_list:
        folder["threads"].sort(key=lambda item: item.get("last_updated") or "", reverse=True)
    folder_list.sort(key=lambda item: (item.get("folder_name") or "", item.get("workspace_path") or ""))
    return folder_list


def folder_candidate_threads(folders: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for folder in folders:
        for thread in folder.get("threads", []) or []:
            candidates.append(
                {
                    "thread_ref": thread.get("thread_ref") or "",
                    "thread_title": thread.get("title") or "",
                    "folder_name": folder.get("folder_name") or "",
                    "workspace_path": thread.get("workspace_path") or "",
                    "last_updated": thread.get("last_updated") or "",
                    "message_count": thread.get("message_count") or 0,
                    "confidence": thread.get("confidence") or "folder",
                    "title_match_score": thread.get("title_match_score") or 0,
                    "matched_test_title": bool(thread.get("matched_test_title")),
                    "account_source": thread.get("account_source") or "unknown",
                    "is_default_thread": "default" in (thread.get("bridge_context_keys") or []),
                }
            )
    return candidates


def unique_test_thread_candidate(folders: list[dict]) -> tuple[dict | None, str]:
    matches: list[dict] = []
    for folder in folders:
        for thread in folder.get("threads", []) or []:
            if thread.get("matched_test_title") and not thread.get("archived"):
                matches.append(thread | {"folder_name": folder.get("folder_name") or ""})
    if len(matches) == 1:
        return matches[0], f"标题精确或高相似匹配 {test_thread_title()}，等待用户确认后才可 active"
    if len(matches) > 1:
        return None, f"发现 {len(matches)} 个高相似测试会话，需用户手动选择 thread_ref"
    return None, f"未发现标题匹配 {test_thread_title()} 的测试会话"


def choose_binding_candidate(session: dict, folders: list[dict], bridge_status: dict) -> tuple[dict | None, str, str]:
    if session.get("agent_id") == "windows-api-codex-app-agent":
        test_candidate, test_note = unique_test_thread_candidate(folders)
        if test_candidate:
            return test_candidate, "high", test_note
    session_workspace = clean_windows_path(session.get("workspace_path_windows"))
    best: dict | None = None
    confidence = "low"
    note = "未找到可自动绑定的真实 Codex App thread，等待用户手动指定 thread_ref"
    if session_workspace:
        for folder in folders:
            for thread in folder.get("threads", []):
                workspace = clean_windows_path(thread.get("workspace_path"))
                if path_key(workspace) == path_key(session_workspace):
                    return thread | {"folder_name": folder.get("folder_name") or ""}, "high", "workspace_path_windows 与 Codex thread cwd 完全匹配"
                if path_key(workspace).startswith(path_key(session_workspace) + "\\"):
                    best = thread | {"folder_name": folder.get("folder_name") or ""}
                    confidence = "medium"
                    note = "Codex thread cwd 位于 session workspace_path_windows 下"
    return best, confidence, note


def build_bindings(agenthub_root: Path, folders: list[dict], bridge_status: dict) -> dict:
    bindings = []
    folder_threads = folder_candidate_threads(folders)
    target = target_workspace()
    for session in windows_codex_sessions(agenthub_root):
        candidate, confidence, note = choose_binding_candidate(session, folders, bridge_status)
        binding = {
            "agent_id": session.get("agent_id") or "",
            "session_id": session.get("session_id") or "",
            "thread_ref": "",
            "workspace_path_windows": target,
            "folder_name": folder_name_from_path(target),
            "thread_title": "",
            "bind_status": "folder_candidate",
            "binding_scope": "folder",
            "confidence": "medium" if folder_threads else confidence,
            "account_source": "unknown",
            "candidate_threads": folder_threads,
            "notes": "按用户要求，只绑定微信直连codex文件夹内的真实 Codex App 对话；等待用户从 candidate_threads 中明确选择 thread_ref",
        }
        if candidate:
            binding.update(
                {
                    "thread_ref": candidate.get("thread_ref") or "",
                    "folder_name": candidate.get("folder_name") or "",
                    "thread_title": candidate.get("title") or "",
                    "bind_status": "candidate",
                    "binding_scope": "thread",
                    "confidence": confidence,
                    "notes": note,
                }
            )
        bindings.append(binding)
    return {
        "version": "1.0",
        "updated_at": now_iso(),
        "source": "codex_app_discovery",
        "bindings": bindings,
    }


def build_thread_tree(codex_root: Path, agenthub_root: Path, bridge_status_url: str = DEFAULT_BRIDGE_STATUS_URL) -> tuple[dict, dict]:
    codex_root = codex_root.expanduser()
    agenthub_root = agenthub_root.expanduser()
    db_path = codex_root / "state_5.sqlite"
    global_state_path = codex_root / ".codex-global-state.json"
    global_state = load_json(global_state_path, {})
    session_index = load_session_index(codex_root)
    bridge_status = load_bridge_status(bridge_status_url)
    threads = load_threads(codex_root)
    sessions = windows_codex_sessions(agenthub_root)
    folders = build_folder_tree(threads, session_index, global_state, sessions, bridge_status)
    table_names = sqlite_tables(db_path)
    payload = {
        "version": "1.0",
        "updated_at": now_iso(),
        "source": "state_5.sqlite + codex global state + session_index.jsonl + bridge status",
        "codex_root": str(codex_root),
        "state_db": str(db_path),
        "global_state_path": str(global_state_path),
        "sources_read": {
            "sqlite_tables": table_names,
            "global_state_keys": sorted(global_state.keys()),
            "session_index_exists": (codex_root / "session_index.jsonl").exists(),
            "bridge_status_url": bridge_status_url,
            "app_thread_context_count": len(bridge_status.get("appThreadContexts") or {}),
        },
        "source_limits": {
            "account_source": "unknown",
            "api_vs_gpt_account_distinction": "not_available_in_local_state",
            "target_workspace": target_workspace(),
            "test_thread_title": test_thread_title(),
            "notes": "本地 Codex App 状态可列出真实 thread/cwd/title。本阶段按用户要求仅输出微信直连codex文件夹；未发现可可靠区分 API 账号与 GPT 账号的字段。",
        },
        "bridge_status": {
            "ok": bool(bridge_status.get("ok")),
            "activeAppThreadKey": bridge_status.get("activeAppThreadKey") or "",
            "appThreadId": bridge_status.get("appThreadId") or "",
            "appThreadContexts": bridge_status.get("appThreadContexts") or {},
            "appServerUrl": bridge_status.get("appServerUrl") or "",
            "appIpcEnabled": bool(bridge_status.get("appIpcEnabled")),
            "appIpcPipe": bridge_status.get("appIpcPipe") or "",
            "queued": bridge_status.get("queued"),
        },
        "windows_api_codex_app": {
            "account_source": "unknown",
            "folders": folders,
            "notes": "这些是真实本机 Codex App thread 候选池；账号来源未知，不能视为 API Agent 已接管。",
        },
        "windows_gpt_codex_app": {
            "account_source": "unknown",
            "folders": [],
            "notes": "未发现可将本地 thread 明确归属为 GPT 账号 Codex App 的可靠字段。",
        },
    }
    bindings = build_bindings(agenthub_root, folders, bridge_status)
    return payload, bindings


def generate_discovery_files(codex_root: Path, agenthub_root: Path, bridge_status_url: str = DEFAULT_BRIDGE_STATUS_URL) -> dict:
    tree, bindings = build_thread_tree(codex_root, agenthub_root, bridge_status_url)
    tree_path = agenthub_root / THREAD_TREE_PATH
    bindings_path = agenthub_root / THREAD_BINDINGS_PATH
    atomic_write_json(tree_path, tree)
    atomic_write_json(bindings_path, bindings)
    return {
        "ok": True,
        "mode": "discovery",
        "thread_tree_path": str(tree_path),
        "thread_bindings_path": str(bindings_path),
        "folder_count": len(tree.get("windows_api_codex_app", {}).get("folders", [])),
        "thread_count": sum(len(folder.get("threads", [])) for folder in tree.get("windows_api_codex_app", {}).get("folders", [])),
        "binding_count": len(bindings.get("bindings", [])),
        "account_source": "unknown",
    }


def load_thread_tree(agenthub_root: Path) -> dict:
    return load_json(agenthub_root / THREAD_TREE_PATH, {})


def load_thread_bindings(agenthub_root: Path) -> dict:
    return load_json(agenthub_root / THREAD_BINDINGS_PATH, {"bindings": []})


def find_thread(tree: dict, thread_ref: str) -> tuple[dict | None, dict | None]:
    for section in ("windows_api_codex_app", "windows_gpt_codex_app"):
        for folder in tree.get(section, {}).get("folders", []) or []:
            for thread in folder.get("threads", []) or []:
                if thread.get("thread_ref") == thread_ref or thread.get("thread_id") == thread_ref:
                    return folder, thread
    return None, None


def delivery_capabilities(bridge_status: dict) -> dict:
    app_server_url = str(bridge_status.get("appServerUrl") or "")
    app_server_listening = can_connect_tcp(app_server_url)
    ipc_pipe = str(bridge_status.get("appIpcPipe") or "")
    ipc_advertised = bool(bridge_status.get("appIpcEnabled") and ipc_pipe)
    if app_server_listening:
        delivery_method = "app-server"
    elif ipc_advertised:
        delivery_method = "app-ipc-pipe"
    else:
        delivery_method = "unsupported"
    return {
        "ok": True,
        "mode": "capabilities",
        "bridge_status_ok": bool(bridge_status.get("ok")),
        "app_server_url": app_server_url,
        "app_server_listening": app_server_listening,
        "app_ipc_enabled": bool(bridge_status.get("appIpcEnabled")),
        "app_ipc_pipe": ipc_pipe,
        "app_ipc_protocol_known": False,
        "delivery_method": delivery_method,
        "can_send": False,
        "can_read_reply": False,
        "risk_level": "high" if delivery_method != "unsupported" else "medium",
        "note": "仅发现本地能力线索，尚未确认 Codex App app-server/thread 或 IPC 协议；不会真实投递。",
    }


def capabilities(agenthub_root: Path, bridge_status_url: str = DEFAULT_BRIDGE_STATUS_URL) -> dict:
    bridge_status = load_bridge_status(bridge_status_url)
    result = delivery_capabilities(bridge_status)
    result["thread_tree_exists"] = (agenthub_root / THREAD_TREE_PATH).exists()
    result["thread_bindings_exists"] = (agenthub_root / THREAD_BINDINGS_PATH).exists()
    result["active_thread_ref"] = bridge_status.get("appThreadId") or ""
    result["app_thread_context_count"] = len(bridge_status.get("appThreadContexts") or {})
    return result


def dry_run_send(agenthub_root: Path, session_id: str, thread_ref: str, message: str, bridge_status_url: str = DEFAULT_BRIDGE_STATUS_URL) -> dict:
    tree = load_thread_tree(agenthub_root)
    bindings = load_thread_bindings(agenthub_root).get("bindings", [])
    bridge_status = load_bridge_status(bridge_status_url)
    caps = delivery_capabilities(bridge_status)
    folder, thread = find_thread(tree, thread_ref)
    binding = next((item for item in bindings if item.get("session_id") == session_id), None)
    would_send_to = {
        "agent_id": (binding or {}).get("agent_id", ""),
        "session_id": session_id,
        "thread_ref": thread_ref,
        "folder_name": (folder or {}).get("folder_name", ""),
        "thread_title": (thread or {}).get("title", ""),
        "workspace_path": (thread or {}).get("workspace_path", ""),
        "bind_status": (binding or {}).get("bind_status", "unknown"),
        "confidence": (binding or {}).get("confidence", "unknown"),
    }
    note_parts = ["未真实投递。"]
    if not thread:
        note_parts.append("thread_ref 未在 CODEX_APP_THREAD_TREE.json 中找到。")
    if not binding or binding.get("thread_ref") != thread_ref:
        note_parts.append("session_id 与 thread_ref 尚未形成 active 绑定。")
    if caps["delivery_method"] == "app-server" and not caps["can_send"]:
        note_parts.append("app-server 端口可探测，但 thread API 协议未确认。")
    elif caps["delivery_method"] == "app-ipc-pipe":
        note_parts.append("只看到 IPC 管道线索，协议未知，不能写入用户消息。")
    else:
        note_parts.append("没有可用 app-server/thread 投递能力。")
    return {
        "ok": True,
        "mode": "dry-run",
        "would_send_to": would_send_to,
        "message_preview": scrub_text(message, 160),
        "delivery_method": caps["delivery_method"],
        "can_send": False,
        "can_read_reply": False,
        "risk_level": "high" if not thread or not binding or caps["delivery_method"] != "unsupported" else "medium",
        "note": " ".join(note_parts),
    }

