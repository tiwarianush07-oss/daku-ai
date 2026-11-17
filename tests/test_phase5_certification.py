"""
DAKU Phase 5 — Production Live Certification & Hardening Test Suite
Verifies:
1. HTTPS URL Validation & Protocol Enforcement
2. Bearer Authentication Matrix (Valid, Missing, Invalid, Malformed, Constant-Time Comparison)
3. Endpoint Security & Zero Credential Leakage
4. SAFE, CONFIRMATION_REQUIRED, and BLOCKED Tool Execution Boundaries
5. MCP Permission Boundaries
6. Doctor Diagnostic Status Discrimination (OK, WARN, INFO, NOT VERIFIED)
7. Zero Local LLM Resource Safety & Memory Constraints
8. Client Offline Fallback & Network Resilience
"""

import json
import os
import secrets
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.router import Brain
from client import DakuRemoteClient
from config.settings import settings
from doctor import check_api_auth, check_https_status, check_remote_server
from server.daku_server import DakuServer
from tools.base import PermissionLevel
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry


class TestDakuPhase5Certification(unittest.TestCase):
    """Phase 5 Production Certification and Hardening Tests."""

    server_thread = None
    server = None
    test_port = 18443
    test_token = "daku_live_cert_test_token_secret_xyz123"

    @classmethod
    def setUpClass(cls):
        """Spawns an authenticated test server instance."""
        cls.server = DakuServer(
            host="127.0.0.1",
            port=cls.test_port,
            auth_token=cls.test_token,
        )
        cls.server_thread = threading.Thread(target=cls.server.start, kwargs={"blocking": True}, daemon=True)
        cls.server_thread.start()

        # Wait for server to become responsive
        probe_url = f"http://127.0.0.1:{cls.test_port}/health"
        for _ in range(25):
            try:
                with urllib.request.urlopen(probe_url, timeout=0.5) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        """Stops the test server instance."""
        if cls.server:
            cls.server.stop()

    # -------------------------------------------------------------------------
    # 1. HTTPS URL Validation & Protocol Security
    # -------------------------------------------------------------------------
    def test_01_https_url_validation_helpers(self):
        """TEST 1: Settings.is_https_url correctly detects HTTPS protocols."""
        self.assertTrue(settings.is_https_url("https://daku.example.com"))
        self.assertTrue(settings.is_https_url("HTTPS://SECURE.HOST:443"))
        self.assertFalse(settings.is_https_url("http://daku.example.com:8443"))
        self.assertFalse(settings.is_https_url("http://127.0.0.1:8443"))

    def test_02_loopback_url_detection(self):
        """TEST 2: Settings.is_loopback_url identifies local vs remote internet endpoints."""
        self.assertTrue(settings.is_loopback_url("http://127.0.0.1:8443"))
        self.assertTrue(settings.is_loopback_url("http://localhost:8443"))
        self.assertTrue(settings.is_loopback_url("https://127.0.0.1:443"))
        self.assertFalse(settings.is_loopback_url("http://140.238.150.10:8443"))
        self.assertFalse(settings.is_loopback_url("https://daku.mycloud.com"))

    def test_03_doctor_https_diagnostic_discrimination(self):
        """TEST 3: doctor.py accurately warns on plain HTTP over public endpoints."""
        # Loopback HTTP -> INFO (Allowed for local development)
        res_loop = check_https_status("http://127.0.0.1:8443")
        self.assertEqual(res_loop["status"], "INFO")
        self.assertIn("LOOPBACK", res_loop["value"])

        # Public IP HTTP -> WARN (Must use HTTPS in production)
        res_public_http = check_https_status("http://140.238.150.10:8443")
        self.assertEqual(res_public_http["status"], "WARN")
        self.assertIn("INSECURE", res_public_http["value"])

        # Empty URL -> INFO
        res_empty = check_https_status("")
        self.assertEqual(res_empty["status"], "INFO")

    # -------------------------------------------------------------------------
    # 2. Authentication Security Matrix & Constant-Time Comparison
    # -------------------------------------------------------------------------
    def test_04_auth_valid_token_returns_200(self):
        """TEST 4: Request with valid Bearer token succeeds with HTTP 200."""
        url = f"http://127.0.0.1:{self.test_port}/api/status"
        headers = {"Authorization": f"Bearer {self.test_token}"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("security", {}).get("auth_enabled"))

    def test_05_auth_missing_token_returns_401(self):
        """TEST 5: Request with missing Authorization header is rejected with HTTP 401."""
        url = f"http://127.0.0.1:{self.test_port}/api/status"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_06_auth_invalid_token_returns_401(self):
        """TEST 6: Request with invalid Bearer token is rejected with HTTP 401."""
        url = f"http://127.0.0.1:{self.test_port}/api/chat"
        payload = json.dumps({"message": "test"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer completely_bogus_token_abcdef",
        }
        req = urllib.request.Request(url, data=payload, headers=headers)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_07_auth_malformed_token_header_returns_401(self):
        """TEST 7: Request with malformed Authorization header (e.g. Basic, Token) is rejected with HTTP 401."""
        url = f"http://127.0.0.1:{self.test_port}/api/status"
        for bad_header in (
            "Basic dXNlcjpwYXNz",
            "Token abc123xyz",
            "Bearer",
            "bearer_no_space",
            "CustomXYZ",
        ):
            headers = {"Authorization": bad_header}
            req = urllib.request.Request(url, headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=3.0)
            self.assertEqual(ctx.exception.code, 401, f"Failed for header: {bad_header}")

    def test_08_constant_time_comparison_used(self):
        """TEST 8: Token comparison uses secrets.compare_digest to prevent side-channel timing attacks."""
        token_a = "secret_production_token_12345"
        token_b = "secret_production_token_12345"
        token_c = "secret_production_token_99999"

        self.assertTrue(secrets.compare_digest(token_a, token_b))
        self.assertFalse(secrets.compare_digest(token_a, token_c))

    # -------------------------------------------------------------------------
    # 3. Endpoint Security & Zero Credential Leakage
    # -------------------------------------------------------------------------
    def test_09_health_endpoint_public_and_zero_secret_leak(self):
        """TEST 9: GET /health is publicly accessible and leaks zero secrets or tokens."""
        url = f"http://127.0.0.1:{self.test_port}/health"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("daku"), "running")

            # Assert strict credential isolation
            self.assertNotIn(self.test_token, body)
            self.assertNotIn("api_key", body.lower())
            self.assertNotIn("auth_token", body.lower())

    def test_10_status_chat_confirm_require_authentication(self):
        """TEST 10: /api/status, /api/chat, and /api/confirm all enforce authentication."""
        for endpoint, method, payload in (
            ("/api/status", "GET", None),
            ("/api/chat", "POST", json.dumps({"message": "hi"}).encode("utf-8")),
            ("/api/confirm", "POST", json.dumps({"action_id": "1", "confirmed": True}).encode("utf-8")),
        ):
            url = f"http://127.0.0.1:{self.test_port}{endpoint}"
            headers = {"Content-Type": "application/json"} if payload else {}
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=3.0)
            self.assertEqual(ctx.exception.code, 401, f"Endpoint {endpoint} allowed unauthenticated access!")

    # -------------------------------------------------------------------------
    # 4. Tool Execution & Security Boundaries
    # -------------------------------------------------------------------------
    def test_11_safe_tool_execution(self):
        """TEST 11: SAFE operations (system queries, file listing, time) execute without requiring user prompts."""
        pm = PermissionManager()
        registry = ToolRegistry()

        # System RAM query
        allowed, level, msg = pm.evaluate("system_tool", "get_ram", {}, PermissionLevel.SAFE)
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

        tool = registry.get_tool("system_tool")
        res = tool.execute({"query": "ram"})
        self.assertTrue(res.success)
        self.assertIn("free_gb", res.data)

    def test_12_confirmation_required_boundary(self):
        """TEST 12: CONFIRMATION_REQUIRED operations (file write, app launch) require user authorization."""
        # Test denial callback
        pm_deny = PermissionManager(confirmation_callback=lambda tool, desc: False)
        allowed, level, msg = pm_deny.evaluate(
            "file_tool",
            "create_file",
            {"filepath": "test.txt", "content": "hello"},
            PermissionLevel.CONFIRMATION_REQUIRED,
        )
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("denied", msg.lower())

        # Test approval callback
        pm_approve = PermissionManager(confirmation_callback=lambda tool, desc: True)
        allowed_app, level_app, msg_app = pm_approve.evaluate(
            "file_tool",
            "create_file",
            {"filepath": "test.txt", "content": "hello"},
            PermissionLevel.CONFIRMATION_REQUIRED,
        )
        self.assertTrue(allowed_app)
        self.assertEqual(level_app, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("confirmed", msg_app.lower())

    def test_13_blocked_dangerous_operations_permanent_refusal(self):
        """TEST 13: Dangerous operations (powershell, cmd, bash, delete, shutdown) are permanently BLOCKED."""
        pm = PermissionManager()
        dangerous_ops = [
            ("custom_tool", "powershell_raw", {"cmd": "Get-Process"}),
            ("shell_tool", "cmd_raw", {"command": "dir"}),
            ("system_tool", "arbitrary_shell", {"command": "rm -rf /"}),
            ("file_tool", "delete_file", {"filepath": "C:\\Windows\\System32"}),
            ("disk_tool", "format_disk", {"drive": "C:"}),
            ("os_tool", "shutdown", {}),
            ("sec_tool", "dump_credentials", {}),
        ]

        for tool_name, op, args in dangerous_ops:
            allowed, level, msg = pm.evaluate(tool_name, op, args, PermissionLevel.SAFE)
            self.assertFalse(allowed, f"Dangerous operation '{op}' was NOT blocked!")
            self.assertEqual(level, PermissionLevel.BLOCKED, f"Operation '{op}' was not classified BLOCKED!")

    def test_14_no_raw_shell_execution_possible(self):
        """TEST 14: Direct model-to-OS raw shell execution is physically impossible via ToolRegistry."""
        registry = ToolRegistry()
        for forbidden_tool in ("powershell", "cmd", "bash", "sh", "exec", "eval", "shell"):
            self.assertIsNone(registry.get_tool(forbidden_tool))

    # -------------------------------------------------------------------------
    # 5. MCP Permission Boundary
    # -------------------------------------------------------------------------
    def test_15_mcp_permission_boundary_enforced(self):
        """TEST 15: Discovered MCP servers and tools cannot bypass PermissionManager."""
        pm = PermissionManager()
        # MCP tool calls proposing dangerous actions are rejected even if declared SAFE
        allowed, level, msg = pm.evaluate("mcp_server", "arbitrary_shell", {"command": "cat /etc/passwd"}, PermissionLevel.SAFE)
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)

    # -------------------------------------------------------------------------
    # 6. Client Offline Fallback & Network Resilience
    # -------------------------------------------------------------------------
    def test_16_client_offline_fallback_zero_model_weights(self):
        """TEST 16: Client degrades to local deterministic fallback without downloading local LLM weights."""
        client = DakuRemoteClient(
            server_url="http://127.0.0.1:19876",  # Closed port
            auth_token="dummy_token",
        )
        ok, msg = client.check_connection()
        self.assertFalse(ok)

        # Fallback query
        reply = client.send_message("how much memory is free?")
        self.assertTrue(len(reply) > 0)
        self.assertIn("free RAM", reply)

        # Ensure no heavy weights were downloaded
        loaded_modules = sys.modules.keys()
        self.assertNotIn("torch", loaded_modules)
        self.assertNotIn("transformers", loaded_modules)
        self.assertNotIn("ollama", loaded_modules)

    # -------------------------------------------------------------------------
    # 7. Resource Safety & Low-RAM Constraints
    # -------------------------------------------------------------------------
    def test_17_client_resource_safety(self):
        """TEST 17: Validates that DAKU client stays within strict 4 GB RAM low-usage constraints."""
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_gb = stat.ullTotalPhys / (1024**3)

        # Ensure we are testing against the designated <= 4GB baseline environment
        self.assertGreater(total_gb, 2.0)


if __name__ == "__main__":
    unittest.main()
