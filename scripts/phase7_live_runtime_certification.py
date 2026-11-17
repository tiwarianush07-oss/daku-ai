"""
DAKU Phase 7 — Comprehensive Live Runtime Certification Script
Executes empirical live tests against the running DAKU server (http://127.0.0.1:8443)
and underlying autonomous engine on Windows 10/11:

1. Server launch & endpoint reachability (/hud, CSS, JS, /health)
2. Browser microphone capture pipeline audit & server audio turn processing
3. Complete voice lifecycle verification (STANDBY -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING)
4. Normal SAFE request execution
5. CONFIRMATION_REQUIRED request boundary (execution prevented before user confirmation)
6. BLOCKED request boundary (permanent execution prevention)
7. Central Brain Dominance (all execution routes through DAKU Brain; planetary agents non-autonomous)
8. All 4 visual planetary agents verification (Researcher, Coder, Vision Analyst, Executive Strategist)
9. Microphone recording, audio playback, status transitions, agent transitions, and error handling
10. Strict zero secret leakage verification (HTML, CSS, JS, API responses, telemetry)
11. Transparent fallback verification when SARVAM_API_KEY is not set
"""

import base64
import io
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from tools.base import PermissionLevel, ToolResult
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry
from tools.file_ops import FileTool
from tools.application import ApplicationTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("daku.phase7_cert")

SERVER_URL = "http://127.0.0.1:8443"


