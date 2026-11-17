"""
DAKU Automated Test Suite for DeepSeek Harness Bridge & Plugin Architecture
Tests:
1. Cordis Plugin Manifest generation and category mapping
2. Tool schema generation for DeepSeek function calling
3. Multi-turn session state with monotonic append-only event logging
4. Event log bounded memory limits
5. 3-Tier security gate dispatch: SAFE, CONFIRMATION_REQUIRED, and BLOCKED
6. <think> reasoning trace extraction and voice output sanitization
7. DeepSeekHarnessBackend integration with DeepSeekHarnessBridge
8. Telemetry snapshot and Solar Swarm HUD endpoint sync
9. Memory footprint verification (< 25 MB)
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.backend import DeepSeekHarnessBackend
from brain.deepseek_harness_bridge import (
    DeepSeekHarnessBridge,
    HarnessCommandResult,
    HarnessPluginManifest,
    HarnessSession,
    MAX_SESSION_EVENTS,
)
from config.settings import settings
from tools.base import PermissionLevel
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry


class TestDeepSeekHarnessBridge(unittest.TestCase):
    """Test suite for DAKU's DeepSeek Harness Cordis plugin adapter and bridge."""

    def setUp(self):
        self.perm_manager = PermissionManager(auto_confirm_in_test=True)
        self.registry = ToolRegistry(permission_manager=self.perm_manager)
        self.bridge = DeepSeekHarnessBridge(
            tool_registry=self.registry,
            permission_manager=self.perm_manager,
        )

    # -------------------------------------------------------------------------
    # 1. Plugin Manifest & Schema Inspection
    # -------------------------------------------------------------------------
    def test_01_plugin_manifest_generation(self):
        """TEST 1: Verify 4 core native tools are exposed as Cordis plugin manifests."""
        manifests = self.bridge.get_plugin_manifests()
        self.assertGreaterEqual(len(manifests), 4)

        plugin_map = {m.plugin_id: m for m in manifests}
        self.assertIn("daku.plugin.application", plugin_map)
        self.assertIn("daku.plugin.browser", plugin_map)
        self.assertIn("daku.plugin.filesystem", plugin_map)
        self.assertIn("daku.plugin.system", plugin_map)

        # Verify categories
        self.assertEqual(plugin_map["daku.plugin.application"].category, "desktop-control")
        self.assertEqual(plugin_map["daku.plugin.browser"].category, "web-automation")
        self.assertEqual(plugin_map["daku.plugin.filesystem"].category, "storage")
        self.assertEqual(plugin_map["daku.plugin.system"].category, "telemetry")

    def test_02_tool_schemas_format(self):
        """TEST 2: Verify tool schemas follow OpenAI/DeepSeek function calling schema format."""
        schemas = self.bridge.get_tool_schemas()
        self.assertGreaterEqual(len(schemas), 4)
        for s in schemas:
            self.assertEqual(s.get("type"), "function")
            func = s.get("function", {})
            self.assertIn("name", func)
            self.assertIn("description", func)
            self.assertIn("parameters", func)

    # -------------------------------------------------------------------------
    # 2. Session State & Append-Only Event Log
    # -------------------------------------------------------------------------
    def test_03_session_creation_and_monotonic_event_log(self):
        """TEST 3: Verify sessions create append-only logs with monotonic sequence numbering."""
        session = self.bridge.create_session("test_session_monotonic")
        self.assertEqual(session.session_id, "test_session_monotonic")

        seq0 = session.record_event("custom/event_one", {"data": 1})
        seq1 = session.record_event("custom/event_two", {"data": 2})
        seq2 = session.record_event("custom/event_three", {"data": 3})

        self.assertLess(seq0, seq1)
        self.assertLess(seq1, seq2)

        events = session.get_events()
        self.assertGreaterEqual(len(events), 4)  # including session/created
        self.assertEqual(events[1]["type"], "custom/event_one")

    def test_04_session_event_log_bounds(self):
        """TEST 4: Verify session event log enforces bounded memory limit (MAX_SESSION_EVENTS)."""
        session = self.bridge.create_session("test_session_bounds")
        for i in range(MAX_SESSION_EVENTS + 30):
            session.record_event("load/event", {"index": i})

        self.assertLessEqual(len(session.event_log), MAX_SESSION_EVENTS)
        # Ensure initial creation event is preserved at index 0
        self.assertEqual(session.event_log[0]["type"], "session/created")

    # -------------------------------------------------------------------------
    # 3. 3-Tier Security Gate Dispatch
    # -------------------------------------------------------------------------
    def test_05_safe_tool_dispatch_and_verification(self):
        """TEST 5: Dispatching a SAFE tool executes cleanly and verifies in OS state."""
        session = self.bridge.create_session("test_session_safe")
        res = self.bridge.dispatch_tool_call("system_tool", {"query": "ram"}, session_id=session.session_id)
        self.assertEqual(res.kind, "success")
        self.assertTrue(res.verified)
        self.assertIn("RAM", res.voice_summary)
        self.assertIn("daku.plugin.system", session.active_plugins)

    def test_06_blocked_tool_dispatch(self):
        """TEST 6: Dispatching a BLOCKED operation immediately returns error and rejected outcome."""
        session = self.bridge.create_session("test_session_blocked")
        res = self.bridge.dispatch_tool_call("file_tool", {"action": "delete_file", "path": "important.txt"}, session_id=session.session_id)
        self.assertEqual(res.kind, "error")
        self.assertFalse(res.verified)
        self.assertEqual(res.outcome, "rejected")
        self.assertIn("security policy", res.voice_summary.lower())

    def test_07_confirmation_required_granted(self):
        """TEST 7: CONFIRMATION_REQUIRED action with user approval executes with allowed-once outcome."""
        pm = PermissionManager(confirmation_callback=lambda tool, desc: True)
        reg = ToolRegistry(permission_manager=pm)
        bridge = DeepSeekHarnessBridge(tool_registry=reg, permission_manager=pm)
        session = bridge.create_session("test_session_confirm_grant")

        test_file = "test_confirm_granted.txt"
        res = bridge.dispatch_tool_call("file_tool", {"action": "create_file", "path": test_file, "content": "hello"}, session_id=session.session_id)
        self.assertEqual(res.kind, "success")
        self.assertTrue(res.verified)
        self.assertEqual(res.outcome, "allowed-once")

        # Cleanup
        if os.path.exists(test_file):
            try:
                os.remove(test_file)
            except Exception:
                pass

    def test_08_confirmation_required_denied(self):
        """TEST 8: CONFIRMATION_REQUIRED action with user denial aborts execution with rejected outcome."""
        pm = PermissionManager(confirmation_callback=lambda tool, desc: False)
        reg = ToolRegistry(permission_manager=pm)
        bridge = DeepSeekHarnessBridge(tool_registry=reg, permission_manager=pm)
        session = bridge.create_session("test_session_confirm_deny")

        test_file = "test_confirm_denied.txt"
        res = bridge.dispatch_tool_call("file_tool", {"action": "create_file", "path": test_file, "content": "hello"}, session_id=session.session_id)
        self.assertEqual(res.kind, "error")
        self.assertFalse(res.verified)
        self.assertEqual(res.outcome, "rejected")
        self.assertIn("cancelled", res.voice_summary.lower())
        self.assertFalse(os.path.exists(test_file))

    # -------------------------------------------------------------------------
    # 4. Reasoning Trace Extraction & Voice Output Normalization
    # -------------------------------------------------------------------------
    def test_09_think_tag_extraction_and_voice_stripping(self):
        """TEST 9: <think> tags are extracted for telemetry and stripped from voice output."""
        session = self.bridge.create_session("test_think_session")
        raw = "<think>\n1. Plan query\n2. Call tool\n</think>\nYour system RAM is 3.4 GB."
        clean, trace = self.bridge.extract_and_route_reasoning(raw, session_id=session.session_id)

        self.assertNotIn("<think>", clean)
        self.assertNotIn("</think>", clean)
        self.assertIn("Your system RAM is 3.4 GB", clean)
        self.assertIn("Plan query", trace)
        self.assertEqual(session.last_think_trace, trace)

    def test_10_unclosed_think_tag_handling(self):
        """TEST 10: Unclosed <think> tag from stream truncation is handled gracefully."""
        session = self.bridge.create_session("test_unclosed_think")
        raw = "Partial greeting before <think>Model reasoning incomplete..."
        clean, trace = self.bridge.extract_and_route_reasoning(raw, session_id=session.session_id)

        self.assertNotIn("<think>", clean)
        self.assertIn("Model reasoning incomplete", trace)
        self.assertEqual(clean, "Partial greeting before")

    # -------------------------------------------------------------------------
    # 5. Backend & Telemetry Integration
    # -------------------------------------------------------------------------
    def test_11_backend_integration_with_bridge(self):
        """TEST 11: DeepSeekHarnessBackend initializes with DeepSeekHarnessBridge and session."""
        backend = DeepSeekHarnessBackend(tool_registry=self.registry, bridge=self.bridge)
        self.assertEqual(backend.get_name(), "DeepSeekHarnessBackend")
        self.assertTrue(backend.is_healthy())
        self.assertIsNotNone(backend.get_session())
        self.assertIsInstance(backend.get_telemetry(), dict)

    def test_12_backend_telemetry_snapshot(self):
        """TEST 12: Backend telemetry returns structured data for Solar Swarm HUD sync."""
        backend = DeepSeekHarnessBackend(tool_registry=self.registry, bridge=self.bridge)
        telemetry = backend.get_telemetry()

        self.assertEqual(telemetry["backend"], "DeepSeekHarnessBackend")
        self.assertEqual(telemetry["harness_status"], "ACTIVE")
        self.assertIn("session_id", telemetry)
        self.assertIn("event_count", telemetry)
        self.assertIn("pass_count", telemetry)
        self.assertIn("last_think_trace", telemetry)
        self.assertIn("active_plugins", telemetry)
        self.assertGreaterEqual(telemetry["plugin_count"], 4)

    def test_13_hud_agents_telemetry_integration(self):
        """TEST 13: GET /api/hud/agents returns harness status and mapped plugin IDs."""
        from server.daku_server import create_server
        server = create_server(host="127.0.0.1", port=18449, auth_token=None)
        server.start(blocking=False)
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:18449/api/hud/agents")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            self.assertIn("sun", data)
            self.assertIn("harness_status", data["sun"])
            self.assertIn("session_id", data["sun"])

            # Verify planetary agents have plugin_ids
            agents = {a["id"]: a for a in data.get("agents", [])}
            self.assertIn("plugin_id", agents["researcher"])
            self.assertEqual(agents["researcher"]["plugin_id"], "daku.plugin.browser")
            self.assertEqual(agents["coder"]["plugin_id"], "daku.plugin.application")
        finally:
            server.stop()

    def test_14_memory_footprint_under_limit(self):
        """TEST 14: Verifies the bridge and backend working set memory remains < 25 MB."""
        from scripts.verify_harness_live import get_process_memory_mb
        mem_mb = get_process_memory_mb()
        self.assertLess(mem_mb, 25.0)


if __name__ == "__main__":
    unittest.main()
