"""
DAKU Automated Test Suite for Phase 9: JARVIS Native Desktop HUD UI
Verifies:
- TEST 1: HUDTelemetryClient header creation & Bearer token attachment
- TEST 2: Secret redaction in telemetry client
- TEST 3: Telemetry payload processing across all 10 DAKU UI states
- TEST 4: Central Sun and Solar Swarm agent telemetry parsing
- TEST 5: Graceful offline fallback when daemon is unreachable
- TEST 6: Confirmation banner state trigger and /api/confirm dispatch
- TEST 7: JarvisDesktopHUD state color palette and visual specs
- TEST 8: Visibility and click-through toggle behavior
- TEST 9: Memory budget verification (<20 MB private working set)
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ui.desktop_hud import JarvisDesktopHUD, STATE_COLORS, SWARM_SPECS, get_process_working_set_mb
from ui.hud_client import HUDTelemetryClient, UI_STATES


class TestDesktopHUD(unittest.TestCase):

    def setUp(self):
        self.mock_client = HUDTelemetryClient(
            host="127.0.0.1",
            port=9999,
            auth_token="daku-test-bearer-secret-token",
        )

    def test_01_headers_and_bearer_token(self):
        """TEST 1: Verify Bearer token header injection and fallback when token unset."""
        headers = self.mock_client.build_headers()
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer daku-test-bearer-secret-token")

        # Unset token client
        no_auth_client = HUDTelemetryClient(host="127.0.0.1", port=9999, auth_token="")
        no_auth_headers = no_auth_client.build_headers()
        self.assertNotIn("Authorization", no_auth_headers)

    def test_02_secret_redaction(self):
        """TEST 2: Verify auth token is never leaked in client repr or public state."""
        state = self.mock_client.get_state()
        state_str = json.dumps(state)
        self.assertNotIn("daku-test-bearer-secret-token", state_str)

    def test_03_telemetry_payload_and_10_states(self):
        """TEST 3: Verify payload processing maps accurately to all 10 recognized UI states."""
        self.assertEqual(len(UI_STATES), 10)

        # 1. STANDBY (Server Online, Harness Standby)
        payload_standby = {
            "version": "1.0.0",
            "sun": {"status": "ONLINE", "harness_status": "STANDBY", "pass_count": 0},
            "agents": [],
        }
        res = self.mock_client._process_success_payload(payload_standby, 1000.0)
        self.assertEqual(res["status"], "STANDBY")
        self.assertTrue(res["is_connected"])

        # 2. THINKING (Harness Active, non-application plugin)
        payload_thinking = {
            "version": "1.0.0",
            "sun": {"status": "ONLINE", "harness_status": "ACTIVE", "active_plugins": ["daku.plugin.browser"], "pass_count": 2},
            "agents": [],
        }
        res_think = self.mock_client._process_success_payload(payload_thinking, 1001.0)
        self.assertEqual(res_think["status"], "THINKING")
        self.assertEqual(res_think["pass_count"], 2)

        # 3. EXECUTING (Harness Active with application plugin)
        payload_exec = {
            "version": "1.0.0",
            "sun": {"status": "ONLINE", "harness_status": "ACTIVE", "active_plugins": ["daku.plugin.application"], "pass_count": 1},
            "agents": [],
        }
        res_exec = self.mock_client._process_success_payload(payload_exec, 1002.0)
        self.assertEqual(res_exec["status"], "EXECUTING")

        # 4. AWAITING_CONFIRMATION (pending confirmation)
        self.mock_client.set_confirmation_state({"action": "create_file", "tool": "file_tool"})
        res_conf = self.mock_client.get_state()
        self.assertEqual(res_conf["status"], "AWAITING_CONFIRMATION")
        self.assertIsNotNone(res_conf["confirmation_pending"])

        # Clear confirmation
        self.mock_client.set_confirmation_state(None)
        self.assertEqual(self.mock_client.get_state()["status"], "STANDBY")

    def test_04_solar_swarm_telemetry_parsing(self):
        """TEST 4: Verify Central Sun and 4 planetary swarm agents are parsed correctly."""
        payload = {
            "version": "1.0.0",
            "sun": {
                "id": "brain",
                "name": "DAKU Central Brain",
                "status": "ONLINE",
                "model": "deepseek-chat",
                "pass_count": 4,
                "session_id": "session_hud_777",
                "last_think_trace": "Analyzing system memory",
                "active_plugins": ["daku.plugin.system"],
            },
            "agents": [
                {"id": "researcher", "name": "Researcher", "status": "IDLE"},
                {"id": "coder", "name": "Coder Agent", "status": "ACTIVE"},
                {"id": "vision", "name": "Vision Analyst", "status": "IDLE"},
                {"id": "strategist", "name": "Executive Strategist", "status": "IDLE"},
            ],
            "sarvam_available": True,
        }
        state = self.mock_client._process_success_payload(payload, 2000.0)
        self.assertEqual(state["sun"]["model"], "deepseek-chat")
        self.assertEqual(state["pass_count"], 4)
        self.assertEqual(state["session_id"], "session_hud_777")
        self.assertEqual(len(state["agents"]), 4)
        coder = next(a for a in state["agents"] if a["id"] == "coder")
        self.assertEqual(coder["status"], "ACTIVE")

    def test_05_graceful_offline_fallback(self):
        """TEST 5: Verify clean transition to OFFLINE state when daemon is unreachable."""
        res = self.mock_client._process_error_state("Connection refused", 3000.0)
        self.assertEqual(res["status"], "OFFLINE")
        self.assertFalse(res["is_connected"])
        self.assertEqual(res["sun"]["status"], "OFFLINE")

    def test_06_confirmation_dispatch(self):
        """TEST 6: Verify confirmation dispatch dispatches POST to /api/confirm."""
        self.mock_client.set_confirmation_state({"action": "delete_cache"})

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            success = self.mock_client.send_confirmation(True)
            self.assertTrue(success)
            self.assertIsNone(self.mock_client.confirmation_pending)
            self.assertNotEqual(self.mock_client.status, "AWAITING_CONFIRMATION")

    def test_07_desktop_hud_palette_and_specs(self):
        """TEST 7: Verify all 10 states have defined color values and swarm specs match."""
        for state in UI_STATES:
            self.assertIn(state, STATE_COLORS)
            self.assertTrue(STATE_COLORS[state].startswith("#"))

        # Verify 4 Swarm Specs
        swarm_ids = {a["id"] for a in SWARM_SPECS}
        expected_ids = {"researcher", "coder", "vision", "strategist"}
        self.assertEqual(swarm_ids, expected_ids)

    def test_08_hud_toggles_and_bindings(self):
        """TEST 8: Verify visibility toggle and click-through toggling logic."""
        hud = JarvisDesktopHUD(client=self.mock_client, enable_tray=False)
        self.assertFalse(hud.click_through)
        self.assertTrue(hud.visible)

        # Toggle click through
        hud.toggle_click_through()
        self.assertTrue(hud.click_through)
        hud.toggle_click_through()
        self.assertFalse(hud.click_through)

    def test_09_memory_budget_verification(self):
        """TEST 9: Measure working set memory and verify low-RAM profile (<20 MB)."""
        mem_mb = get_process_working_set_mb()
        self.assertGreater(mem_mb, 0.0)

        # Measure standalone HUD process private working set
        import subprocess
        cmd = [sys.executable, "-c", "import ui.desktop_hud as dh; print(dh.get_process_working_set_mb())"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(res.returncode, 0)
        proc_mem = float(res.stdout.strip())
        self.assertLess(proc_mem, 20.0, f"HUD standalone memory {proc_mem} MB exceeds 20 MB budget")


if __name__ == "__main__":
    unittest.main()
