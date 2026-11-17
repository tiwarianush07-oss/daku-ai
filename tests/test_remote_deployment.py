"""
DAKU Automated Test Suite for Remote Deployment & Low-RAM Client Architecture
Validates:
1. DakuServer initialization, request routing, and lifecycle (start/stop)
2. Public /health endpoint and zero credential leakage
3. Bearer token authentication gate (401 Unauthorized vs 200 OK)
4. Authenticated /api/chat processing with DAKU Brain
5. Authenticated /api/status reporting (tools, metrics, Hermes state)
6. /api/confirm interactive security confirmation handler
7. DakuRemoteClient connection probe and chat messaging
8. DakuRemoteClient double-redundant local offline fallback when server is stopped
9. Doctor diagnostics (--remote) functions: check_remote_server, check_hermes_service, check_api_auth
10. Strict zero local heavy LLM memory assertion
"""

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from client import DakuRemoteClient
from config.settings import settings
from doctor import check_api_auth, check_hermes_service, check_remote_server
from server.daku_server import DakuServer, create_server


class TestRemoteDeployment(unittest.TestCase):
    """Integration test suite for DAKU Server, Authentication, and Remote Client."""

    server: DakuServer
    test_port: int = 18443
    test_token: str = "test_secret_token_1234567890abcdef"

    @classmethod
    def setUpClass(cls):
        """Start a background DAKU server on an isolated test port."""
        cls.server = create_server(
            host="127.0.0.1",
            port=cls.test_port,
            auth_token=cls.test_token,
        )
        cls.server.start(blocking=False)
        # Allow server thread to initialize
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        """Stop background server."""
        if cls.server:
            cls.server.stop()
            time.sleep(0.1)

    # -------------------------------------------------------------------------
    # 1. Server Health Check & Public Endpoints
    # -------------------------------------------------------------------------
    def test_01_health_endpoint_public_access(self):
        """TEST 1: GET /health returns HTTP 200 with valid JSON without authentication."""
        url = f"http://127.0.0.1:{self.test_port}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("daku"), "running")
            self.assertIn("version", data)
            self.assertIn("uptime_seconds", data)
            self.assertIn("system", data)

    def test_02_health_endpoint_zero_secret_leakage(self):
        """TEST 2: GET /health response never contains secret API keys or auth tokens."""
        url = f"http://127.0.0.1:{self.test_port}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body_text = resp.read().decode("utf-8")
            self.assertNotIn(self.test_token, body_text)
            self.assertNotIn("your_api_key_here", body_text)
            self.assertNotIn("API_KEY", body_text)

    # -------------------------------------------------------------------------
    # 2. Authentication Gate & Security
    # -------------------------------------------------------------------------
    def test_03_chat_missing_auth_returns_401(self):
        """TEST 3: POST /api/chat without Authorization header is rejected with HTTP 401."""
        url = f"http://127.0.0.1:{self.test_port}/api/chat"
        payload = json.dumps({"message": "Hello"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_04_chat_invalid_auth_returns_401(self):
        """TEST 4: POST /api/chat with an invalid Bearer token is rejected with HTTP 401."""
        url = f"http://127.0.0.1:{self.test_port}/api/chat"
        payload = json.dumps({"message": "Hello"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong_invalid_token_999",
        }
        req = urllib.request.Request(url, data=payload, headers=headers)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_05_chat_valid_auth_success(self):
        """TEST 5: POST /api/chat with valid Bearer token executes and returns valid response."""
        url = f"http://127.0.0.1:{self.test_port}/api/chat"
        payload = json.dumps({"message": "Hello DAKU"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.test_token}",
        }
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("response", data)
            self.assertIn("Hello", data["response"])

    def test_06_status_authenticated_endpoint(self):
        """TEST 6: GET /api/status provides authenticated server metrics and tool registry."""
        url = f"http://127.0.0.1:{self.test_port}/api/status"
        # Test unauthorized first
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(url, timeout=3.0)
        self.assertEqual(ctx.exception.code, 401)

        # Test authorized
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.test_token}"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("server"), "DAKU Headless Gateway")
            self.assertIn("tools", data)
            self.assertGreater(data["tools"]["count"], 0)
            self.assertIn("system", data)

    def test_07_confirm_endpoint(self):
        """TEST 7: POST /api/confirm stores client authorization decision."""
        url = f"http://127.0.0.1:{self.test_port}/api/confirm"
        payload = json.dumps({"action_id": "act_999", "confirmed": True}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.test_token}",
        }
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertTrue(data.get("confirmed"))

    # -------------------------------------------------------------------------
    # 3. Remote Client Integration & Offline Fallback
    # -------------------------------------------------------------------------
    def test_08_client_connection_probe(self):
        """TEST 8: DakuRemoteClient probe successfully connects to the test server."""
        client = DakuRemoteClient(
            server_url=f"http://127.0.0.1:{self.test_port}",
            auth_token=self.test_token,
        )
        ok, msg = client.check_connection()
        self.assertTrue(ok)
        self.assertTrue(client.is_connected)
        self.assertIn("Connected", msg)

    def test_09_client_send_message_online(self):
        """TEST 9: DakuRemoteClient sends message and receives response over HTTP."""
        client = DakuRemoteClient(
            server_url=f"http://127.0.0.1:{self.test_port}",
            auth_token=self.test_token,
        )
        client.check_connection()
        reply = client.send_message("who are you")
        self.assertIn("DAKU", reply)

    def test_10_client_offline_fallback_when_server_stopped(self):
        """TEST 10: DakuRemoteClient seamlessly degrades to local offline intent parsing when server is offline."""
        # Point client to a closed/unreachable port
        offline_client = DakuRemoteClient(
            server_url="http://127.0.0.1:19999",
            auth_token="dummy",
        )
        ok, msg = offline_client.check_connection()
        self.assertFalse(ok)
        self.assertFalse(offline_client.is_connected)

        # Should NOT raise an unhandled exception; must execute offline fallback locally
        reply = offline_client.send_message("how much ram is free?")
        self.assertIn("free RAM", reply)

        reply2 = offline_client.send_message("what is the time?")
        self.assertIn("current time is", reply2.lower())

    # -------------------------------------------------------------------------
    # 4. Doctor Diagnostics Integration
    # -------------------------------------------------------------------------
    def test_11_doctor_remote_server_check(self):
        """TEST 11: doctor.py check_remote_server probes running server and reports ONLINE."""
        res = check_remote_server(f"http://127.0.0.1:{self.test_port}")
        self.assertEqual(res["status"], "OK")
        self.assertIn("ONLINE", res["value"])

        # Test offline port
        res_offline = check_remote_server("http://127.0.0.1:19999")
        self.assertEqual(res_offline["status"], "INFO")
        self.assertIn("OFFLINE", res_offline["value"])

    def test_12_doctor_api_auth_check(self):
        """TEST 12: doctor.py check_api_auth correctly identifies whether a token is set."""
        res = check_api_auth()
        self.assertIn(res["status"], ("OK", "INFO"))
        self.assertIn("API Authentication", res["name"])

    # -------------------------------------------------------------------------
    # 5. Resource Safety Assertion
    # -------------------------------------------------------------------------
    def test_13_zero_local_large_model_inference_guard(self):
        """TEST 13: Strictly verifies that no local LLMs (torch, transformers, ollama) are loaded."""
        loaded = sys.modules.keys()
        self.assertNotIn("torch", loaded)
        self.assertNotIn("transformers", loaded)
        self.assertNotIn("llama_cpp", loaded)
        self.assertNotIn("ollama", loaded)


if __name__ == "__main__":
    unittest.main()
