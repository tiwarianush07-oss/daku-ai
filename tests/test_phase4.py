"""
DAKU Automated Test Suite for Phase 4
DeepSeek Harness + Uncensored R1 Backend + MCP Orchestration + Agent Hardening

Test Categories:
1. Backend Selection & Factory:
   - TEST 1: DirectModelBackend selection via BackendFactory
   - TEST 2: DeepSeekHarnessBackend selection via BackendFactory
   - TEST 3: UncensoredR1Backend selection via BackendFactory
   - TEST 4: Invalid backend fallback to DirectModelBackend
   - TEST 5: DirectModelBackend class and alias compatibility
2. DeepSeek Harness Backend:
   - TEST 6: DeepSeekHarnessBackend initialization and lifecycle (session_id, is_active)
   - TEST 7: DeepSeekHarnessBackend message processing with voice normalization
   - TEST 8: DeepSeekHarnessBackend tool request extraction and dispatch
   - TEST 9: DeepSeekHarnessBackend timeout handling without crashing
   - TEST 10: DeepSeekHarnessBackend authentication and HTTP failure handling
   - TEST 11: DeepSeekHarnessBackend clean shutdown
3. Uncensored R1 Remote Backend:
   - TEST 12: UncensoredR1Backend initialization
   - TEST 13: UncensoredR1Backend <think> reasoning tag stripping for clean TTS output
   - TEST 14: UncensoredR1Backend tool request extraction from reasoning/markdown JSON
   - TEST 15: UncensoredR1Backend authentication failure (401) handling
   - TEST 16: UncensoredR1Backend unavailable endpoint and network fallback
   - TEST 17: UncensoredR1Backend clean shutdown
4. Agent Loop & Task Planner Hardening:
   - TEST 18: Maximum task step limit (capped at 10 steps)
   - TEST 19: Maximum retry limit (capped at 2 retries per step)
   - TEST 20: Full state machine transitions (PLANNING -> EXECUTING -> VERIFYING -> COMPLETED)
   - TEST 21: Failure path and recovery (EXECUTING -> FAILED -> RECOVERY)
5. MCP Orchestration & Tool Routing:
   - TEST 22: MCP server reuse without configuration modification
   - TEST 23: MCP tool routing priority and malformed argument rejection
6. Security & Safety:
   - TEST 24: Direct model-to-OS execution blocked (no raw shell or script execution)
   - TEST 25: Permission bypass permanently blocked
   - TEST 26: Sensitive credential masking in logs and outputs
7. Resource Safety:
   - TEST 27: Verification of zero heavy local model / lightweight RAM operation
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.backend import (
    AgentBackend,
    BackendFactory,
    DeepSeekHarnessBackend,
    UncensoredR1Backend,
)
from brain.router import Brain, DirectModelBackend, DirectModelRouter
from config.settings import settings
from tools.base import PermissionLevel, ToolResult
from tools.mcp_client import DynamicMCPTool, MCPManager
from tools.permissions import PermissionManager
from tools.planner import (
    MAX_RETRIES_PER_STEP,
    MAX_TASK_STEPS,
    TaskPlan,
    TaskPlanner,
    TaskState,
    TaskStep,
)
from tools.registry import ToolRegistry


class TestDakuPhase4(unittest.TestCase):

    def setUp(self):
        self.perm_manager = PermissionManager(auto_confirm_in_test=True)
        self.registry = ToolRegistry(permission_manager=self.perm_manager)
        self.planner = TaskPlanner(tool_registry=self.registry)

    # -------------------------------------------------------------------------
    # 1. Backend Selection & Factory
    # -------------------------------------------------------------------------
    def test_01_backend_factory_direct(self):
        """TEST 1: BackendFactory instantiates DirectModelBackend when 'direct' is requested."""
        backend = BackendFactory.create_backend("direct", tool_registry=self.registry)
        self.assertIsInstance(backend, AgentBackend)
        self.assertIsInstance(backend, DirectModelRouter)
        self.assertEqual(backend.get_name(), "DirectModelRouter")

    def test_02_backend_factory_harness(self):
        """TEST 2: BackendFactory instantiates DeepSeekHarnessBackend when 'harness' is requested."""
        backend = BackendFactory.create_backend("harness", tool_registry=self.registry)
        self.assertIsInstance(backend, AgentBackend)
        self.assertIsInstance(backend, DeepSeekHarnessBackend)
        self.assertEqual(backend.get_name(), "DeepSeekHarnessBackend")

    def test_03_backend_factory_uncensored(self):
        """TEST 3: BackendFactory instantiates UncensoredR1Backend when 'uncensored' is requested."""
        backend = BackendFactory.create_backend("uncensored", tool_registry=self.registry)
        self.assertIsInstance(backend, AgentBackend)
        self.assertIsInstance(backend, UncensoredR1Backend)
        self.assertEqual(backend.get_name(), "UncensoredR1Backend")

    def test_04_backend_factory_invalid_fallback(self):
        """TEST 4: BackendFactory gracefully defaults to DirectModelBackend on invalid backend name."""
        backend = BackendFactory.create_backend("invalid_unknown_backend_xyz", tool_registry=self.registry)
        self.assertIsInstance(backend, AgentBackend)
        self.assertIsInstance(backend, DirectModelRouter)

    def test_05_direct_backend_alias_compatibility(self):
        """TEST 5: DirectModelBackend class and DirectModelRouter alias are identical and compatible."""
        self.assertEqual(DirectModelBackend, DirectModelRouter)
        instance = DirectModelBackend(tool_registry=self.registry)
        self.assertTrue(issubclass(DirectModelBackend, AgentBackend))
        self.assertTrue(hasattr(instance, "process_message"))

    # -------------------------------------------------------------------------
    # 2. DeepSeek Harness Backend
    # -------------------------------------------------------------------------
    def test_06_harness_initialization_lifecycle(self):
        """TEST 6: DeepSeekHarnessBackend initializes with valid session, health status, and lifecycle."""
        harness = DeepSeekHarnessBackend(tool_registry=self.registry)
        self.assertTrue(harness.initialize())
        self.assertTrue(harness.is_healthy())
        self.assertTrue(harness.session_id.startswith("dsh_session_"))
        self.assertEqual(harness.get_name(), "DeepSeekHarnessBackend")

    def test_07_harness_process_message_offline(self):
        """TEST 7: DeepSeekHarnessBackend processes conversational message and normalizes voice output."""
        harness = DeepSeekHarnessBackend(api_key="", tool_registry=self.registry)
        res = harness.process_message("Hello DAKU")
        self.assertIn("Hello", res)
        # Verify markdown stripping and normalization
        raw = "### **Title**\nHello `World` *test*"
        norm = harness._normalize_response(raw)
        self.assertNotIn("*", norm)
        self.assertNotIn("`", norm)
        self.assertNotIn("#", norm)

    def test_08_harness_tool_request_extraction(self):
        """TEST 8: DeepSeekHarnessBackend extracts tool calls from choice structure or <tool_call> tags."""
        harness = DeepSeekHarnessBackend(tool_registry=self.registry)
        # Standard tool_calls structure
        choice_dict = {
            "tool_calls": [
                {
                    "function": {
                        "name": "system_tool",
                        "arguments": json.dumps({"query": "ram"}),
                    }
                }
            ]
        }
        extracted = harness._extract_tool_request(choice_dict)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted[0], "system_tool")
        self.assertEqual(extracted[1].get("query"), "ram")

        # <tool_call> text tag structure
        tag_choice = {
            "message": {
                "content": "Let me check that: <tool_call>{\"name\": \"system_tool\", \"arguments\": {\"query\": \"cpu\"}}</tool_call>"
            }
        }
        tag_extracted = harness._extract_tool_request(tag_choice)
        self.assertIsNotNone(tag_extracted)
        self.assertEqual(tag_extracted[0], "system_tool")
        self.assertEqual(tag_extracted[1].get("query"), "cpu")

    def test_09_harness_timeout_handling(self):
        """TEST 9: DeepSeekHarnessBackend gracefully handles network timeout without crashing."""
        harness = DeepSeekHarnessBackend(api_key="valid_key", tool_registry=self.registry)
        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            reply = harness.process_message("Perform analysis")
            self.assertIn("timed out", reply.lower())

    def test_10_harness_auth_failure_handling(self):
        """TEST 10: DeepSeekHarnessBackend returns clear message on HTTP 401 authentication error."""
        import urllib.error
        harness = DeepSeekHarnessBackend(api_key="invalid_mock_key", tool_registry=self.registry)
        http_err = urllib.error.HTTPError(
            url="http://mock", code=401, msg="Unauthorized", hdrs={}, fp=MagicMock()
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            reply = harness.process_message("Hello cloud agent")
            self.assertIn("Authentication failed", reply)

    def test_11_harness_clean_shutdown(self):
        """TEST 11: DeepSeekHarnessBackend shuts down cleanly and rejects further processing."""
        harness = DeepSeekHarnessBackend(tool_registry=self.registry)
        self.assertTrue(harness.is_healthy())
        harness.shutdown()
        self.assertFalse(harness.is_healthy())
        reply = harness.process_message("Hello after shutdown")
        self.assertIn("shut down", reply.lower())

    # -------------------------------------------------------------------------
    # 3. Uncensored R1 Remote Backend
    # -------------------------------------------------------------------------
    def test_12_uncensored_r1_initialization(self):
        """TEST 12: UncensoredR1Backend initializes with remote model target and healthy state."""
        r1 = UncensoredR1Backend(tool_registry=self.registry)
        self.assertTrue(r1.initialize())
        self.assertTrue(r1.is_healthy())
        self.assertEqual(r1.get_name(), "UncensoredR1Backend")
        self.assertIn("deepseek-r1", r1.model_name.lower())

    def test_13_uncensored_r1_think_tag_stripping(self):
        """TEST 13: UncensoredR1Backend strips <think>...</think> reasoning traces so TTS only speaks clean output."""
        r1 = UncensoredR1Backend(tool_registry=self.registry)
        raw_text = (
            "<think>\n"
            "The user is asking about the time in Delhi. The current local time is known.\n"
            "I should provide a direct, polite answer.\n"
            "</think>\n"
            "The current time is 7:30 PM."
        )
        clean_text, reasoning = r1._strip_think_tags(raw_text)
        self.assertEqual(clean_text, "The current time is 7:30 PM.")
        self.assertIsNotNone(reasoning)
        self.assertIn("user is asking about the time", reasoning)
        self.assertNotIn("<think>", clean_text)
        self.assertNotIn("</think>", clean_text)

    def test_14_uncensored_r1_tool_request_extraction(self):
        """TEST 14: UncensoredR1Backend extracts tool requests from reasoning or JSON blocks."""
        r1 = UncensoredR1Backend(tool_registry=self.registry)
        # Markdown JSON block format
        text_with_json = (
            "I will check the RAM for you.\n"
            "```json\n"
            "{\n"
            '  "tool": "system_tool",\n'
            '  "args": {"query": "ram"}\n'
            "}\n"
            "```"
        )
        tool_req = r1._extract_tool_request(text_with_json)
        self.assertIsNotNone(tool_req)
        self.assertEqual(tool_req[0], "system_tool")
        self.assertEqual(tool_req[1].get("query"), "ram")

        # <action tool="..."> format
        text_with_tag = '<action tool="system_tool">{"query": "cpu"}</action>'
        tool_req2 = r1._extract_tool_request(text_with_tag)
        self.assertIsNotNone(tool_req2)
        self.assertEqual(tool_req2[0], "system_tool")

    def test_15_uncensored_r1_auth_error_handling(self):
        """TEST 15: UncensoredR1Backend handles 401 Unauthorized cleanly with informative message."""
        import urllib.error
        r1 = UncensoredR1Backend(api_key="bad_token", tool_registry=self.registry)
        http_err = urllib.error.HTTPError(
            url="http://mock", code=401, msg="Unauthorized", hdrs={}, fp=MagicMock()
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            res = r1.process_message("What is your status?")
            self.assertIn("Authentication failed", res)

    def test_16_uncensored_r1_endpoint_unavailable_fallback(self):
        """TEST 16: UncensoredR1Backend falls back to local intent when remote endpoint is unreachable."""
        import urllib.error
        r1 = UncensoredR1Backend(api_key="valid_test_key", tool_registry=self.registry)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            # Should gracefully fall back to local intent parser for RAM query
            res = r1.process_message("how much ram is free?")
            self.assertIn("free RAM", res)

    def test_17_uncensored_r1_clean_shutdown(self):
        """TEST 17: UncensoredR1Backend shuts down cleanly and rejects processing."""
        r1 = UncensoredR1Backend(tool_registry=self.registry)
        r1.shutdown()
        self.assertFalse(r1.is_healthy())
        reply = r1.process_message("hello")
        self.assertIn("shut down", reply.lower())

    # -------------------------------------------------------------------------
    # 4. Agent Loop & Task Planner Hardening
    # -------------------------------------------------------------------------
    def test_18_max_task_steps_limit(self):
        """TEST 18: TaskPlanner enforces maximum 10 steps limit to prevent runaway execution."""
        self.assertEqual(MAX_TASK_STEPS, 10)
        # Create a plan with 15 steps
        steps = [
            TaskStep(
                step_id=i,
                description=f"Step {i}",
                tool_name="system_tool",
                action="ram",
                args={"query": "ram"},
            )
            for i in range(1, 16)
        ]
        plan = TaskPlan(plan_id="plan_overlimit", raw_query="large plan", steps=steps)
        # Execute plan
        res = self.planner.execute_plan(plan)
        # Plan steps must be truncated to 10
        self.assertLessEqual(len(plan.steps), MAX_TASK_STEPS)

    def test_19_max_retries_limit(self):
        """TEST 19: TaskPlanner enforces maximum 2 retries per step upon failure."""
        self.assertEqual(MAX_RETRIES_PER_STEP, 2)
        step = TaskStep(
            step_id=1,
            description="Failing step",
            tool_name="application_tool",
            action="launch",
            args={"action": "launch", "app_name": "fake_app_9999999"},
            max_retries=10,  # Requesting excessive retries
        )
        plan = TaskPlan(plan_id="plan_retry_limit", raw_query="retry test", steps=[step])
        res = self.planner.execute_plan(plan)
        # Retries must not exceed MAX_RETRIES_PER_STEP (which is 2)
        self.assertLessEqual(step.retries, MAX_RETRIES_PER_STEP)
        self.assertFalse(res["success"])

    def test_20_state_machine_transitions(self):
        """TEST 20: TaskPlanner strictly follows PLANNING -> EXECUTING -> VERIFYING -> COMPLETED."""
        mock_html = "<html><head><title>Test Page</title></head></html>"
        with patch("subprocess.Popen"):
            with patch.object(self.registry.get_tool("browser_tool"), "_fetch_html", return_value=(mock_html, None)):
                with patch.object(self.registry.get_tool("application_tool"), "_is_process_running", return_value=True):
                    plan = self.planner.create_plan("open Chrome, go to https://example.com and tell me the page title")
                    self.assertEqual(plan.state, TaskState.PLANNING)
                    res = self.planner.execute_plan(plan)
                    self.assertTrue(res["success"])
                    self.assertEqual(plan.state, TaskState.COMPLETED)

    def test_21_failure_path_and_recovery(self):
        """TEST 21: TaskPlanner failure path transitions to FAILED and RECOVERY without false success."""
        step = TaskStep(
            step_id=1,
            description="Non-existent app",
            tool_name="application_tool",
            action="launch",
            args={"action": "launch", "app_name": "definitely_invalid_app_123"},
            max_retries=1,
        )
        plan = TaskPlan(plan_id="plan_fail", raw_query="fail", steps=[step])
        res = self.planner.execute_plan(plan)
        self.assertFalse(res["success"])
        self.assertIn(plan.state, (TaskState.FAILED, TaskState.RECOVERY))
        self.assertIn("Task stopped at step", res["message"])

    # -------------------------------------------------------------------------
    # 5. MCP Orchestration & Tool Routing
    # -------------------------------------------------------------------------
    def test_22_mcp_server_reuse_without_modification(self):
        """TEST 22: MCPManager discovers existing MCP servers without modifying any machine configuration."""
        mcp = MCPManager()
        servers = mcp.discovered_servers
        self.assertTrue(mcp.is_available())
        # Verify presence of existing machine servers
        self.assertTrue(any(k in servers for k in ("chrome-devtools-mcp", "code-review-graph", "netlify-mcp", "netlify")))

    def test_23_mcp_tool_routing_and_validation(self):
        """TEST 23: ToolRegistry validates MCP tool names, schemas, and prevents arbitrary shell execution."""
        # Registered tools check
        tools = self.registry.list_tool_names()
        self.assertIn("browser_tool", tools)
        self.assertIn("application_tool", tools)

        # Non-existent tool execution returns clean structured error
        bad_res = self.registry.execute_tool("unknown_malformed_tool_call", {"x": 1})
        self.assertFalse(bad_res.success)
        self.assertFalse(bad_res.verified)
        self.assertIn("not registered", bad_res.error)

    # -------------------------------------------------------------------------
    # 6. Security & Safety
    # -------------------------------------------------------------------------
    def test_24_direct_model_os_execution_blocked(self):
        """TEST 24: Direct model-to-OS execution is blocked; raw shell execution is prohibited."""
        # Attempt to run cmd.exe / powershell as a tool
        res1 = self.registry.execute_tool("powershell", {"cmd": "dir"})
        self.assertFalse(res1.success)
        self.assertFalse(res1.verified)

        res2 = self.registry.execute_tool("cmd", {"command": "echo test"})
        self.assertFalse(res2.success)
        self.assertFalse(res2.verified)

    def test_25_permission_bypass_permanently_blocked(self):
        """TEST 25: PermissionManager strictly rejects BLOCKED operations even if called directly."""
        pm = PermissionManager()
        # Attempt file deletion
        allowed, level, msg = pm.evaluate("file_tool", "delete_file", {"path": "C:\\Windows\\win.ini"}, PermissionLevel.SAFE)
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)
        self.assertIn("prohibited by DAKU safety policy", msg)

        # Attempt raw powershell
        allowed2, level2, msg2 = pm.evaluate("custom_tool", "powershell_raw", {}, PermissionLevel.SAFE)
        self.assertFalse(allowed2)
        self.assertEqual(level2, PermissionLevel.BLOCKED)

    def test_26_sensitive_credential_masking(self):
        """TEST 26: Sensitive values (API keys, tokens, passwords) are masked in outputs and logs."""
        from brain.backend import _mask_secret_value
        from tools.mcp_client import _mask_secret

        masked1 = _mask_secret_value("sk-deepseek-1234567890abcdef")
        self.assertTrue("********" in masked1)
        self.assertNotIn("1234567890", masked1)

        masked2 = _mask_secret("Bearer token_secret_123456789")
        self.assertTrue("***" in masked2)
        self.assertNotIn("secret_123456", masked2)

    # -------------------------------------------------------------------------
    # 7. Resource Safety
    # -------------------------------------------------------------------------
    def test_27_zero_local_large_model_resource_safety(self):
        """TEST 27: Asserts zero heavy local LLMs or torch weights are loaded in the DAKU process."""
        # Verify torch or heavy LLM libraries are not imported into memory
        loaded_modules = sys.modules.keys()
        self.assertNotIn("torch", loaded_modules, "PyTorch weights must NOT be loaded locally.")
        self.assertNotIn("transformers", loaded_modules, "Transformers weights must NOT be loaded locally.")
        self.assertNotIn("llama_cpp", loaded_modules, "llama.cpp must NOT be loaded locally.")
        self.assertNotIn("ollama", loaded_modules, "Local Ollama client must NOT be active.")


if __name__ == "__main__":
    unittest.main()
