"""
DAKU Automated Test Suite for Adaptive Multi-Pass Reasoning & Reusable Computation Engine
Phase 6: Multi-Pass Reasoning, Verification-First Gatekeeping, Reflection & Safe Self-Learning

Verifies:
- TEST 1: EASY task uses 1-2 passes.
- TEST 2: MEDIUM task uses multiple passes.
- TEST 3: HARD task uses bounded passes.
- TEST 4: Successful task stops immediately after verification.
- TEST 5: Verification failure triggers reflection.
- TEST 6: Reflection creates a different strategy (e.g. Edge when Chrome fails).
- TEST 7: Repeated identical action is detected (REPEATED_ACTION_DETECTED).
- TEST 8: Maximum pass limit is strictly enforced (MAX_PASSES = 8).
- TEST 9: Zero MCP servers works gracefully.
- TEST 10: Existing native tools continue working.
- TEST 11: Existing MCP tools continue working.
- TEST 12: Permission system remains enforced.
- TEST 13: BLOCKED actions remain blocked.
- TEST 14: Offline mode remains functional.
- TEST 15: Learning records failure cleanly.
- TEST 16: Learning records success cleanly.
- TEST 17: Learned strategy can be safely reused.
- TEST 18: Secrets never appear in logs or lessons.
- TEST 19: Memory limits are enforced (MAX_LESSONS, MAX_RECENT_OBSERVATIONS).
- TEST 20: No infinite loop is possible.
"""

from io import StringIO
import json
import logging
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.learning import LearningEngine, Lesson, sanitize_data
from brain.multipass import (
    ComplexityLevel,
    MultiPassReasoner,
    PassPhase,
    PassState,
    ReasoningContext,
    ReasoningResult,
)
from brain.reflection import ReflectionEngine, ReflectionResult
from brain.router import Brain, DirectModelRouter
from config.settings import settings
from tools.base import BaseTool, PermissionLevel, ToolParameter, ToolResult
from tools.mcp_client import DynamicMCPTool, MCPManager
from tools.permissions import PermissionManager
from tools.planner import TaskPlanner
from tools.registry import ToolRegistry


