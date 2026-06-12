from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.backend import app as backend


def write_json(root: Path, relative: str, payload: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def read_ndjson(root: Path, relative: str) -> list[dict]:
    path = root / relative
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def mcp_tool_payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


class AgentHubDispatchContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_agenthub_dir = os.environ.get("AGENTHUB_DIR")
        os.environ["AGENTHUB_DIR"] = str(self.root)
        write_json(
            self.root,
            "coordination/AGENT_REGISTRY.json",
            {
                "version": "1.0",
                "items": [
                    {"agent_id": "windows-api-codex-app-agent", "name": "Windows API Codex App Agent", "agent_type": "codex-app"},
                    {"agent_id": "windows-gpt-codex-app-agent", "name": "Windows GPT Codex App Agent", "agent_type": "codex-app"},
                    {"agent_id": "ubuntu-codex-cli-agent", "name": "Ubuntu Codex CLI Agent", "agent_type": "codex-cli"},
                    {"agent_id": "openclaw-agent", "name": "OpenClaw 微信入口 Agent", "agent_type": "wechat-bridge"},
                ],
            },
        )
        write_json(
            self.root,
            "coordination/SESSION_REGISTRY.json",
            {
                "version": "1.0",
                "items": [
                    {
                        "session_id": "session-win-api-agenthub-001",
                        "agent_id": "windows-api-codex-app-agent",
                        "display_name": "Windows API Codex App / AgentHub 总控开发会话",
                        "project_id": "agenthub",
                        "codex_client": "codex-app",
                    },
                    {
                        "session_id": "session-win-gpt-agenthub-001",
                        "agent_id": "windows-gpt-codex-app-agent",
                        "display_name": "Windows GPT Codex App / AgentHub 辅助会话",
                        "project_id": "agenthub",
                        "codex_client": "codex-app",
                    },
                    {
                        "session_id": "session-ubuntu-agenthub-001",
                        "agent_id": "ubuntu-codex-cli-agent",
                        "display_name": "Ubuntu Codex CLI / AgentHub 开发会话",
                        "project_id": "agenthub",
                        "codex_client": "codex-cli",
                    },
                    {
                        "session_id": "session-openclaw-wechat-001",
                        "agent_id": "openclaw-agent",
                        "display_name": "OpenClaw 微信入口 / AgentHub 转发会话",
                        "project_id": "openclaw",
                        "codex_client": "openclaw-bridge",
                    },
                ],
            },
        )
        write_json(self.root, "coordination/TASK_BOARD.json", {"version": "1.0", "items": []})

    def tearDown(self) -> None:
        if self.old_agenthub_dir is None:
            os.environ.pop("AGENTHUB_DIR", None)
        else:
            os.environ["AGENTHUB_DIR"] = self.old_agenthub_dir
        self.tmp.cleanup()

    def test_mcp_tool_registry_exposes_task_room_supervisor_and_attachment_tools(self) -> None:
        init = backend.handle_mcp_rpc(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }
        )
        self.assertEqual(init["result"]["serverInfo"]["version"], backend.AGENTHUB_MCP_SERVER_VERSION)
        self.assertTrue(init["result"]["capabilities"]["tools"]["listChanged"])

        response = backend.handle_mcp_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}

        self.assertIn("list_task_rooms", names)
        self.assertIn("create_task_room", names)
        self.assertIn("send_task_room_message", names)
        self.assertIn("supervisor_dispatch", names)
        self.assertIn("upload_attachment", names)

        send_tool = next(tool for tool in tools if tool["name"] == "send_task_room_message")
        supervisor_tool = next(tool for tool in tools if tool["name"] == "supervisor_dispatch")
        self.assertIn("attachments", send_tool["inputSchema"]["properties"])
        self.assertIn("attachment_ids", send_tool["inputSchema"]["properties"])
        self.assertIn("attachments", supervisor_tool["inputSchema"]["properties"])
        self.assertIn("attachment_ids", supervisor_tool["inputSchema"]["properties"])

    def test_supervisor_mention_creates_real_supervisor_and_routes_to_windows_api(self) -> None:
        result = backend.agenthub_dispatch_chat_message(
            self.root,
            "@主管 帮我把这个项目交给 @windows-api-codex",
            sender_id="user",
            room_id="taskroom-contract",
        )

        sessions = read_json(self.root, "coordination/SESSION_REGISTRY.json")["items"]
        self.assertTrue(any(item["session_id"] == "session-supervisor-main-001" for item in sessions))
        self.assertIn("session-win-api-agenthub-001", [item["session_id"] for item in result["routed_to"]])
        tasks = read_json(self.root, "coordination/TASK_BOARD.json")["items"]
        self.assertTrue(any(item["assigned_agent"] == "windows-api-codex-app-agent" for item in tasks))

    def test_openclaw_mention_routes_to_openclaw_session(self) -> None:
        result = backend.agenthub_dispatch_chat_message(
            self.root,
            "@openclaw 把这条任务转发给微信入口",
            sender_id="user",
            room_id="taskroom-contract",
        )

        self.assertIn("session-openclaw-wechat-001", [item["session_id"] for item in result["routed_to"]])
        session_rows = read_ndjson(self.root, "logs/SESSION_MESSAGES.ndjson")
        self.assertTrue(any(row["session_id"] == "session-openclaw-wechat-001" for row in session_rows))

    def test_task_room_message_is_persisted_with_mentions_and_routes(self) -> None:
        room = backend.agenthub_create_task_room(self.root, "多 Agent 验收", participants=["supervisor-agent"])
        result = backend.agenthub_dispatch_chat_message(
            self.root,
            "@session-ubuntu-agenthub-001 做一次测试",
            sender_id="user",
            room_id=room["room_id"],
        )

        rooms = read_json(self.root, "coordination/TASK_ROOMS.json")["items"]
        self.assertTrue(any(item["room_id"] == room["room_id"] for item in rooms))
        room_rows = read_ndjson(self.root, "logs/TASK_ROOM_MESSAGES.ndjson")
        self.assertEqual(room_rows[-1]["room_id"], room["room_id"])
        self.assertIn("@session-ubuntu-agenthub-001", room_rows[-1]["mentions"])
        self.assertIn("session-ubuntu-agenthub-001", [item["session_id"] for item in result["routed_to"]])

    def test_attachments_are_written_into_message_protocol(self) -> None:
        attachment = backend.agenthub_store_attachment(
            self.root,
            filename="note.txt",
            content=b"hello",
            mime="text/plain",
        )
        result = backend.agenthub_dispatch_chat_message(
            self.root,
            "@session-win-gpt-agenthub-001 看附件",
            sender_id="user",
            room_id="taskroom-contract",
            attachments=[attachment],
        )

        self.assertEqual(result["attachments"][0]["filename"], "note.txt")
        attachment_registry = read_json(self.root, "coordination/ATTACHMENTS.json")["items"]
        self.assertTrue(any(item["attachment_id"] == attachment["attachment_id"] for item in attachment_registry))
        session_rows = read_ndjson(self.root, "logs/SESSION_MESSAGES.ndjson")
        self.assertEqual(session_rows[-1]["attachments"][0]["attachment_id"], attachment["attachment_id"])

    def test_mcp_can_upload_attachment_id_and_supervisor_dispatch_to_ubuntu_session(self) -> None:
        upload_response = backend.handle_mcp_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "upload_attachment",
                    "arguments": {"filename": "test.txt", "mime": "text/plain", "content": "hello from mcp"},
                },
            }
        )
        attachment = mcp_tool_payload(upload_response)["attachment"]

        room_response = backend.handle_mcp_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "create_task_room", "arguments": {"title": "测试主管调度 OpenClaw"}},
            }
        )
        room = mcp_tool_payload(room_response)["room"]

        dispatch_response = backend.handle_mcp_rpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "supervisor_dispatch",
                    "arguments": {
                        "room_id": room["room_id"],
                        "message": "@主管 请把这个附件交给 @ubuntu-codex-cli，只做路由测试，不需要实际执行。",
                        "attachment_ids": [attachment["attachment_id"]],
                    },
                },
            }
        )
        result = mcp_tool_payload(dispatch_response)

        self.assertTrue((self.root / attachment["path"]).exists())
        self.assertIn("session-ubuntu-agenthub-001", [item["session_id"] for item in result["routed_to"]])

        room_rows = read_ndjson(self.root, "logs/TASK_ROOM_MESSAGES.ndjson")
        self.assertEqual(room_rows[-1]["attachments"][0]["attachment_id"], attachment["attachment_id"])

        session_rows = read_ndjson(self.root, "logs/SESSION_MESSAGES.ndjson")
        self.assertTrue(
            any(
                row["session_id"] == "session-ubuntu-agenthub-001"
                and row["attachments"]
                and row["attachments"][0]["attachment_id"] == attachment["attachment_id"]
                for row in session_rows
            )
        )

    def test_sidebar_tree_contains_agent_folder_session_and_task_rooms(self) -> None:
        backend.agenthub_create_task_room(self.root, "树状房间", participants=["supervisor-agent"])
        tree = backend.agenthub_build_sidebar_tree(self.root)

        api_agent = next(item for item in tree["items"] if item["id"] == "windows-api-codex-app-agent")
        self.assertTrue(any(child["type"] == "folder" and child["label"] == "AgentHub" for child in api_agent["children"]))
        rooms = next(item for item in tree["items"] if item["id"] == "task-rooms")
        self.assertTrue(any(child["type"] == "task-room" for child in rooms["children"]))


if __name__ == "__main__":
    unittest.main()
