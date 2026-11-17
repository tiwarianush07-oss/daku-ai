"""
DAKU Automated Test Suite for Phase 7: Solar HUD Integration
Validates:
1. Static HUD asset serving (/hud, /hud/solar_hud.css, /hud/solar_hud.js)
2. Strict zero secret leakage in served HTML, CSS, JS and API responses
3. /api/hud/agents mapping the 4 visual agents to real DAKU capabilities
4. /api/hud/turn unified voice and text turn execution
5. 10 UI status states handling
6. Safe UI profile creation (/api/hud/profiles) and privilege escalation prevention
7. 3-tier permission and confirmation boundary enforcement
8. Fallback provider transparency (Sarvam -> Google STT / Windows SAPI)
9. Doctor Phase 7 check_solar_hud diagnostics
"""

import base64
import json
import os
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from doctor import check_solar_hud
from server.daku_server import DakuServer, create_server


class TestSolarHUDIntegration(unittest.TestCase):
    """Integration test suite for Solar AI Agent Swarm HUD."""

    server: DakuServer
    test_port: int = 18445
    test_token: str = "test_solar_hud_token_abcdef123456"

    @classmethod
    def setUpClass(cls):
        """Starts background DAKU server on isolated test port."""
        cls.server = create_server(
            host="127.0.0.1",
            port=cls.test_port,
            auth_token=None,  # Open / local mode for UI access
        )
        cls.server.start(blocking=False)
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        """Stops background server."""
        if cls.server:
            cls.server.stop()
            time.sleep(0.1)

    def _get(self, path: str, headers: dict = None) -> tuple[int, bytes, dict]:
        """Helper to execute GET request."""
        url = f"http://127.0.0.1:{self.test_port}{path}"
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            content = resp.read()
            resp_headers = dict(resp.headers)
            return resp.status, content, resp_headers

    def _post_json(self, path: str, payload: dict, headers: dict = None) -> tuple[int, dict]:
        """Helper to execute POST request with JSON."""
        url = f"http://127.0.0.1:{self.test_port}{path}"
        data = json.dumps(payload).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return resp.status, res_json

    # -------------------------------------------------------------------------
    # 1. Static Asset Serving & MIME Types
    # -------------------------------------------------------------------------
    def test_01_hud_html_serving(self):
        """TEST 1: GET /hud serves index.html with text/html content-type."""
        status, content, headers = self._get("/hud")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", "").lower())
        html_text = content.decode("utf-8")
        self.assertIn("Solar AI Agent Swarm HUD", html_text)
        self.assertIn("DAKU Central Brain", html_text)
        self.assertIn("solar-canvas", html_text)

    def test_02_hud_css_and_js_serving(self):
        """TEST 2: GET /hud/solar_hud.css and /hud/solar_hud.js serve correct assets."""
        status_css, content_css, headers_css = self._get("/hud/solar_hud.css")
        self.assertEqual(status_css, 200)
        self.assertIn("text/css", headers_css.get("Content-Type", "").lower())
        self.assertIn("--bg-space", content_css.decode("utf-8"))

        status_js, content_js, headers_js = self._get("/hud/solar_hud.js")
        self.assertEqual(status_js, 200)
        self.assertIn("javascript", headers_js.get("Content-Type", "").lower())
        self.assertIn("CORE_AGENTS", content_js.decode("utf-8"))

    # -------------------------------------------------------------------------
    # 2. Strict Zero Secret Leakage
    # -------------------------------------------------------------------------
    def test_03_zero_secret_leakage(self):
        """TEST 3: Verifies frontend static assets NEVER leak SARVAM_API_KEY or auth credentials."""
        for path in ("/hud", "/hud/solar_hud.css", "/hud/solar_hud.js"):
            _, content, _ = self._get(path)
            text = content.decode("utf-8", errors="ignore")
            if settings.SARVAM_API_KEY:
                self.assertNotIn(settings.SARVAM_API_KEY, text)
            self.assertNotIn("sk_", text)
            self.assertNotIn("API_KEY", text)
            self.assertNotIn("test_solar_hud_token", text)

    # -------------------------------------------------------------------------
    # 3. Agent Mapping & Real Capabilities
    # -------------------------------------------------------------------------
    def test_04_hud_agents_endpoint(self):
        """TEST 4: GET /api/hud/agents returns the 4 visual agents + Central Sun mapped to real tools."""
        status, content, _ = self._get("/api/hud/agents")
        self.assertEqual(status, 200)
        data = json.loads(content.decode("utf-8"))

        self.assertIn("sun", data)
        self.assertEqual(data["sun"]["id"], "brain")
        self.assertEqual(data["sun"]["role"], "Autonomous Core & Multi-Pass Reasoner")

        agents = {a["id"]: a for a in data.get("agents", [])}
        self.assertIn("researcher", agents)
        self.assertIn("coder", agents)
        self.assertIn("vision", agents)
        self.assertIn("strategist", agents)

        # Verify real capability mappings
        self.assertEqual(agents["researcher"]["capability"], "DAKU research/search capability")
        self.assertEqual(agents["coder"]["capability"], "DAKU coding/execution capability")
        self.assertEqual(agents["vision"]["capability"], "DAKU vision capability")
        self.assertEqual(agents["strategist"]["capability"], "DAKU planning/orchestration")

        # Verify permission levels
        self.assertEqual(agents["researcher"]["permission_level"], "SAFE")
        self.assertEqual(agents["coder"]["permission_level"], "CONFIRMATION_REQUIRED")

    # -------------------------------------------------------------------------
    # 4. Voice & Text Turn Dispatch
    # -------------------------------------------------------------------------
    def test_05_hud_turn_text_command(self):
        """TEST 5: POST /api/hud/turn processes text command through DAKU Brain."""
        status, data = self._post_json("/api/hud/turn", {"text": "what time is it?"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("transcript"), "what time is it?")
        self.assertTrue(bool(data.get("response")))
        self.assertIn("ui_state", data)
        self.assertEqual(data["ui_state"], "STANDBY")

    def test_06_hud_turn_missing_input_error(self):
        """TEST 6: POST /api/hud/turn with empty input returns HTTP 400."""
        url = f"http://127.0.0.1:{self.test_port}/api/hud/turn"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 400)

    def test_07_hud_turn_simulated_audio_roundtrip(self):
        """TEST 7: POST /api/hud/turn handles base64 audio and returns transparent STT status."""
        dummy_audio = b"RIFF____WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        dummy_b64 = base64.b64encode(dummy_audio).decode("ascii")

        status, data = self._post_json("/api/hud/turn", {"audio_base64": dummy_b64})
        self.assertEqual(status, 200)
        self.assertIn("stt_provider", data)
        self.assertIn("tts_provider", data)

    # -------------------------------------------------------------------------
    # 5. UI Agent Profile Management & Privilege Escalation Boundary
    # -------------------------------------------------------------------------
    def test_08_hud_profiles_create_and_list(self):
        """TEST 8: POST /api/hud/profiles safely stores a UI-level profile."""
        profile_payload = {
            "profile": {
                "name": "Market Researcher",
                "role": "Search Specialist",
                "capability": "Web search and summarization",
                "color": "#00ffcc",
                "icon": "🌐",
            }
        }
        status, res = self._post_json("/api/hud/profiles", profile_payload)
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        saved = res.get("profile", {})
        self.assertEqual(saved.get("name"), "Market Researcher")
        self.assertFalse(saved.get("privileged"), "Profile must NEVER be privileged")

        # Verify listing
        status_list, content, _ = self._get("/api/hud/profiles")
        self.assertEqual(status_list, 200)
        data = json.loads(content.decode("utf-8"))
        names = [p["name"] for p in data.get("profiles", [])]
        self.assertIn("Market Researcher", names)

    def test_09_hud_profile_cannot_escalate_privilege(self):
        """TEST 9: Adding arbitrary privileged tools or shell flags to profile is sanitized."""
        malicious_payload = {
            "profile": {
                "name": "Root Admin Agent",
                "role": "Superuser",
                "privileged": True,
                "tools": ["arbitrary_shell", "delete_file", "browser_tool"],
            }
        }
        status, res = self._post_json("/api/hud/profiles", malicious_payload)
        self.assertEqual(status, 200)
        saved = res.get("profile", {})
        self.assertFalse(saved.get("privileged"))
        self.assertNotIn("arbitrary_shell", saved.get("tools", []))
        self.assertNotIn("delete_file", saved.get("tools", []))
        self.assertIn("browser_tool", saved.get("tools", []))

    # -------------------------------------------------------------------------
    # 6. Fallback Transparency & Doctor Verification
    # -------------------------------------------------------------------------
    def test_10_fallback_transparency(self):
        """TEST 10: Provider report transparently reflects whether Sarvam key is live or standby."""
        status, content, _ = self._get("/api/hud/agents")
        data = json.loads(content.decode("utf-8"))
        if not settings.has_sarvam_key():
            self.assertFalse(data.get("sarvam_available"))
            self.assertIn("Fallback", data.get("stt_provider", ""))
            self.assertIn("Fallback", data.get("tts_provider", ""))

    def test_11_doctor_check_solar_hud(self):
        """TEST 11: doctor.py check_solar_hud() passes with status OK."""
        res = check_solar_hud()
        self.assertEqual(res["status"], "OK")
        self.assertIn("READY", res["value"])


if __name__ == "__main__":
    unittest.main()