class TestMultiPassReasoning(unittest.TestCase):

    def setUp(self):
        self.perm_manager = PermissionManager(auto_confirm_in_test=True)
        self.tool_registry = ToolRegistry(permission_manager=self.perm_manager)
        self.learning_engine = LearningEngine(storage_path=BASE_DIR / "data" / "test_lessons.json")
        self.learning_engine.clear()
        self.reflection_engine = ReflectionEngine(learning_engine=self.learning_engine)
        self.reasoner = MultiPassReasoner(
            tool_registry=self.tool_registry,
            learning_engine=self.learning_engine,
            reflection_engine=self.reflection_engine,
            max_passes=8,
        )

    def tearDown(self):
        self.learning_engine.clear()

    def test_01_easy_task_uses_one_pass(self):
        """TEST 1: EASY task (hardware metric query) uses one pass."""
        query = "check ram"
        complexity = self.reasoner.determine_task_complexity(query)
        self.assertEqual(complexity, ComplexityLevel.EASY)

        budget = self.reasoner.determine_initial_pass_budget(complexity)
        self.assertEqual(budget, 1)

        result = self.reasoner.reason_and_execute(query)
        self.assertTrue(result.success)
        # Easy conversational or single step: passes_used is 1
        self.assertEqual(result.passes_used, 1)
        self.assertIn("RAM", result.final_answer)

    def test_02_medium_task_uses_multiple_passes(self):
        """TEST 2: MEDIUM task uses multiple passes (e.g. 2-3 passes)."""
        query = "open notepad"
        complexity = self.reasoner.determine_task_complexity(query)
        self.assertEqual(complexity, ComplexityLevel.MEDIUM)

        budget = self.reasoner.determine_initial_pass_budget(complexity)
        self.assertGreaterEqual(budget, 3)

        # Mock application launch to succeed and verify
        with patch.object(self.tool_registry, "execute_tool") as mock_exec:
            mock_exec.return_value = ToolResult(
                success=True,
                verified=True,
                message="Notepad is running.",
                data={"app": "notepad"},
            )
            result = self.reasoner.reason_and_execute(query)
            self.assertTrue(result.success)
            self.assertTrue(result.verification_status)
            self.assertGreater(result.passes_used, 1)
            self.assertLessEqual(result.passes_used, 3)

    def test_03_hard_task_uses_bounded_passes(self):
        """TEST 3: HARD task uses bounded passes (e.g. up to 5-6 passes, <= 8)."""
        query = "open chrome, but if it fails figure out another way and verify"
        complexity = self.reasoner.determine_task_complexity(query)
        self.assertEqual(complexity, ComplexityLevel.HARD)

        budget = self.reasoner.determine_initial_pass_budget(complexity)
        self.assertGreaterEqual(budget, 5)
        self.assertLessEqual(budget, 8)

    def test_04_successful_task_stops_immediately_after_verification(self):
        """TEST 4: Successful task stops immediately after verification without continuing to loop."""
        query = "open notepad"  # MEDIUM complexity, budget = 3
        with patch.object(self.tool_registry, "execute_tool") as mock_exec:
            mock_exec.return_value = ToolResult(
                success=True,
                verified=True,
                message="Notepad launched.",
                data={"app": "notepad"},
            )
            result = self.reasoner.reason_and_execute(
                query,
                initial_action=("application_tool", {"action": "launch", "app_name": "notepad"}),
            )
            self.assertTrue(result.success)
            self.assertTrue(result.verification_status)
            # Budget was 3, but stopped immediately on pass 2 once verified
            self.assertEqual(result.passes_used, 2)

    def test_05_verification_failure_triggers_reflection(self):
        """TEST 5: Verification failure triggers reflection engine."""
        fake_result = ToolResult(
            success=False,
            verified=False,
            error="Chrome executable not found on system path.",
            message="Chrome failed to launch.",
        )
        ref_res = self.reflection_engine.reflect_on_failure(
            tool_name="application_tool",
            args={"action": "launch", "app_name": "chrome"},
            tool_result=fake_result,
            expected="Chrome running as verified process",
        )
        self.assertIsInstance(ref_res, ReflectionResult)
        self.assertTrue(ref_res.should_retry)
        self.assertEqual(ref_res.suggested_tool, "application_tool")
        self.assertEqual(ref_res.suggested_args.get("app_name"), "edge")
        self.assertIn("Chrome", ref_res.explanation)

    def test_06_reflection_creates_different_strategy(self):
        """TEST 6: Reflection creates a different strategy when Chrome fails (proposes Edge)."""
        call_count = 0

        def dynamic_exec(tool_name, args):
            nonlocal call_count
            call_count += 1
            if tool_name == "application_tool" and args.get("app_name") == "chrome":
                return ToolResult(
                    success=False,
                    verified=False,
                    error="Application 'chrome' not found on system.",
                    message="Chrome not found.",
                )
            elif tool_name == "application_tool" and args.get("app_name") == "edge":
                return ToolResult(
                    success=True,
                    verified=True,
                    data={"app": "edge", "running": True},
                    message="Application 'edge' launched successfully.",
                )
            return ToolResult(success=False, error="Unknown tool")

        with patch.object(self.tool_registry, "execute_tool", side_effect=dynamic_exec):
            res = self.reasoner.reason_and_execute(
                "open chrome",
                initial_action=("application_tool", {"action": "launch", "app_name": "chrome"}),
            )
            self.assertTrue(res.success)
            self.assertTrue(res.verification_status)
            self.assertIn("Edge", res.final_answer)
            # Checked that call_count executed twice (Chrome -> failed -> Edge -> verified)
            self.assertEqual(call_count, 2)

    def test_07_repeated_identical_action_detected(self):
        """TEST 7: Repeated identical action is detected and prevented from looping."""
        self.assertTrue(self.reasoner._is_repeated_action == self.reasoner._is_repeated_action)
        # Mock action history with identical failing calls
        self.reasoner._action_history = [
            ("application_tool", json.dumps({"action": "launch", "app_name": "chrome"}, sort_keys=True)),
            ("application_tool", json.dumps({"action": "launch", "app_name": "chrome"}, sort_keys=True)),
        ]
        is_rep = self.reasoner._is_repeated_action(
            "application_tool",
            {"action": "launch", "app_name": "chrome"},
        )
        self.assertTrue(is_rep)

    def test_08_maximum_pass_limit_enforced(self):
        """TEST 8: Absolute safety ceiling (MAX_PASSES = 8) is strictly enforced."""
        self.assertLessEqual(self.reasoner.max_passes_ceiling, 8)

        # Force persistent failure with constant retries
        with patch.object(self.tool_registry, "execute_tool") as mock_tool:
            mock_tool.return_value = ToolResult(success=False, verified=False, error="Persistent error")
            res = self.reasoner.reason_and_execute(
                "do task that fails persistently",
                initial_action=("system_tool", {"query": "ram"}),
            )
            self.assertLessEqual(res.passes_used, 8)
            self.assertFalse(res.verification_status)

    def test_09_zero_mcp_servers_works_gracefully(self):
        """TEST 9: DAKU operates smoothly when zero MCP servers exist."""
        empty_mcp = MCPManager(config_paths=[Path("non_existent_folder_xyz")])
        empty_mcp.discovered_servers.clear()
        empty_mcp.tool_schemas.clear()
        self.assertEqual(len(empty_mcp.discovered_servers), 0)
        tools = empty_mcp.create_mcp_tools()
        self.assertEqual(len(tools), 0)

        # Tool registry registers native tools without issues
        reg = ToolRegistry(mcp_manager=empty_mcp)
        self.assertIn("application_tool", reg.list_tool_names())
        self.assertIn("browser_tool", reg.list_tool_names())
        self.assertIn("file_tool", reg.list_tool_names())
        self.assertIn("system_tool", reg.list_tool_names())

    def test_10_existing_native_tools_continue_working(self):
        """TEST 10: Existing native tools continue working through ToolRegistry."""
        ram_res = self.tool_registry.execute_tool("system_tool", {"query": "ram"})
        self.assertTrue(ram_res.success)
        self.assertTrue(ram_res.verified)

        cpu_res = self.tool_registry.execute_tool("system_tool", {"query": "cpu"})
        self.assertTrue(cpu_res.success)
        self.assertTrue(cpu_res.verified)

    def test_11_existing_mcp_tools_continue_working(self):
        """TEST 11: Dynamic MCP tools execute and verify with simulated or real handlers."""
        def mock_handler(tool_name, args):
            return {"echo": args, "status": "ok"}

        mcp_tool = DynamicMCPTool(
            server_name="test_server",
            tool_name="test_echo",
            description="Test MCP tool",
            handler=mock_handler,
        )
        self.tool_registry.register(mcp_tool)
        res = self.tool_registry.execute_tool(mcp_tool.name, {"msg": "hello"})
        self.assertTrue(res.success)
        self.assertTrue(res.verified)

    def test_12_permission_system_remains_enforced(self):
        """TEST 12: 3-tier permission hierarchy is enforced."""
        perm = PermissionManager(auto_confirm_in_test=False)
        # Safe is pre-approved
        allowed, level, _ = perm.evaluate("system_tool", "ram", {}, PermissionLevel.SAFE)
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

        # Blocked is permanently refused
        allowed, level, msg = perm.evaluate("system_tool", "dump_credentials", {}, PermissionLevel.SAFE)
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)

    def test_13_blocked_actions_remain_blocked(self):
        """TEST 13: Dangerous operations are permanently blocked by PermissionManager."""
        allowed, level, msg = self.perm_manager.evaluate("file_tool", "delete_file", {"path": "test.txt"}, PermissionLevel.SAFE)
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)
        self.assertIn("BLOCKED", msg)

        # Also verify raw shell and arbitrary execution are blocked
        allowed2, level2, msg2 = self.perm_manager.evaluate("shell_tool", "arbitrary_shell", {}, PermissionLevel.SAFE)
        self.assertFalse(allowed2)
        self.assertEqual(level2, PermissionLevel.BLOCKED)

    def test_14_offline_mode_remains_functional(self):
        """TEST 14: Offline deterministic mode remains fully functional."""
        router = DirectModelRouter(api_key="", tool_registry=self.tool_registry)
        reply = router.process_message("hello daku")
        self.assertEqual(reply, "Hello. I'm DAKU. How can I help?")

        ram_reply = router.process_message("check ram")
        self.assertIn("RAM", ram_reply)

    def test_15_learning_records_failure(self):
        """TEST 15: LearningEngine records compact failure lesson."""
        lesson = self.learning_engine.record_failure(
            task_type="app_launch",
            failed_action="application_tool:chrome",
            failure_reason="chrome.exe not found",
            successful_alternative="application_tool:edge",
            context={"os": "win10"},
        )
        self.assertIsInstance(lesson, Lesson)
        self.assertTrue(lesson.reusable)
        self.assertEqual(lesson.successful_action, "application_tool:edge")

        found = self.learning_engine.find_failure_lesson("app_launch", "chrome")
        self.assertIsNotNone(found)
        self.assertEqual(found.lesson_id, lesson.lesson_id)

    def test_16_learning_records_success(self):
        """TEST 16: LearningEngine records compact success lesson."""
        lesson = self.learning_engine.record_success(
            task_type="browser_navigation",
            strategy_name="browser_navigation_verified",
            successful_action="browser_tool:navigate",
            context={"site": "example.com"},
        )
        self.assertIsInstance(lesson, Lesson)
        self.assertEqual(lesson.strategy_name, "browser_navigation_verified")
        self.assertEqual(len(self.learning_engine.get_lessons()), 1)

    def test_17_learned_strategy_can_be_reused(self):
        """TEST 17: Learned successful strategy can be queried and reused."""
        self.learning_engine.record_success(
            task_type="app_launch",
            strategy_name="edge_desktop_fallback",
            successful_action="application_tool:launch:edge",
            confidence=0.98,
        )
        rec = self.learning_engine.get_recommended_strategy("app_launch")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.strategy_name, "edge_desktop_fallback")
        self.assertEqual(rec.usage_count, 1)

    def test_18_secrets_never_appear_in_logs_or_lessons(self):
        """TEST 18: Secrets and API keys never appear in learning memory or logs."""
        raw_secret_data = {
            "api_key": "sk-123456789012345678901234",
            "auth_token": "Bearer my_super_secret_token_value",
            "normal_field": "safe_value",
        }
        sanitized = sanitize_data(raw_secret_data)
        self.assertEqual(sanitized["api_key"], "***REDACTED***")
        self.assertEqual(sanitized["auth_token"], "***REDACTED***")
        self.assertEqual(sanitized["normal_field"], "safe_value")

        # Masking in logger
        masked_log = self.reasoner._mask_for_logs("api_key=sk-123456789012345678901234 Bearer abcdef1234567890")
        self.assertNotIn("sk-123456789012345678901234", masked_log)
        self.assertNotIn("abcdef1234567890", masked_log)

    def test_19_memory_limits_are_enforced(self):
        """TEST 19: Bounded memory limits (MAX_LESSONS, MAX_RECENT_OBSERVATIONS) are strictly enforced."""
        small_engine = LearningEngine(max_lessons=5, storage_path=BASE_DIR / "data" / "small_lessons.json")
        small_engine.clear()
        for i in range(10):
            small_engine.record_success("task", f"strat_{i}", f"action_{i}")

        self.assertLessEqual(len(small_engine.get_lessons()), 5)
        small_engine.clear()

        # Context observations boundedness
        ctx = ReasoningContext(task_id="t1", user_request="query")
        for i in range(30):
            ctx.add_observation({"step": i})
        self.assertLessEqual(len(ctx.observations), 20)

    def test_20_no_infinite_loop_possible(self):
        """TEST 20: No infinite loop is possible even with failing, cyclic strategies."""
        with patch.object(self.tool_registry, "execute_tool") as mock_exec:
            mock_exec.return_value = ToolResult(
                success=False,
                verified=False,
                error="Loop simulated failure",
            )
            # Run reasoner
            res = self.reasoner.reason_and_execute(
                "run looping task",
                initial_action=("application_tool", {"action": "launch", "app_name": "chrome"}),
            )
            self.assertFalse(res.success)
            self.assertLessEqual(res.passes_used, 8)

    def test_21_voice_friendly_output_cleanliness(self):
        """TEST 21: ReasoningResult.to_voice_summary strips <think> tags and internal passes."""
        res = ReasoningResult(
            success=True,
            final_answer="<think>Step 1 succeeded. Step 2 verified.</think>PASS 1: Notepad is open.",
            passes_used=2,
            confidence=0.95,
            verification_status=True,
        )
        clean = res.to_voice_summary()
        self.assertNotIn("<think>", clean)
        self.assertNotIn("PASS 1", clean)
        self.assertEqual(clean, "Notepad is open.")


if __name__ == "__main__":
    unittest.main()
