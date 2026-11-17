"""
DAKU Automated Test Suite for Phase 2 (Local Computer Agent & MCP)
Verifies:
- TEST 1: Tool registry initialization and schema export.
- TEST 2: Application launch and process verification.
- TEST 3: Application launch failure handling for non-existent application.
- TEST 4: File search with pattern matching (e.g. *.pdf, *.txt).
- TEST 5: Directory listing with item count and memory safeguards.
- TEST 6: Text file reading with character truncation limit.
- TEST 7: System information queries (RAM, CPU, disk, time, Windows version).
- TEST 8: Permission SAFE action automatic execution.
- TEST 9: Permission CONFIRMATION_REQUIRED action handling (approve & reject).
- TEST 10: BLOCKED action rejection (e.g. file deletion, arbitrary shell).
- TEST 11: Invalid tool arguments validation.
- TEST 12: Real action verification contract.
- TEST 13: Error handling for non-existent paths/files.
- TEST 14: No arbitrary shell execution guarantee.
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
from tools.application import ApplicationTool
from tools.base import PermissionLevel, ToolResult
from tools.file_ops import FileTool
from tools.mcp_client import DynamicMCPTool, MCPManager
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry
from tools.system import SystemTool


class TestDakuPhase2(unittest.TestCase):

    def setUp(self):
        self.perm_manager = PermissionManager(auto_confirm_in_test=True)
        self.registry = ToolRegistry(permission_manager=self.perm_manager)

    def test_01_tool_registry(self):
        """TEST 1: Verify tool registry registers native and MCP tools and exports schemas."""
        tool_names = self.registry.list_tool_names()
        self.assertIn("application_tool", tool_names)
        self.assertIn("file_tool", tool_names)
        self.assertIn("system_tool", tool_names)

        schemas = self.registry.get_schemas()
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 0)
        self.assertTrue(any(s["name"] == "application_tool" for s in schemas))

    def test_02_application_launch(self):
        """TEST 2: Verify application launch and process verification."""
        app_tool = ApplicationTool()
        with patch("subprocess.Popen") as mock_popen:
            with patch.object(app_tool, "_is_process_running", return_value=True):
                res = app_tool.launch_app("notepad")
                self.assertTrue(res.success)
                self.assertTrue(res.verified)
                self.assertIn("Notepad is open", res.message)

    def test_03_application_launch_failure(self):
        """TEST 3: Verify graceful failure when attempting to launch a non-existent app."""
        app_tool = ApplicationTool()
        res = app_tool.launch_app("non_existent_fake_app_12345")
        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertIn("couldn't find", res.message.lower())

    def test_04_file_search(self):
        """TEST 4: Verify file search with pattern matching."""
        file_tool = FileTool()
        # Search inside DAKU directory for *.py files
        res = file_tool.search_files(pattern="*.py", search_dir=str(BASE_DIR))
        self.assertTrue(res.success)
        self.assertTrue(res.verified)
        self.assertGreater(res.data["count"], 0)
        self.assertTrue(any(f["name"] == "main.py" for f in res.data["matches"]))

    def test_05_directory_listing(self):
        """TEST 5: Verify directory listing with memory safeguards."""
        file_tool = FileTool()
        res = file_tool.list_directory(str(BASE_DIR))
        self.assertTrue(res.success)
        self.assertTrue(res.verified)
        self.assertIsInstance(res.data["items"], list)
        self.assertLessEqual(len(res.data["items"]), 50)

    def test_06_text_file_reading(self):
        """TEST 6: Verify safe text file reading within character limits."""
        file_tool = FileTool()
        readme_path = str(BASE_DIR / "README.md")
        res = file_tool.read_text_file(readme_path, max_chars=500)
        self.assertTrue(res.success)
        self.assertTrue(res.verified)
        self.assertLessEqual(len(res.data["content"]), 500)

    def test_07_system_information(self):
        """TEST 7: Verify real system information queries (RAM, CPU, disk, time, OS)."""
        sys_tool = SystemTool()

        # Query RAM
        ram_res = sys_tool.get_ram_info()
        self.assertTrue(ram_res.success)
        self.assertGreater(ram_res.data["total_gb"], 0)
        self.assertGreater(ram_res.data["free_gb"], 0)
        self.assertIn("GB of free RAM", ram_res.message)

        # Query CPU
        cpu_res = sys_tool.get_cpu_info()
        self.assertTrue(cpu_res.success)
        self.assertGreater(cpu_res.data["logical_cores"], 0)

        # Query Disk
        disk_res = sys_tool.get_disk_info()
        self.assertTrue(disk_res.success)
        self.assertGreater(disk_res.data["total_gb"], 0)

        # Query Time
        time_res = sys_tool.get_current_time()
        self.assertTrue(time_res.success)
        self.assertIn("current time is", time_res.message)

        # Query Windows Version
        os_res = sys_tool.get_windows_version()
        self.assertTrue(os_res.success)
        self.assertIn("Windows", os_res.data["os"])

    def test_08_permission_safe_action(self):
        """TEST 8: Verify SAFE permission level allows immediate execution."""
        pm = PermissionManager()
        allowed, level, msg = pm.evaluate("system_tool", "get_ram_info", {}, PermissionLevel.SAFE)
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

    def test_09_permission_confirmation_action(self):
        """TEST 9: Verify CONFIRMATION_REQUIRED actions prompt user and respect response."""
        # Case A: User approves confirmation
        pm_approve = PermissionManager(confirmation_callback=lambda tool, desc: True)
        allowed, level, msg = pm_approve.evaluate("file_tool", "create_file", {"path": "test.txt"}, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)

        # Case B: User denies confirmation
        pm_deny = PermissionManager(confirmation_callback=lambda tool, desc: False)
        allowed_deny, level_deny, msg_deny = pm_deny.evaluate("file_tool", "create_file", {"path": "test.txt"}, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertFalse(allowed_deny)
        self.assertIn("denied", msg_deny.lower())

    def test_10_blocked_action(self):
        """TEST 10: Verify dangerous and BLOCKED actions are permanently rejected."""
        pm = PermissionManager()

        # Delete operations
        allowed1, level1, msg1 = pm.evaluate("file_tool", "delete_file", {"path": "important.txt"}, PermissionLevel.SAFE)
        self.assertFalse(allowed1)
        self.assertEqual(level1, PermissionLevel.BLOCKED)

        # Arbitrary shell execution attempt
        allowed2, level2, msg2 = pm.evaluate("shell_tool", "exec_shell", {"cmd": "rm -rf /"}, PermissionLevel.SAFE)
        self.assertFalse(allowed2)
        self.assertEqual(level2, PermissionLevel.BLOCKED)

    def test_11_invalid_tool_arguments(self):
        """TEST 11: Verify invalid or missing arguments fail validation cleanly."""
        res = self.registry.execute_tool("application_tool", {"action": "invalid_unknown_action"})
        self.assertFalse(res.success)
        self.assertIn("Validation failed", res.error)

    def test_12_action_verification(self):
        """TEST 12: Verify execution contract: actions verify their real output."""
        file_tool = FileTool()
        dummy_file = BASE_DIR / "tests" / "scratch_test_verify.tmp"
        try:
            # Create file
            res = file_tool.create_file(str(dummy_file), "Verification test content")
            self.assertTrue(res.success)
            self.assertTrue(res.verified)
            self.assertTrue(dummy_file.is_file())
        finally:
            if dummy_file.is_file():
                dummy_file.unlink()

    def test_13_error_handling(self):
        """TEST 13: Verify non-existent files or invalid paths are handled gracefully."""
        file_tool = FileTool()
        res = file_tool.read_text_file("C:\\invalid\\non_existent_folder_999\\fake.txt")
        self.assertFalse(res.success)
        self.assertIn("Could not find file", res.message)

    def test_14_no_arbitrary_shell_execution(self):
        """TEST 14: Verify raw command strings cannot be executed directly on the system."""
        # Attempt to run a shell command as a tool
        res = self.registry.execute_tool("powershell_raw", {"cmd": "Get-Process"})
        self.assertFalse(res.success)
        self.assertFalse(res.verified)
        self.assertIn("not registered", res.error)

    def test_15_mcp_discovery_and_tools(self):
        """TEST 15: Verify MCPManager discovers existing machine MCP servers and registers tools."""
        mcp = MCPManager()
        servers = mcp.get_status_report()
        self.assertIsInstance(servers, list)
        tools = mcp.create_mcp_tools()
        self.assertIsInstance(tools, list)

    def test_16_brain_offline_tool_routing(self):
        """TEST 16: Verify Brain routes offline voice queries to local system tools."""
        brain = Brain(backend=DirectModelRouter(api_key="", tool_registry=self.registry))

        # Test RAM query via Brain
        ram_reply = brain.think("DAKU, how much RAM is free?")
        self.assertIn("free RAM", ram_reply)

        # Test PDF search via Brain
        pdf_reply = brain.think("DAKU, find my PDF files")
        self.assertTrue("PDF" in pdf_reply or "file" in pdf_reply)

        # Test App launch via Brain
        with patch.object(ApplicationTool, "launch_app", return_value=ToolResult(success=True, message="Notepad is open.", verified=True)):
            app_reply = brain.think("DAKU, open Notepad")
            self.assertEqual(app_reply, "Notepad is open.")


if __name__ == "__main__":
    unittest.main()
