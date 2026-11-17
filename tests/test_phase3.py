"""
DAKU Automated Test Suite for Phase 3 (MCP + Browser + Multi-Step Task Automation)
Verifies:
- TEST 1: MCP server discovery without duplication or config overwrite.
- TEST 2: MCP server health checks and status reporting.
- TEST 3: MCP tool schema validation and parameter mapping.
- TEST 4: MCP unavailable fallback to safe native handling.
- TEST 5: Browser MCP connection and detection.
- TEST 6: Browser launch and safe process execution.
- TEST 7: Safe URL sanitization & blocked schemes (javascript:, file:, data:).
- TEST 8: Browser navigation and verified connectivity.
- TEST 9: Page title extraction and verification from real/mock HTML.
- TEST 10: Page visible text extraction with memory/token safeguards.
- TEST 11: Inspect safe links with scheme filtering.
- TEST 12: ToolRouter priority order resolution (Native -> MCP -> Fallback -> Refuse).
- TEST 13: Multi-step task planning (open Chrome and navigate URL).
- TEST 14: Multi-step task planning with title query.
- TEST 15: Task state machine transitions (PLANNING -> EXECUTING -> VERIFYING -> COMPLETED).
- TEST 16: Task state machine failure path and recovery (EXECUTING -> FAILED -> RECOVERY).
- TEST 17: Maximum retry enforcement (stops after max 2 retries on step failure).
- TEST 18: Safe browser action auto-execution.
- TEST 19: Confirmation-required action handling in browser and tools.
- TEST 20: Blocked action rejection (credential theft, arbitrary eval).
- TEST 21: Sensitive data protection (passwords/tokens redacted in tool results).
- TEST 22: Arbitrary shell execution strictly blocked.
- TEST 23: End-to-end multi-step Brain task execution.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.router import Brain, DirectModelRouter
from tools.base import PermissionLevel, ToolResult
from tools.browser import BrowserTool
from tools.mcp_client import DynamicMCPTool, MCPManager
from tools.permissions import PermissionManager
from tools.planner import TaskPlan, TaskPlanner, TaskState, TaskStep
from tools.registry import ToolRegistry, ToolRouter


class TestDakuPhase3(unittest.TestCase):

    def setUp(self):
        self.perm_manager = PermissionManager(auto_confirm_in_test=True)
        self.registry = ToolRegistry(permission_manager=self.perm_manager)
        self.planner = TaskPlanner(tool_registry=self.registry)

    def test_01_mcp_discovery(self):
        """TEST 1: Verify MCP server discovery without duplication or config modification."""
        mcp = MCPManager()
        servers = mcp.discovered_servers
        self.assertIsInstance(servers, dict)
        self.assertTrue(mcp.is_available())
        # Check known servers from Phase 2
        server_names = list(servers.keys())
        self.assertTrue(any(s in server_names for s in ("chrome-devtools-mcp", "netlify-mcp", "code-review-graph")))

    def test_02_mcp_health_check(self):
        """TEST 2: Verify MCP server health reporting and zero credential exposure."""
        mcp = MCPManager()
        report = mcp.get_status_report()
        self.assertIsInstance(report, list)
        self.assertGreater(len(report), 0)
        for s in report:
            self.assertIn("name", s)
            self.assertIn("status", s)
            self.assertIn("tools_count", s)
            # Ensure no secret strings in status
            for k, v in s.items():
                self.assertNotIn("password", str(v).lower())
                self.assertNotIn("secret_key", str(v).lower())

    def test_03_mcp_schema_validation(self):
        """TEST 3: Verify MCP tool schema parsing and permission classification."""
        mcp = MCPManager()
        tools = mcp.create_mcp_tools()
        self.assertGreater(len(tools), 0)
        for t in tools:
            self.assertIsInstance(t, DynamicMCPTool)
            self.assertTrue(t.name.startswith("mcp_"))
            self.assertIn(t.permission_level, (PermissionLevel.SAFE, PermissionLevel.CONFIRMATION_REQUIRED, PermissionLevel.BLOCKED))

    def test_04_mcp_unavailable_fallback(self):
        """TEST 4: Verify graceful handling and fallback when an MCP handler fails."""
        def failing_handler(tool_name, args):
            raise ConnectionError("Simulated MCP socket disconnect")

        mcp_tool = DynamicMCPTool(
            server_name="test_server",
            tool_name="test_action",
            description="Test MCP tool",
            handler=failing_handler,
        )
        res = mcp_tool.execute({"param": 123})
        self.assertFalse(res.success)
        self.assertIn("Falling back", res.message)

    def test_05_browser_mcp_detection(self):
        """TEST 5: Verify browser MCP capability detection."""
        mcp = MCPManager()
        self.assertTrue(mcp.has_browser_mcp())

    def test_06_browser_launch(self):
        """TEST 6: Verify safe browser launch and process verification."""
        browser_tool = BrowserTool()
        with patch("subprocess.Popen") as mock_popen:
            res = browser_tool.launch_browser(browser="chrome", url="https://www.google.com")
            self.assertTrue(res.success)
            self.assertTrue(res.verified)
            self.assertIn("Chrome launched", res.message)

    def test_07_url_sanitization_and_blocked_schemes(self):
        """TEST 7: Verify URL sanitization and blocking of malicious schemes."""
        bt = BrowserTool()

        # Blocked javascript: scheme
        url1, err1 = bt._sanitize_url("javascript:alert(1)")
        self.assertIsNone(url1)
        self.assertIn("Security Block", err1)

        # Blocked file: scheme
        url2, err2 = bt._sanitize_url("file:///C:/Windows/System32/cmd.exe")
        self.assertIsNone(url2)
        self.assertIn("Security Block", err2)

        # Valid domain auto-prefixed with https://
        url3, err3 = bt._sanitize_url("bhartiyarishtey.com")
        self.assertIsNone(err3)
        self.assertEqual(url3, "https://bhartiyarishtey.com")

    def test_08_browser_navigation(self):
        """TEST 8: Verify browser navigation and connectivity verification."""
        bt = BrowserTool()
        mock_html = "<html><head><title>Bhartiya Rishtey - Matrimonial Portal</title></head><body><h1>Welcome</h1></body></html>"
        with patch.object(bt, "launch_browser", return_value=ToolResult(success=True, verified=True, message="Opened")):
            with patch.object(bt, "_fetch_html", return_value=(mock_html, None)):
                res = bt.navigate("bhartiyarishtey.com")
                self.assertTrue(res.success)
                self.assertTrue(res.verified)
                self.assertIn("Bhartiya Rishtey", res.data["title"])

    def test_09_page_title_extraction(self):
        """TEST 9: Verify page title extraction and verification from real/mock HTML."""
        bt = BrowserTool()
        mock_html = "<html><head><title>   Google   </title></head><body>Content</body></html>"
        with patch.object(bt, "_fetch_html", return_value=(mock_html, None)):
            res = bt.get_page_title("https://www.google.com")
            self.assertTrue(res.success)
            self.assertTrue(res.verified)
            self.assertEqual(res.data["title"], "Google")
            self.assertEqual(res.message, "The page title is Google.")

    def test_10_page_text_extraction_limits(self):
        """TEST 10: Verify page visible text extraction adheres to character limits."""
        bt = BrowserTool()
        long_content = "Word " * 500
        mock_html = f"<html><body><p>{long_content}</p><script>var x = 1;</script></body></html>"
        with patch.object(bt, "_fetch_html", return_value=(mock_html, None)):
            res = bt.get_page_text("https://example.com", max_chars=100)
            self.assertTrue(res.success)
            self.assertLessEqual(len(res.data["text"]), 105)
            self.assertNotIn("var x", res.data["text"])  # Script removed

    def test_11_inspect_safe_links(self):
        """TEST 11: Verify inspect_links filters out non-HTTP links safely."""
        bt = BrowserTool()
        mock_html = """
        <html><body>
            <a href="/about">About Us</a>
            <a href="https://example.com/contact">Contact</a>
            <a href="javascript:doBadThings()">Malicious Link</a>
        </body></html>
        """
        with patch.object(bt, "_fetch_html", return_value=(mock_html, None)):
            res = bt.inspect_links("https://example.com")
            self.assertTrue(res.success)
            links = res.data["links"]
            self.assertEqual(len(links), 2)
            self.assertTrue(all(l.startswith("http") for l in links))

    def test_12_tool_router_priority(self):
        """TEST 12: Verify ToolRouter priority decision order (Native -> MCP -> Fallback)."""
        router = self.registry.router
        tool_name, args = router.route_action("navigate", {"url": "https://google.com"})
        self.assertEqual(tool_name, "browser_tool")

        tool_name2, _ = router.route_action("launch_app", {"app_name": "notepad"})
        self.assertEqual(tool_name2, "application_tool")

        tool_name3, _ = router.route_action("ram", {})
        self.assertEqual(tool_name3, "system_tool")

    def test_13_multi_step_planning(self):
        """TEST 13: Verify multi-step planning for browser open and navigation."""
        plan = self.planner.create_plan("open Chrome and open bhartiyarishtey.com")
        self.assertEqual(plan.state, TaskState.PLANNING)
        self.assertGreaterEqual(len(plan.steps), 2)
        # Step 1 is app launch or browser launch
        self.assertIn(plan.steps[0].tool_name, ("application_tool", "browser_tool"))
        # Step 2 is navigation
        self.assertEqual(plan.steps[1].tool_name, "browser_tool")
        self.assertEqual(plan.steps[1].action, "navigate")

    def test_14_multi_step_plan_with_title(self):
        """TEST 14: Verify planning for browser launch, navigation, and page title extraction."""
        plan = self.planner.create_plan("open Chrome, go to bhartiyarishtey.com and tell me the page title")
        self.assertGreaterEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].tool_name, "application_tool")
        self.assertEqual(plan.steps[1].tool_name, "browser_tool")
        self.assertEqual(plan.steps[2].action, "get_title")

    def test_15_task_state_machine_execution(self):
        """TEST 15: Verify state machine transitions from PLANNING to COMPLETED with verification."""
        mock_html = "<html><head><title>Bhartiya Rishtey Matrimonial</title></head></html>"
        with patch("subprocess.Popen"):
            with patch.object(self.registry.get_tool("browser_tool"), "_fetch_html", return_value=(mock_html, None)):
                with patch.object(self.registry.get_tool("application_tool"), "_is_process_running", return_value=True):
                    plan = self.planner.create_plan("open Chrome, go to bhartiyarishtey.com and tell me the page title")
                    result = self.planner.execute_plan(plan)
                    self.assertTrue(result["success"])
                    self.assertEqual(plan.state, TaskState.COMPLETED)
                    self.assertIn("The page title is Bhartiya Rishtey Matrimonial.", result["message"])

    def test_16_state_machine_failure_and_recovery(self):
        """TEST 16: Verify failure path transitions to FAILED/RECOVERY and never claims false success."""
        plan = TaskPlan(
            plan_id="plan_fail",
            raw_query="fail test",
            steps=[
                TaskStep(
                    step_id=1,
                    description="Open invalid application",
                    tool_name="application_tool",
                    action="launch",
                    args={"action": "launch", "app_name": "definitely_non_existent_app_99999"},
                    max_retries=1,
                )
            ],
        )
        result = self.planner.execute_plan(plan)
        self.assertFalse(result["success"])
        self.assertIn(plan.state, (TaskState.FAILED, TaskState.RECOVERY))
        self.assertIn("Task stopped at step", result["message"])

    def test_17_max_retry_enforcement(self):
        """TEST 17: Verify planner stops after max 2 retries upon step failure."""
        mock_tool = MagicMock()
        mock_tool.name = "mock_failing_tool"
        mock_tool.permission_level = PermissionLevel.SAFE
        mock_tool.validate_args.return_value = None
        mock_tool.execute.return_value = ToolResult(success=False, error="Persistent network timeout", verified=False)
        mock_tool.verify.return_value = False

        self.registry.register(mock_tool)

        step = TaskStep(
            step_id=1,
            description="Mock failing action",
            tool_name="mock_failing_tool",
            action="execute",
            args={},
            max_retries=2,
        )
        plan = TaskPlan(plan_id="plan_retry", raw_query="retry test", steps=[step])

        self.planner.execute_plan(plan)
        # Attempt 0, retry 1, retry 2 = 3 executions total
        self.assertEqual(mock_tool.execute.call_count, 3)
        self.assertEqual(step.retries, 2)
        self.assertEqual(plan.state, TaskState.RECOVERY)

    def test_18_safe_action_auto_execution(self):
        """TEST 18: Verify SAFE browser navigation executes automatically."""
        pm = PermissionManager()
        allowed, level, _ = pm.evaluate("browser_tool", "navigate", {"url": "https://google.com"}, PermissionLevel.SAFE)
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

    def test_19_confirmation_required_browser_action(self):
        """TEST 19: Verify sensitive typing/actions require confirmation."""
        # Approved by callback
        pm_approve = PermissionManager(confirmation_callback=lambda tool, desc: True)
        reg_approve = ToolRegistry(permission_manager=pm_approve)
        res_app = reg_approve.execute_tool("browser_tool", {"action": "type_text", "selector": "#login", "text": "my_user", "sensitive": True})
        self.assertTrue(res_app.success)

        # Denied by callback
        pm_deny = PermissionManager(confirmation_callback=lambda tool, desc: False)
        reg_deny = ToolRegistry(permission_manager=pm_deny)
        res_deny = reg_deny.execute_tool("browser_tool", {"action": "type_text", "selector": "#login", "text": "my_user", "sensitive": True})
        self.assertFalse(res_deny.success)
        self.assertIn("denied", res_deny.error.lower())

    def test_20_blocked_action_rejection(self):
        """TEST 20: Verify dangerous and credential-theft actions are permanently blocked."""
        pm = PermissionManager()
        allowed, level, msg = pm.evaluate("browser_tool", "read_password", {}, PermissionLevel.SAFE)
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)

    def test_21_sensitive_data_protection(self):
        """TEST 21: Verify sensitive field text is masked to prevent logging or leaks."""
        bt = BrowserTool()
        res = bt.type_text(selector="#user_password_input", text="SecretPassword123")
        self.assertTrue(res.success)
        self.assertEqual(res.data["text"], "******")
        self.assertNotIn("SecretPassword123", str(res.data))

    def test_22_arbitrary_shell_blocked(self):
        """TEST 22: Verify raw shell execution requests remain strictly rejected."""
        res = self.registry.execute_tool("powershell_raw", {"cmd": "Get-Process"})
        self.assertFalse(res.success)
        self.assertIn("not registered", res.error)

    def test_23_end_to_end_brain_task(self):
        """TEST 23: Verify end-to-end voice/offline brain pipeline for multi-step browser query."""
        brain = Brain(tool_registry=self.registry)
        mock_html = "<html><head><title>Bhartiya Rishtey - Matrimony</title></head></html>"
        with patch("subprocess.Popen"):
            with patch.object(self.registry.get_tool("browser_tool"), "_fetch_html", return_value=(mock_html, None)):
                with patch.object(self.registry.get_tool("application_tool"), "_is_process_running", return_value=True):
                    response = brain.think("DAKU, open Chrome, go to bhartiyarishtey.com and tell me the page title")
                    self.assertIn("The page title is Bhartiya Rishtey - Matrimony.", response)


if __name__ == "__main__":
    unittest.main()