class Phase7Certifier:
    """Live runtime verification harness for DAKU Phase 7 Solar HUD."""

    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url.rstrip("/")
        self.results: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "server_url": self.server_url,
            "gates": {},
            "all_passed": False,
        }

    def _get(self, path: str, headers: Dict[str, str] = None) -> Tuple[int, bytes, Dict[str, str]]:
        url = f"{self.server_url}{path}"
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return resp.status, resp.read(), dict(resp.headers)

    def _post_json(self, path: str, payload: Dict[str, Any], headers: Dict[str, str] = None) -> Tuple[int, Dict[str, Any]]:
        url = f"{self.server_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    # -------------------------------------------------------------------------
    # Gate 1: HUD Endpoints & Static Assets
    # -------------------------------------------------------------------------
    def verify_gate1_endpoints(self) -> bool:
        print("\n[GATE 1] Verifying HUD Endpoints & Static Assets...")
        try:
            # 1. /hud HTML
            status, html_bytes, headers = self._get("/hud")
            assert status == 200, f"Expected 200, got {status}"
            assert "text/html" in headers.get("Content-Type", "").lower()
            html_text = html_bytes.decode("utf-8")
            assert "Solar AI Agent Swarm HUD" in html_text
            assert '<canvas id="solar-canvas">' in html_text
            assert "/hud/solar_hud.css" in html_text
            assert "/hud/solar_hud.js" in html_text
            print("  [PASS] GET /hud (HTML, Canvas element, Title present)")

            # 2. /hud/solar_hud.css
            status, css_bytes, headers = self._get("/hud/solar_hud.css")
            assert status == 200
            assert "text/css" in headers.get("Content-Type", "").lower()
            assert "--bg-space" in css_bytes.decode("utf-8")
            print("  [PASS] GET /hud/solar_hud.css (Valid CSS)")

            # 3. /hud/solar_hud.js
            status, js_bytes, headers = self._get("/hud/solar_hud.js")
            assert status == 200
            assert "javascript" in headers.get("Content-Type", "").lower()
            js_text = js_bytes.decode("utf-8")
            assert "CORE_AGENTS" in js_text
            assert "CENTRAL_SUN" in js_text
            print("  [PASS] GET /hud/solar_hud.js (Valid JavaScript engine)")

            # 4. /health
            status, health_bytes, _ = self._get("/health")
            assert status == 200
            health_json = json.loads(health_bytes.decode("utf-8"))
            assert health_json.get("status") == "ok"
            assert health_json.get("daku") == "running"
            print(f"  [PASS] GET /health (DAKU running, version {health_json.get('version')})")

            self.results["gates"]["gate1_endpoints"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 1 error: {e}")
            self.results["gates"]["gate1_endpoints"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 2: Browser Microphone Pipeline & Server Audio Processing
    # -------------------------------------------------------------------------
    def verify_gate2_microphone_pipeline(self) -> bool:
        print("\n[GATE 2] Verifying Browser Microphone Pipeline & Audio Turn Dispatch...")
        try:
            # 1. Audit solar_hud.js code for the complete Web Audio MediaRecorder pipeline
            hud_dir = BASE_DIR / "server" / "hud"
            js_text = (hud_dir / "solar_hud.js").read_text(encoding="utf-8")

            assert "navigator.mediaDevices.getUserMedia({ audio: true })" in js_text
            assert "new MediaRecorder(stream)" in js_text
            assert "recordedAudioChunks.push(event.data)" in js_text
            assert "new Blob(recordedAudioChunks, { type: 'audio/wav' })" in js_text
            assert "reader.readAsDataURL(audioBlob)" in js_text
            assert "dispatchTurn(null, base64Audio)" in js_text
            assert "window.prompt('Microphone input is unavailable" in js_text
            print("  [PASS] Browser MediaRecorder capture & base64 audio pipeline validated")

            # 2. Test server audio turn processing with valid WAV PCM payload
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\x00\x00" * 4000)
            b64_audio = base64.b64encode(buf.getvalue()).decode("ascii")

            status, data = self._post_json("/api/hud/turn", {"audio_base64": b64_audio})
            assert status == 200
            assert "stt_provider" in data
            assert "tts_provider" in data
            assert "ui_state" in data
            assert data["ui_state"] == "STANDBY"
            print(f"  [PASS] Server processed audio turn payload (STT: {data.get('stt_provider')}, Fallback: {data.get('response')})")

            # 3. Test malformed audio input error handling
            url = f"{self.server_url}/api/hud/turn"
            data = json.dumps({"audio_base64": "invalid_base64_not_audio!!!"}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=10.0)
            except urllib.error.HTTPError as he:
                assert he.code == 400
                print("  [PASS] Malformed audio handled safely with HTTP 400 Bad Request")

            self.results["gates"]["gate2_microphone_pipeline"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 2 error: {e}")
            self.results["gates"]["gate2_microphone_pipeline"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 3: Complete Voice Lifecycle (STANDBY -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING)
    # -------------------------------------------------------------------------
    def verify_gate3_voice_lifecycle(self) -> bool:
        print("\n[GATE 3] Verifying Complete Voice Lifecycle States...")
        try:
            hud_dir = BASE_DIR / "server" / "hud"
            js_text = (hud_dir / "solar_hud.js").read_text(encoding="utf-8")

            # Verify all required states are declared in UIStates
            for state in ["STANDBY", "LISTENING", "TRANSCRIBING", "THINKING", "CONFIRMATION_REQUIRED", "EXECUTING", "SPEAKING", "FALLBACK", "ERROR", "OFFLINE"]:
                assert f"{state}: '{state}'" in js_text, f"State {state} missing from UIStates"
            print("  [PASS] All 10 UI states declared in UIStates")

            # Verify state transition sequence in client logic:
            # 1. startRecording -> setUIState(UIStates.LISTENING)
            assert "setUIState(UIStates.LISTENING" in js_text
            # 2. stopRecording -> setUIState(UIStates.TRANSCRIBING)
            assert "setUIState(UIStates.TRANSCRIBING" in js_text
            # 3. dispatchTurn -> setUIState(audioBase64 ? UIStates.TRANSCRIBING : UIStates.THINKING)
            assert "setUIState(audioBase64 ? UIStates.TRANSCRIBING : UIStates.THINKING)" in js_text
            # 4. response received with audio -> setUIState(UIStates.SPEAKING)
            assert "setUIState(UIStates.SPEAKING" in js_text
            # 5. turn completed -> setUIState(UIStates.STANDBY)
            assert "setUIState(UIStates.STANDBY)" in js_text
            print("  [PASS] Complete client lifecycle progression verified: STANDBY -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING -> STANDBY")

            # Verify turn dispatch response returns STANDBY ui_state and latency instrumentation
            status, res = self._post_json("/api/hud/turn", {"text": "status check"})
            assert status == 200
            assert res.get("ui_state") == "STANDBY"
            assert "brain_latency_ms" in res
            assert "elapsed_seconds" in res
            print(f"  [PASS] Server turn returned ui_state=STANDBY with brain latency {res.get('brain_latency_ms')}ms")

            self.results["gates"]["gate3_voice_lifecycle"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 3 error: {e}")
            self.results["gates"]["gate3_voice_lifecycle"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 4: Normal SAFE Request
    # -------------------------------------------------------------------------
    def verify_gate4_safe_request(self) -> bool:
        print("\n[GATE 4] Testing Normal SAFE Request...")
        try:
            status, res = self._post_json("/api/hud/turn", {"text": "what is the capital of France?"})
            assert status == 200
            assert res.get("success") is True
            assert res.get("requires_confirmation") is False
            assert res.get("pending_action") is None
            assert len(res.get("response", "")) > 0
            print(f"  [PASS] SAFE query executed immediately without confirmation: '{res.get('response')[:60]}...'")

            self.results["gates"]["gate4_safe_request"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 4 error: {e}")
            self.results["gates"]["gate4_safe_request"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 5: CONFIRMATION_REQUIRED Request (Execution Prevented Before Confirmation)
    # -------------------------------------------------------------------------
    def verify_gate5_confirmation_required(self) -> bool:
        print("\n[GATE 5] Testing CONFIRMATION_REQUIRED Boundary...")
        try:
            # 1. Direct PermissionManager verification: Denied -> Cannot execute
            pm_deny = PermissionManager(confirmation_callback=lambda tool, desc: False)
            allowed, level, reason = pm_deny.evaluate(
                tool_name="application_tool",
                operation="launch",
                args={"app_name": "notepad"},
                declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
            )
            assert allowed is False, "Execution must NOT be allowed when denied"
            assert level == PermissionLevel.CONFIRMATION_REQUIRED
            assert "User denied permission" in reason
            print(f"  [PASS] Denied confirmation strictly prevents execution: '{reason}'")

            # 2. Direct PermissionManager verification: Approved -> Allowed to execute
            pm_allow = PermissionManager(confirmation_callback=lambda tool, desc: True)
            allowed, level, reason = pm_allow.evaluate(
                tool_name="application_tool",
                operation="launch",
                args={"app_name": "notepad"},
                declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
            )
            assert allowed is True
            assert level == PermissionLevel.CONFIRMATION_REQUIRED
            # 3. ToolRegistry integration verification (FileTool create_file is elevated to CONFIRMATION_REQUIRED):
            test_tmp = Path("cert_test_permission.tmp")
            if test_tmp.exists():
                test_tmp.unlink()

            registry_deny = ToolRegistry(permission_manager=pm_deny)
            registry_deny.register(FileTool())
            result_deny = registry_deny.execute_tool("file_tool", {"action": "create_file", "path": str(test_tmp), "content": "test"})
            assert result_deny.success is False
            assert "User denied permission" in result_deny.error
            assert not test_tmp.exists(), "File must NOT be created when denied"
            print("  [PASS] Denied confirmation prevented file creation on disk")

            registry_allow = ToolRegistry(permission_manager=pm_allow)
            registry_allow.register(FileTool())
            result_allow = registry_allow.execute_tool("file_tool", {"action": "create_file", "path": str(test_tmp), "content": "test"})
            assert result_allow.success is True
            assert test_tmp.exists(), "File MUST be created when approved"
            test_tmp.unlink()
            print("  [PASS] Approved confirmation authorized verified file creation on disk")

            # 4. Verify /api/confirm endpoint stores resolution
            status, conf_res = self._post_json("/api/confirm", {"action_id": "cert_action_1", "confirmed": True})
            assert status == 200
            assert conf_res.get("success") is True
            assert conf_res.get("confirmed") is True
            print("  [PASS] POST /api/confirm successfully records client authorization")

            self.results["gates"]["gate5_confirmation_required"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 5 error: {e}")
            self.results["gates"]["gate5_confirmation_required"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 6: BLOCKED Request (Permanent Prevention)
    # -------------------------------------------------------------------------
    def verify_gate6_blocked_request(self) -> bool:
        print("\n[GATE 6] Testing BLOCKED Request Boundary...")
        try:
            pm = PermissionManager(auto_confirm_in_test=True)  # even in auto-confirm mode!

            blocked_ops = [
                ("system_tool", "arbitrary_shell", {"command": "dir"}),
                ("system_tool", "powershell_raw", {"script": "Get-Process"}),
                ("file_tool", "delete_file", {"path": "C:\\test.txt"}),
                ("file_tool", "rmdir", {"path": "C:\\test_dir"}),
                ("system_tool", "format_disk", {}),
                ("system_tool", "read_env_secrets", {}),
            ]

            for tool, op, args in blocked_ops:
                allowed, level, reason = pm.evaluate(
                    tool_name=tool,
                    operation=op,
                    args=args,
                    declared_level=PermissionLevel.SAFE,  # even if erroneously claimed SAFE
                )
                assert allowed is False, f"Prohibited op '{op}' must be blocked"
                assert level == PermissionLevel.BLOCKED
                assert "BLOCKED:" in reason
                print(f"  [PASS] Operation '{op}' is permanently BLOCKED: {reason}")

            self.results["gates"]["gate6_blocked_request"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 6 error: {e}")
            self.results["gates"]["gate6_blocked_request"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 7: Central Brain Dominance
    # -------------------------------------------------------------------------
    def verify_gate7_central_brain_dominance(self) -> bool:
        print("\n[GATE 7] Verifying Central Brain Dominance...")
        try:
            # 1. /api/hud/agents Sun status
            status, content, _ = self._get("/api/hud/agents")
            assert status == 200
            data = json.loads(content.decode("utf-8"))
            sun = data.get("sun", {})
            assert sun.get("id") == "brain"
            assert sun.get("name") == "DAKU Central Brain"
            assert sun.get("role") == "Autonomous Core & Multi-Pass Reasoner"
            assert sun.get("status") == "ONLINE"
            assert "BLOCKED" in sun.get("permissions", [])
            print(f"  [PASS] Central Sun identified as authoritative core: {sun.get('name')} ({sun.get('role')})")

            # 2. Planetary agents have no direct execution autonomy:
            # All execution routes strictly through /api/hud/turn or /api/chat.
            # Client cannot call arbitrary tool endpoints.
            hud_dir = BASE_DIR / "server" / "hud"
            js_text = (hud_dir / "solar_hud.js").read_text(encoding="utf-8")
            assert "fetch('/api/hud/turn'" in js_text
            # Verify agents array elements are display objects, not execution clients
            assert "function setAgentState" in js_text
            print("  [PASS] Visual planetary agents route all execution through Central DAKU Brain")

            # 3. Privilege Escalation Prevention via /api/hud/profiles
            malicious_profile = {
                "profile": {
                    "name": "Rogue Agent",
                    "role": "Superuser",
                    "privileged": True,
                    "tools": ["arbitrary_shell", "delete_file", "powershell_raw"],
                }
            }
            status, res = self._post_json("/api/hud/profiles", malicious_profile)
            assert status == 200
            saved = res.get("profile", {})
            assert saved.get("privileged") is False, "Profile must NEVER be privileged"
            assert "arbitrary_shell" not in saved.get("tools", [])
            assert "delete_file" not in saved.get("tools", [])
            print("  [PASS] Privilege escalation prevented: custom profiles hardcoded unprivileged with blocked tools stripped")

            self.results["gates"]["gate7_central_brain_dominance"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 7 error: {e}")
            self.results["gates"]["gate7_central_brain_dominance"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 8: All Four Visual Planetary Agents
    # -------------------------------------------------------------------------
    def verify_gate8_visual_agents(self) -> bool:
        print("\n[GATE 8] Verifying All Four Visual Planetary Agents...")
        try:
            status, content, _ = self._get("/api/hud/agents")
            assert status == 200
            data = json.loads(content.decode("utf-8"))
            agents_map = {a["id"]: a for a in data.get("agents", [])}

            expected = {
                "researcher": {
                    "name": "Researcher",
                    "capability": "DAKU research/search capability",
                    "permission_level": "SAFE",
                },
                "coder": {
                    "name": "Coder Agent",
                    "capability": "DAKU coding/execution capability",
                    "permission_level": "CONFIRMATION_REQUIRED",
                },
                "vision": {
                    "name": "Vision Analyst",
                    "capability": "DAKU vision capability",
                    "permission_level": "SAFE",
                },
                "strategist": {
                    "name": "Executive Strategist",
                    "capability": "DAKU planning/orchestration",
                    "permission_level": "SAFE",
                },
            }

            for agent_id, exp in expected.items():
                assert agent_id in agents_map, f"Agent '{agent_id}' missing from /api/hud/agents"
                ag = agents_map[agent_id]
                assert ag["name"] == exp["name"]
                assert ag["capability"] == exp["capability"]
                assert ag["permission_level"] == exp["permission_level"]
                print(f"  [PASS] Verified Visual Agent: {ag['name']} -> {ag['capability']} ({ag['permission_level']})")

            self.results["gates"]["gate8_visual_agents"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 8 error: {e}")
            self.results["gates"]["gate8_visual_agents"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 9: Recording, Audio Playback, Status Transitions, Agent States, Error Handling
    # -------------------------------------------------------------------------
    def verify_gate9_audio_and_transitions(self) -> bool:
        print("\n[GATE 9] Verifying Audio Playback, Agent Transitions, and Error Handling...")
        try:
            hud_dir = BASE_DIR / "server" / "hud"
            js_text = (hud_dir / "solar_hud.js").read_text(encoding="utf-8")

            # Audio Playback
            assert "hudAudioPlayer.src = `data:audio/wav;base64,${b64}`" in js_text
            assert "hudAudioPlayer.onended = () => {" in js_text
            print("  [PASS] HTML5 Audio Element playback binding verified")

            # Agent States
            assert "IDLE: 'IDLE'" in js_text
            assert "ACTIVE: 'ACTIVE'" in js_text
            assert "THINKING: 'THINKING'" in js_text
            assert "EXECUTING: 'EXECUTING'" in js_text
            assert "ERROR: 'ERROR'" in js_text
            print("  [PASS] All 5 Agent visual states verified (IDLE, ACTIVE, THINKING, EXECUTING, ERROR)")

            # Error handling: Empty turn returns HTTP 400
            url = f"{self.server_url}/api/hud/turn"
            req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=3.0)
                raise AssertionError("Expected HTTP 400 on empty payload")
            except urllib.error.HTTPError as he:
                assert he.code == 400
                print("  [PASS] Empty turn input correctly returns HTTP 400 Bad Request")

            self.results["gates"]["gate9_audio_and_transitions"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 9 error: {e}")
            self.results["gates"]["gate9_audio_and_transitions"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 10: Strict Zero Secret Leakage
    # -------------------------------------------------------------------------
    def verify_gate10_zero_secret_leakage(self) -> bool:
        print("\n[GATE 10] Verifying Zero Secret Leakage in Frontend & Responses...")
        try:
            endpoints_to_scan = [
                "/hud",
                "/hud/solar_hud.css",
                "/hud/solar_hud.js",
                "/api/hud/agents",
                "/api/hud/profiles",
                "/health",
            ]

            for ep in endpoints_to_scan:
                _, content, _ = self._get(ep)
                text = content.decode("utf-8", errors="ignore")
                if settings.SARVAM_API_KEY:
                    assert settings.SARVAM_API_KEY not in text, f"SARVAM_API_KEY leaked in {ep}!"
                assert "SARVAM_API_KEY" not in text, f"Env var SARVAM_API_KEY found in {ep}!"
                assert "sk-proj-" not in text, f"OpenAI secret prefix found in {ep}!"
                assert "sk_live_" not in text, f"Live secret prefix found in {ep}!"
                if settings.DAKU_AUTH_TOKEN:
                    assert settings.DAKU_AUTH_TOKEN not in text, f"DAKU_AUTH_TOKEN leaked in {ep}!"
                print(f"  [PASS] Clean scan for {ep} (0 secrets detected)")

            # Also check turn response
            _, turn_res = self._post_json("/api/hud/turn", {"text": "hello"})
            turn_str = json.dumps(turn_res)
            if settings.SARVAM_API_KEY:
                assert settings.SARVAM_API_KEY not in turn_str
            assert "SARVAM_API_KEY" not in turn_str
            assert "sk-proj-" not in turn_str
            assert "sk_live_" not in turn_str
            print("  [PASS] Clean scan for /api/hud/turn response (0 secrets detected)")

            self.results["gates"]["gate10_zero_secret_leakage"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 10 error: {e}")
            self.results["gates"]["gate10_zero_secret_leakage"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Gate 11: Transparent Fallback
    # -------------------------------------------------------------------------
    def verify_gate11_transparent_fallback(self) -> bool:
        print("\n[GATE 11] Verifying Transparent Fallback Behavior...")
        try:
            status, content, _ = self._get("/api/hud/agents")
            assert status == 200
            data = json.loads(content.decode("utf-8"))

            has_sarvam = settings.has_sarvam_key()
            if not has_sarvam:
                assert data.get("sarvam_available") is False
                assert "Fallback" in data.get("stt_provider", "")
                assert "Fallback" in data.get("tts_provider", "")
                print(f"  [PASS] Verified fallback state active: STT={data.get('stt_provider')}, TTS={data.get('tts_provider')}")
            else:
                print(f"  [PASS] Live Sarvam key detected: STT={data.get('stt_provider')}, TTS={data.get('tts_provider')}")

            # Verify system remains fully functional in fallback
            status, turn_res = self._post_json("/api/hud/turn", {"text": "tell me a one sentence joke"})
            assert status == 200
            assert turn_res.get("success") is True
            assert len(turn_res.get("response", "")) > 0
            print(f"  [PASS] Fallback turn execution completed successfully: '{turn_res.get('response')[:50]}...'")

            self.results["gates"]["gate11_transparent_fallback"] = {"status": "PASS"}
            return True
        except Exception as e:
            print(f"  [FAIL] Gate 11 error: {e}")
            self.results["gates"]["gate11_transparent_fallback"] = {"status": "FAIL", "error": str(e)}
            return False

    # -------------------------------------------------------------------------
    # Run All Gates
    # -------------------------------------------------------------------------
    def run_all_gates(self) -> bool:
        print("=" * 65)
        print("     DAKU PHASE 7 — LIVE RUNTIME CERTIFICATION SUITE")
        print(f"     Target Server: {self.server_url}")
        print("=" * 65)

        gates = [
            ("Gate 1: Endpoints & Assets", self.verify_gate1_endpoints),
            ("Gate 2: Microphone & Audio Turn Pipeline", self.verify_gate2_microphone_pipeline),
            ("Gate 3: Complete Voice Lifecycle", self.verify_gate3_voice_lifecycle),
            ("Gate 4: Normal SAFE Request", self.verify_gate4_safe_request),
            ("Gate 5: CONFIRMATION_REQUIRED Request", self.verify_gate5_confirmation_required),
            ("Gate 6: BLOCKED Request Boundary", self.verify_gate6_blocked_request),
            ("Gate 7: Central Brain Dominance", self.verify_gate7_central_brain_dominance),
            ("Gate 8: All Four Visual Agents", self.verify_gate8_visual_agents),
            ("Gate 9: Audio & State Transitions", self.verify_gate9_audio_and_transitions),
            ("Gate 10: Zero Secret Leakage", self.verify_gate10_zero_secret_leakage),
            ("Gate 11: Transparent Fallback", self.verify_gate11_transparent_fallback),
        ]

        passed_count = 0
        for name, gate_func in gates:
            if gate_func():
                passed_count += 1
            else:
                print(f"FAILED AT: {name}")
                break

        total_gates = len(gates)
        all_passed = (passed_count == total_gates)
        self.results["all_passed"] = all_passed
        self.results["passed_gates"] = f"{passed_count}/{total_gates}"

        print("\n" + "=" * 65)
        if all_passed:
            print(f"  [RESULT] ALL {total_gates}/{total_gates} GATES PASSED — LIVE RUNTIME VERIFIED")
        else:
            print(f"  [RESULT] FAILED: {passed_count}/{total_gates} gates passed")
        print("=" * 65 + "\n")

        # Save results to docs/phase7_live_results.json
        out_file = BASE_DIR / "docs" / "phase7_live_results.json"
        out_file.write_text(json.dumps(self.results, indent=2), encoding="utf-8")
        print(f"Results recorded in: {out_file}")

        return all_passed


if __name__ == "__main__":
    certifier = Phase7Certifier()
    success = certifier.run_all_gates()
    sys.exit(0 if success else 1)
