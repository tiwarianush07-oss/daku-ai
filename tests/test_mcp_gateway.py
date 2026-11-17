"""
Unit Tests for Phase 8: MCP Permission Gateway Hardening
Validates:
- Declarative per-server ACL loading
- Fallback for unknown MCP servers (CONFIRMATION_REQUIRED)
- Per-tool policy evaluation (SAFE, CONFIRMATION_REQUIRED, BLOCKED)
- Token isolation boundary: environment scrubbing of sensitive API keys
- Token-bucket rate limiting and burst handling
- DeepSeek Harness bridge integration with MCP Gateway & Memory Audit Log
"""

import json
import os
import tempfile
import time
import unittest

from brain.deepseek_harness_bridge import DeepSeekHarnessBridge
from brain.mcp_gateway import MCPPermissionGateway, TokenBucket
from brain.memory_store import MemoryStore, MemoryTier
from tools.base import PermissionLevel


class TestMCPGateway(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.acl_path = os.path.join(self.temp_dir.name, "test_mcp_acl.json")
        self.sample_acl = {
            "default_policy": "CONFIRMATION_REQUIRED",
            "forbidden_env_keys": [
                "MODEL_API_KEY",
                "SARVAM_API_KEY",
                "DAKU_AUTH_TOKEN",
                "SECRET_KEY",
            ],
            "servers": {
                "safe_server": {
                    "default_policy": "SAFE",
                    "tools": {
                        "read_docs": "SAFE",
                        "admin_action": "BLOCKED",
                    },
                    "allowed_env_keys": ["SAFE_PUBLIC_CONFIG", "CUSTOM_ALLOWED_VAR"],
                    "rate_limit_per_minute": 60,
                    "burst_size": 2,
                },
                "strict_server": {
                    "default_policy": "CONFIRMATION_REQUIRED",
                    "tools": {
                        "risky_exec": "CONFIRMATION_REQUIRED",
                        "wipe_all": "BLOCKED",
                    },
                    "allowed_env_keys": [],
                    "rate_limit_per_minute": 10,
                    "burst_size": 1,
                },
            },
        }
        with open(self.acl_path, "w", encoding="utf-8") as f:
            json.dump(self.sample_acl, f)

        self.gateway = MCPPermissionGateway(acl_path=self.acl_path, auto_confirm_in_test=True)
        self.gateway.reset_rate_limits()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_unknown_server_defaults_to_confirmation(self):
        """Unknown servers should default to CONFIRMATION_REQUIRED per Phase 8 security law."""
        effective_level, decl_reason = self.gateway.get_effective_permission(
            server_name="unknown_ext_server",
            tool_name="random_tool",
        )
        self.assertEqual(effective_level, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("Unknown MCP server", decl_reason)

        allowed, level, reason = self.gateway.evaluate_mcp_tool(
            server_name="unknown_ext_server",
            tool_name="random_tool",
            arguments={},
        )
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)

    def test_server_and_tool_rules(self):
        """Verify explicit SAFE, CONFIRMATION_REQUIRED, and BLOCKED evaluation."""
        # SAFE tool
        allowed, level, _ = self.gateway.evaluate_mcp_tool(
            server_name="safe_server",
            tool_name="read_docs",
            arguments={},
        )
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

        # BLOCKED tool
        allowed, level, reason = self.gateway.evaluate_mcp_tool(
            server_name="safe_server",
            tool_name="admin_action",
            arguments={},
        )
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)
        self.assertIn("blocked", reason.lower())

        # CONFIRMATION_REQUIRED tool
        allowed, level, _ = self.gateway.evaluate_mcp_tool(
            server_name="strict_server",
            tool_name="risky_exec",
            arguments={},
        )
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)

    def test_token_isolation_scrub_environment(self):
        """Verify token boundary strictly strips sensitive credentials from child process env."""
        raw_env = {
            "PATH": "/usr/bin;C:\\Windows",
            "MODEL_API_KEY": "sk-deepseek-topsecret-999",
            "SARVAM_API_KEY": "sarvam-live-token-123",
            "DAKU_AUTH_TOKEN": "daku-master-auth-xyz",
            "SAFE_PUBLIC_CONFIG": "allowlisted_value",
            "CUSTOM_ALLOWED_VAR": "custom_val",
            "RANDOM_UNSAFE_VAR": "drop_this",
        }

        # For safe_server (SAFE_PUBLIC_CONFIG & CUSTOM_ALLOWED_VAR allowed, PATH is harmless system)
        scrubbed = self.gateway.scrub_environment("safe_server", raw_env)
        self.assertNotIn("MODEL_API_KEY", scrubbed)
        self.assertNotIn("SARVAM_API_KEY", scrubbed)
        self.assertNotIn("DAKU_AUTH_TOKEN", scrubbed)
        self.assertNotIn("RANDOM_UNSAFE_VAR", scrubbed)
        self.assertEqual(scrubbed.get("PATH"), "/usr/bin;C:\\Windows")
        self.assertEqual(scrubbed.get("SAFE_PUBLIC_CONFIG"), "allowlisted_value")
        self.assertEqual(scrubbed.get("CUSTOM_ALLOWED_VAR"), "custom_val")

        # For strict_server (no allowed keys)
        scrubbed_strict = self.gateway.scrub_environment("strict_server", raw_env)
        self.assertNotIn("MODEL_API_KEY", scrubbed_strict)
        self.assertNotIn("SARVAM_API_KEY", scrubbed_strict)
        self.assertNotIn("DAKU_AUTH_TOKEN", scrubbed_strict)
        self.assertNotIn("SAFE_PUBLIC_CONFIG", scrubbed_strict)
        self.assertEqual(scrubbed_strict.get("PATH"), "/usr/bin;C:\\Windows")

    def test_rate_limiter_burst_and_recovery(self):
        """Verify token-bucket rate limiter enforces ceilings."""
        bucket = TokenBucket(rate_per_minute=60, burst_capacity=2)  # 1 token/sec, max 2
        # First 2 should succeed
        allowed1, _ = bucket.consume(1)
        allowed2, _ = bucket.consume(1)
        self.assertTrue(allowed1)
        self.assertTrue(allowed2)
        # 3rd immediate call should be rejected
        allowed3, wait_time = bucket.consume(1)
        self.assertFalse(allowed3)
        self.assertGreater(wait_time, 0)

        # Test gateway rate limiting rejection
        # safe_server has burst_size=2
        res1, _, _ = self.gateway.evaluate_mcp_tool("safe_server", "read_docs")
        res2, _, _ = self.gateway.evaluate_mcp_tool("safe_server", "read_docs")
        res3, level, reason = self.gateway.evaluate_mcp_tool("safe_server", "read_docs")

        self.assertTrue(res1)
        self.assertTrue(res2)
        self.assertFalse(res3)
        self.assertEqual(level, PermissionLevel.BLOCKED)
        self.assertIn("Rate limit exceeded", reason)

    def test_deepseek_harness_bridge_integration(self):
        """Verify DeepSeekHarnessBridge enforces Phase 8 gateway and logs to MemoryStore."""
        memory_store = MemoryStore(db_path=":memory:")
        bridge = DeepSeekHarnessBridge(
            mcp_gateway=self.gateway,
            memory_store=memory_store,
        )
        session = bridge.create_session("test_session_p8")

        # Call blocked MCP tool through bridge
        # Tool format: mcp_{server_name}_{tool_name}
        cmd_result = bridge.dispatch_tool_call(
            tool_name="mcp_safe_server_admin_action",
            arguments={"query": "test"},
            session_id=session.session_id,
        )
        self.assertEqual(cmd_result.kind, "error")
        self.assertEqual(cmd_result.outcome, "rejected")
        self.assertEqual(cmd_result.permission_level, "BLOCKED")

        # Check session event log
        event_types = [e.get("type") for e in session.event_log]
        self.assertIn("tool/mcp_blocked", event_types)

        # Check MemoryStore audit log tier
        audit_entries = memory_store.list_entries(user_id="system", tier=MemoryTier.SECURITY_AUDIT_LOG)
        self.assertGreaterEqual(len(audit_entries), 1)
        self.assertIn("MCP Gate Blocked", audit_entries[0]["content"])
        self.assertEqual(audit_entries[0]["metadata"].get("server"), "safe_server")

        memory_store.close()


if __name__ == "__main__":
    unittest.main()
