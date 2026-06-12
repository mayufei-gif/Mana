from __future__ import annotations

import unittest
from pathlib import Path

from codex_app_discovery import capabilities, dry_run_send, generate_discovery_files, load_thread_bindings, load_thread_tree


SCRIPT_DIR = Path(__file__).resolve().parent
AGENTHUB_ROOT = SCRIPT_DIR.parent.parent
CODEX_ROOT = Path.home() / ".codex"


class WindowsCodexAppDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = generate_discovery_files(CODEX_ROOT, AGENTHUB_ROOT)
        cls.tree = load_thread_tree(AGENTHUB_ROOT)
        cls.bindings = load_thread_bindings(AGENTHUB_ROOT)
        cls.caps = capabilities(AGENTHUB_ROOT)

    def test_red_app_server_url_is_not_usable_when_port_is_not_listening(self) -> None:
        self.assertEqual(self.caps.get("app_server_url"), "ws://127.0.0.1:19682")
        self.assertFalse(self.caps.get("app_server_listening"))
        self.assertNotEqual(self.caps.get("delivery_method"), "app-server")

    def test_red_default_bridge_context_is_not_enough_for_full_thread_mapping(self) -> None:
        self.assertEqual(self.caps.get("app_thread_context_count"), 1)
        bridge_status = self.tree.get("bridge_status") or {}
        self.assertEqual(list((bridge_status.get("appThreadContexts") or {}).keys()), ["default"])

    def test_green_thread_tree_and_candidate_bindings_exist(self) -> None:
        self.assertTrue(Path(self.discovery["thread_tree_path"]).exists())
        self.assertTrue(Path(self.discovery["thread_bindings_path"]).exists())
        self.assertGreater(self.discovery.get("thread_count", 0), 0)
        folders = self.tree.get("windows_api_codex_app", {}).get("folders", [])
        self.assertEqual(len(folders), 1)
        self.assertEqual(folders[0].get("folder_name"), "微信直连codex")
        bindings = self.bindings.get("bindings") or []
        self.assertGreaterEqual(len(bindings), 2)
        self.assertTrue(all(item.get("bind_status") in {"candidate", "folder_candidate"} for item in bindings))
        self.assertFalse(any(item.get("thread_ref") == self.caps.get("active_thread_ref") for item in bindings))

    def test_green_dry_run_returns_routing_shape_without_sending(self) -> None:
        binding = next(item for item in self.bindings.get("bindings", []) if item.get("session_id") == "session-win-api-agenthub-001")
        thread_ref = binding["candidate_threads"][0]["thread_ref"]
        result = dry_run_send(
            AGENTHUB_ROOT,
            session_id=binding["session_id"],
            thread_ref=thread_ref,
            message="AgentHub 1F dry-run 测试，不要真实投递",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "dry-run")
        self.assertIn("would_send_to", result)
        self.assertIn("delivery_method", result)
        self.assertIn("can_send", result)
        self.assertIn("can_read_reply", result)
        self.assertIn("risk_level", result)
        self.assertFalse(result.get("can_send"))


if __name__ == "__main__":
    unittest.main()
