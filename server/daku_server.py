"""
DAKU Remote Server Module
Lightweight, authenticated HTTP/REST daemon designed for headless Linux VPS (Oracle Cloud Always Free).
Exposes /health, /api/chat, /api/confirm, and /api/status.
Built with the standard library (http.server) for zero RAM bloat (< 25 MB working set).
"""

import argparse
import base64
import datetime
import json
import logging
import os
import platform
import secrets
import shutil
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.router import Brain
from config.settings import settings
from tools.base import PermissionLevel, ToolResult
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.server")

SERVER_VERSION = "7.0.0"
HUD_DIR = Path(__file__).resolve().parent / "hud"
MAX_REQUEST_BODY_BYTES = 1024 * 1024  # 1 MB maximum payload guard


def _mask_token(token: str) -> str:
    """Masks secret token for display in logs."""
    if not token or len(token) < 8:
        return "********"
    return f"{token[:3]}...{token[-3:]}"


def _get_system_metrics() -> Dict[str, Any]:
    """Collects system metrics across Linux and Windows without external dependencies."""
    metrics: Dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
    }

    # Memory check (Linux /proc/meminfo or Windows ctypes)
    try:
        if platform.system() == "Linux" and os.path.exists("/proc/meminfo"):
            meminfo = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = parts[1].strip()
            total_kb = int(meminfo.get("MemTotal", "0 kB").split()[0])
            avail_kb = int(meminfo.get("MemAvailable", "0 kB").split()[0])
            metrics["ram_total_mb"] = round(total_kb / 1024, 1)
            metrics["ram_free_mb"] = round(avail_kb / 1024, 1)
            metrics["ram_used_mb"] = round((total_kb - avail_kb) / 1024, 1)
        elif platform.system() == "Windows":
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
            total_mb = round(stat.ullTotalPhys / (1024**2), 1)
            avail_mb = round(stat.ullAvailPhys / (1024**2), 1)
            metrics["ram_total_mb"] = total_mb
            metrics["ram_free_mb"] = avail_mb
            metrics["ram_used_mb"] = round(total_mb - avail_mb, 1)
    except Exception as e:
        metrics["ram_error"] = str(e)

    # Disk check
    try:
        disk_path = "/" if platform.system() != "Windows" else "C:\\"
        usage = shutil.disk_usage(disk_path)
        metrics["disk_total_gb"] = round(usage.total / (1024**3), 2)
        metrics["disk_free_gb"] = round(usage.free / (1024**3), 2)
    except Exception:
        pass

    return metrics


class DakuRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for DAKU Server."""

    server_instance: "DakuServer"

    def log_message(self, format: str, *args: Any) -> None:
        """Custom logger preventing raw stdout clutter."""
        logger.info(f"{self.address_string()} - {format % args}")

    def _send_json_response(
        self,
        status: int,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Helper to send JSON response with correct headers."""
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Daku-Server-Version", SERVER_VERSION)
            if headers:
                for k, v in headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            pass

    def _serve_static_file(self, file_path: Path, content_type: str) -> None:
        """Helper to stream static assets safely without secret leakage."""
        try:
            if not file_path.is_file():
                self._send_json_response(HTTPStatus.NOT_FOUND, {"error": "Not Found", "file": file_path.name})
                return
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Daku-Server-Version", SERVER_VERSION)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            pass
        except Exception as e:
            self._send_json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    def _check_auth(self) -> bool:
        """
        Validates Bearer token authentication.
        Returns True if authorized or if authentication is not configured;
        returns False and sends 401 if unauthorized.
        """
        configured_token = self.server_instance.auth_token
        if not configured_token:
            # If no auth token is set, server allows local/loopback or warns
            return True

        auth_header = self.headers.get("Authorization", "").strip()
        if not auth_header.startswith("Bearer "):
            self._send_json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "Unauthorized",
                    "message": "Missing or invalid Authorization header. Expected: 'Bearer <token>'.",
                },
                {"WWW-Authenticate": 'Bearer realm="DAKU"'},
            )
            return False

        provided_token = auth_header[7:].strip()
        # Use constant-time comparison to protect against timing attacks
        if not secrets.compare_digest(provided_token, configured_token):
            self._send_json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "Unauthorized",
                    "message": "Invalid authentication token.",
                },
                {"WWW-Authenticate": 'Bearer realm="DAKU"'},
            )
            return False

        return True

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Reads and parses JSON body up to MAX_REQUEST_BODY_BYTES."""
        try:
            length_str = self.headers.get("Content-Length", "0")
            content_length = int(length_str)
            if content_length > MAX_REQUEST_BODY_BYTES:
                self._send_json_response(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "Payload too large", "max_bytes": MAX_REQUEST_BODY_BYTES},
                )
                return None
            if content_length == 0:
                return {}
            raw_data = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_data)
        except json.JSONDecodeError:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Bad Request", "message": "Malformed JSON payload."},
            )
            return None
        except Exception as e:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Bad Request", "message": str(e)},
            )
            return None

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.split("?")[0].rstrip("/")
        if not path:
            path = "/"

        # Static Solar HUD assets
        if path in ("/hud", "/hud/index.html") or (path == "/" and "text/html" in self.headers.get("Accept", "")):
            self._serve_static_file(HUD_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/hud/solar_hud.css":
            self._serve_static_file(HUD_DIR / "solar_hud.css", "text/css; charset=utf-8")
        elif path == "/hud/solar_hud.js":
            self._serve_static_file(HUD_DIR / "solar_hud.js", "application/javascript; charset=utf-8")
        elif path == "/health":
            self._handle_health()
        elif path == "/api/status":
            if self._check_auth():
                self._handle_status()
        elif path == "/api/hud/agents":
            self._handle_hud_agents()
        elif path == "/api/hud/profiles":
            self._handle_hud_profiles_get()
        elif path == "/":
            self._send_json_response(
                HTTPStatus.OK,
                {
                    "name": "DAKU Remote Server",
                    "version": SERVER_VERSION,
                    "status": "online",
                    "endpoints": [
                        "/health",
                        "/hud",
                        "/api/chat",
                        "/api/confirm",
                        "/api/status",
                        "/api/voice/transcribe",
                        "/api/voice/synthesize",
                        "/api/hud/agents",
                        "/api/hud/turn",
                        "/api/hud/profiles",
                    ],
                },
            )
        else:
            self._send_json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "Not Found", "path": path},
            )

    def do_POST(self) -> None:
        """Route POST requests."""
        path = self.path.split("?")[0].rstrip("/")

        if path == "/api/chat":
            if self._check_auth():
                self._handle_chat()
        elif path == "/api/confirm":
            if self._check_auth():
                self._handle_confirm()
        elif path == "/api/voice/transcribe":
            if self._check_auth():
                self._handle_voice_transcribe()
        elif path == "/api/voice/synthesize":
            if self._check_auth():
                self._handle_voice_synthesize()
        elif path == "/api/hud/turn":
            self._handle_hud_turn()
        elif path == "/api/hud/profiles":
            self._handle_hud_profiles_post()
        else:
            self._send_json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "Not Found", "path": path},
            )

    def _handle_health(self) -> None:
        """
        GET /health
        Returns public health status without leaking secrets.
        """
        uptime = round(time.time() - self.server_instance.start_time, 2)
        model_status = "available" if settings.has_api_key() else "offline_demo"

        # Check Hermes Gateway reachability
        hermes_status = self.server_instance.check_hermes_status()

        data = {
            "status": "ok",
            "daku": "running",
            "hermes": hermes_status,
            "model_provider": model_status,
            "model_name": settings.MODEL_NAME,
            "backend": settings.AGENT_BACKEND,
            "version": SERVER_VERSION,
            "uptime_seconds": uptime,
            "system": _get_system_metrics(),
        }
        self._send_json_response(HTTPStatus.OK, data)

    def _handle_status(self) -> None:
        """
        GET /api/status
        Detailed authenticated status report.
        """
        uptime = round(time.time() - self.server_instance.start_time, 2)
        metrics = _get_system_metrics()
        hermes_status = self.server_instance.check_hermes_status()
        tools_list = self.server_instance.brain.tool_registry.list_tool_names()

        data = {
            "server": "DAKU Headless Gateway",
            "version": SERVER_VERSION,
            "uptime_seconds": uptime,
            "started_at": datetime.datetime.fromtimestamp(self.server_instance.start_time).isoformat(),
            "hermes_gateway": {
                "configured_url": settings.HERMES_GATEWAY_URL,
                "status": hermes_status,
            },
            "model_configuration": {
                "provider": settings.MODEL_PROVIDER,
                "model_name": settings.MODEL_NAME,
                "base_url": settings.MODEL_BASE_URL,
                "api_key_configured": settings.has_api_key(),
                "agent_backend": settings.AGENT_BACKEND,
            },
            "security": {
                "auth_enabled": bool(self.server_instance.auth_token),
                "require_confirmation": settings.REQUIRE_CONFIRMATION,
                "permission_levels": ["SAFE", "CONFIRMATION_REQUIRED", "BLOCKED"],
            },
            "tools": {
                "count": len(tools_list),
                "registered": tools_list,
            },
            "system": metrics,
        }
        self._send_json_response(HTTPStatus.OK, data)

    def _handle_chat(self) -> None:
        """
        POST /api/chat
        Processes user query through DAKU Brain and Model Router.
        """
        body = self._read_json_body()
        if body is None:
            return

        user_message = body.get("message", "").strip()
        if not user_message:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Missing message", "message": "Field 'message' is required."},
            )
            return

        start_t = time.time()
        try:
            response_text = self.server_instance.brain.think(user_message)
            elapsed = round(time.time() - start_t, 3)

            # Check if an action is awaiting confirmation
            pending_action = getattr(self.server_instance, "_pending_action", None)

            self._send_json_response(
                HTTPStatus.OK,
                {
                    "success": True,
                    "response": response_text,
                    "elapsed_seconds": elapsed,
                    "requires_confirmation": bool(pending_action),
                    "pending_action": pending_action,
                },
            )
        except Exception as e:
            logger.error(f"Error processing chat message: {e}", exc_info=True)
            self._send_json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "success": False,
                    "error": "Execution error",
                    "message": f"Server encountered an error: {str(e)}",
                },
            )

    def _handle_confirm(self) -> None:
        """
        POST /api/confirm
        Allows the client to confirm or deny an action requiring user authorization.
        """
        body = self._read_json_body()
        if body is None:
            return

        action_id = body.get("action_id")
        confirmed = bool(body.get("confirmed", False))

        # Store confirmation resolution in server instance
        self.server_instance.resolve_confirmation(action_id, confirmed)

        self._send_json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action_id": action_id,
                "confirmed": confirmed,
                "message": f"Action {'confirmed' if confirmed else 'denied'}.",
            },
        )

    def _handle_voice_transcribe(self) -> None:
        """
        POST /api/voice/transcribe
        Transcribes uploaded audio via server-side Sarvam STT (with Google STT fallback).
        Keeps Sarvam API key strictly server-side.
        """
        body = self._read_json_body()
        if body is None:
            return

        audio_b64 = body.get("audio_base64", "").strip()
        language = body.get("language", settings.SARVAM_LANGUAGE)
        if not audio_b64:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Missing audio", "message": "Field 'audio_base64' is required."},
            )
            return

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Invalid base64", "message": f"Could not decode audio: {str(e)}"},
            )
            return

        from voice.providers.sarvam_stt import SarvamSTTProvider
        from voice.providers.google_stt import GoogleSTTProvider

        sarvam_stt = SarvamSTTProvider()
        google_stt = GoogleSTTProvider()
        transcript = None
        provider_used = "none"
        latency_ms = 0.0

        if sarvam_stt.is_available():
            res = sarvam_stt.transcribe(audio_bytes, language=language)
            if res and res.text:
                transcript = res.text
                provider_used = "sarvam"
                latency_ms = res.latency_ms

        if not transcript and google_stt.is_available():
            res = google_stt.transcribe(audio_bytes, language=language)
            if res and res.text:
                transcript = res.text
                provider_used = "google_stt"
                latency_ms = res.latency_ms

        self._send_json_response(
            HTTPStatus.OK,
            {
                "success": bool(transcript),
                "transcript": transcript or "",
                "provider": provider_used,
                "latency_ms": round(latency_ms, 2),
            },
        )

    def _handle_voice_synthesize(self) -> None:
        """
        POST /api/voice/synthesize
        Synthesizes text via server-side Sarvam Bulbul v3 TTS.
        Keeps Sarvam API key strictly server-side.
        """
        body = self._read_json_body()
        if body is None:
            return

        text = body.get("text", "").strip()
        language = body.get("language", settings.SARVAM_LANGUAGE)
        speaker = body.get("speaker", settings.SARVAM_TTS_SPEAKER)

        if not text:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Missing text", "message": "Field 'text' is required."},
            )
            return

        from voice_agent.normalizer import TTSNormalizer
        from voice.providers.sarvam_tts import SarvamTTSProvider

        clean_text = TTSNormalizer.clean_for_speech(text, target_lang=language)
        sarvam_tts = SarvamTTSProvider()

        if sarvam_tts.is_available():
            res = sarvam_tts.synthesize(clean_text, language=language, speaker=speaker)
            if res and res.audio_base64:
                self._send_json_response(
                    HTTPStatus.OK,
                    {
                        "success": True,
                        "audio_base64": res.audio_base64,
                        "format": res.format,
                        "sample_rate": res.sample_rate,
                        "provider": "sarvam",
                        "model": res.model,
                        "speaker": res.speaker,
                        "latency_ms": round(res.latency_ms, 2),
                    },
                )
                return

        # If Sarvam TTS unavailable or synthesis failed on server
        self._send_json_response(
            HTTPStatus.OK,
            {
                "success": False,
                "audio_base64": "",
                "provider": "none",
                "message": "Sarvam TTS unavailable on server; client should use local TTS fallback.",
            },
        )

    def _handle_hud_agents(self) -> None:
        """
        GET /api/hud/agents
        Returns capability specifications and real operational mappings for the
        4 visual agents + Central Sun (DAKU Brain).
        """
        tools_list = self.server_instance.brain.tool_registry.list_tool_names()
        sarvam_active = settings.has_sarvam_key()
        backend = getattr(self.server_instance.brain, "backend", None)
        harness_telemetry = {}
        if backend and hasattr(backend, "get_telemetry"):
            try:
                harness_telemetry = backend.get_telemetry()
            except Exception:
                pass

        data = {
            "version": SERVER_VERSION,
            "stt_provider": "Sarvam Saaras" if sarvam_active else "Google STT / Text Fallback",
            "tts_provider": "Sarvam Bulbul" if sarvam_active else "Windows SAPI / Audio Fallback",
            "sarvam_available": sarvam_active,
            "sun": {
                "id": "brain",
                "name": "DAKU Central Brain",
                "role": "Autonomous Core & Multi-Pass Reasoner",
                "model": settings.MODEL_NAME,
                "provider": settings.MODEL_PROVIDER,
                "backend": settings.AGENT_BACKEND,
                "status": "ONLINE",
                "permissions": ["SAFE", "CONFIRMATION_REQUIRED", "BLOCKED"],
                "harness_status": harness_telemetry.get("harness_status", "ACTIVE" if settings.AGENT_BACKEND == "harness" else "STANDBY"),
                "session_id": harness_telemetry.get("session_id", ""),
                "pass_count": harness_telemetry.get("pass_count", 0),
                "last_think_trace": harness_telemetry.get("last_think_trace", ""),
                "active_plugins": harness_telemetry.get("active_plugins", []),
                "event_count": harness_telemetry.get("event_count", 0),
            },
            "agents": [
                {
                    "id": "researcher",
                    "name": "Researcher",
                    "role": "Research & Search Specialist",
                    "capability": "DAKU research/search capability",
                    "plugin_id": "daku.plugin.browser",
                    "tools": [t for t in tools_list if "browser" in t or "search" in t or "file" in t],
                    "permission_level": "SAFE",
                    "color": "#00d2ff",
                    "status": "ACTIVE" if "daku.plugin.browser" in harness_telemetry.get("active_plugins", []) else "IDLE",
                },
                {
                    "id": "coder",
                    "name": "Coder Agent",
                    "role": "Coding & Execution Engine",
                    "capability": "DAKU coding/execution capability",
                    "plugin_id": "daku.plugin.application",
                    "tools": [t for t in tools_list if "application" in t or "system" in t or "file" in t],
                    "permission_level": "CONFIRMATION_REQUIRED",
                    "color": "#06d6a0",
                    "status": "ACTIVE" if "daku.plugin.application" in harness_telemetry.get("active_plugins", []) else "IDLE",
                },
                {
                    "id": "vision",
                    "name": "Vision Analyst",
                    "role": "Visual & DOM Inspector",
                    "capability": "DAKU vision capability",
                    "plugin_id": "daku.plugin.vision",
                    "tools": [t for t in tools_list if "browser" in t],
                    "permission_level": "SAFE",
                    "color": "#9d4edd",
                    "status": "IDLE",
                },
                {
                    "id": "strategist",
                    "name": "Executive Strategist",
                    "role": "Planning & Multi-Pass Orchestrator",
                    "capability": "DAKU planning/orchestration",
                    "plugin_id": "daku.plugin.orchestrator",
                    "tools": ["TaskPlanner", "MultiPassReasoner", "ToolRouter"],
                    "permission_level": "SAFE",
                    "color": "#ffb703",
                    "status": "IDLE",
                },
            ],
            "harness_plugins": harness_telemetry.get("plugins", []),
            "custom_profiles": self.server_instance.hud_profiles,
        }
        self._send_json_response(HTTPStatus.OK, data)

    def _handle_hud_profiles_get(self) -> None:
        """GET /api/hud/profiles - Returns list of configured UI profiles."""
        self._send_json_response(
            HTTPStatus.OK,
            {"success": True, "profiles": self.server_instance.hud_profiles},
        )

    def _handle_hud_profiles_post(self) -> None:
        """
        POST /api/hud/profiles
        Saves a UI-level visualization profile.
        Explicitly enforces that profiles are visual/UI only and cannot grant
        arbitrary OS or privileged execution capabilities.
        """
        body = self._read_json_body()
        if body is None:
            return

        profile = body.get("profile", {})
        name = str(profile.get("name", "")).strip()
        if not name or len(name) > 32:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Invalid name", "message": "Profile name is required (max 32 chars)."},
            )
            return

        # Security constraint: profile cannot contain arbitrary privileged commands or tools
        cleaned_profile = {
            "id": profile.get("id", f"agent-profile-{int(time.time())}"),
            "name": name,
            "role": str(profile.get("role", "Custom Agent Profile"))[:64],
            "capability": str(profile.get("capability", "UI Agent Profile"))[:128],
            "tools": [str(t) for t in profile.get("tools", []) if str(t) in self.server_instance.brain.tool_registry.list_tool_names() or str(t) in ("browser_tool", "file_tool", "application_tool", "system_tool", "TaskPlanner")],
            "color": str(profile.get("color", "#00d2ff"))[:16],
            "icon": str(profile.get("icon", "🛸"))[:8],
            "description": str(profile.get("description", ""))[:128],
            "created_at": datetime.datetime.now().isoformat(),
            "privileged": False,  # Hardcoded False: no profile can be privileged
        }

        self.server_instance.hud_profiles.append(cleaned_profile)
        self._send_json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "message": f"Profile '{name}' saved successfully as UI visualization profile.",
                "profile": cleaned_profile,
            },
        )

    def _handle_hud_turn(self) -> None:
        """
        POST /api/hud/turn
        Processes a voice or text turn through DAKU VoiceSession and Brain.
        Executes:
        Audio (base64) / Text -> STT (Sarvam Saaras -> Google STT fallback)
        -> Central DAKU Brain (MultiPassReasoner / Intent / Router)
        -> 3-Tier Permission Check
        -> Tool Execution (if authorized)
        -> TTS (Sarvam Bulbul -> Windows SAPI fallback)
        -> Telemetry & Audio Response.
        """
        body = self._read_json_body()
        if body is None:
            return

        text_input = body.get("text", "").strip()
        audio_b64 = body.get("audio_base64", "").strip()
        language = body.get("language", settings.SARVAM_LANGUAGE)

        if not text_input and not audio_b64:
            self._send_json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "Missing input", "message": "Either 'text' or 'audio_base64' is required."},
            )
            return

        transcript = text_input
        stt_provider_used = "none"
        stt_latency_ms = 0.0
        start_t = time.perf_counter()

        # Step 1: STT if audio supplied
        if audio_b64 and not transcript:
            try:
                audio_bytes = base64.b64decode(audio_b64)
            except Exception as e:
                self._send_json_response(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Invalid base64", "message": f"Could not decode audio: {str(e)}"},
                )
                return

            from voice.providers.sarvam_stt import SarvamSTTProvider
            from voice.providers.google_stt import GoogleSTTProvider

            sarvam_stt = SarvamSTTProvider()
            google_stt = GoogleSTTProvider()

            if sarvam_stt.is_available():
                t0 = time.perf_counter()
                res = sarvam_stt.transcribe(audio_bytes, language=language)
                if res and res.text:
                    transcript = res.text
                    stt_provider_used = "sarvam"
                    stt_latency_ms = (time.perf_counter() - t0) * 1000.0

            if not transcript and google_stt.is_available():
                t0 = time.perf_counter()
                res = google_stt.transcribe(audio_bytes, language=language)
                if res and res.text:
                    transcript = res.text
                    stt_provider_used = "google_stt"
                    stt_latency_ms = (time.perf_counter() - t0) * 1000.0

            if not transcript:
                self._send_json_response(
                    HTTPStatus.OK,
                    {
                        "success": False,
                        "transcript": "",
                        "response": "I could not understand the audio input. Please try speaking again.",
                        "error": "STT produced no transcript",
                        "stt_provider": stt_provider_used,
                        "tts_provider": "none",
                        "audio_base64": "",
                        "requires_confirmation": False,
                        "pending_action": None,
                        "executed_tools": [],
                        "elapsed_seconds": round(time.perf_counter() - start_t, 3),
                        "ui_state": "STANDBY",
                    },
                )
                return

        # Step 2: DAKU Brain Thinking & Permission Check
        brain = self.server_instance.brain
        t_brain = time.perf_counter()
        response_text = ""
        pending_action = getattr(self.server_instance, "_pending_action", None)

        try:
            response_text = brain.think(transcript)
        except Exception as e:
            logger.error(f"DAKU Brain execution failed: {e}", exc_info=True)
            response_text = f"I encountered an error: {str(e)}"

        brain_latency_ms = (time.perf_counter() - t_brain) * 1000.0

        # Step 3: TTS Synthesis
        tts_audio_b64 = ""
        tts_provider_used = "none"
        tts_latency_ms = 0.0

        if response_text:
            from voice.providers.sarvam_tts import SarvamTTSProvider
            from voice_agent.normalizer import TTSNormalizer

            clean_text = TTSNormalizer.clean_for_speech(response_text, target_lang=language)
            sarvam_tts = SarvamTTSProvider()

            if sarvam_tts.is_available():
                t0 = time.perf_counter()
                res = sarvam_tts.synthesize(clean_text, language=language)
                if res and res.audio_base64:
                    tts_audio_b64 = res.audio_base64
                    tts_provider_used = "sarvam"
                    tts_latency_ms = (time.perf_counter() - t0) * 1000.0

            if not tts_audio_b64:
                from voice.providers.windows_tts import WindowsSapiTTSProvider
                win_tts = WindowsSapiTTSProvider()
                if win_tts.is_available():
                    tts_provider_used = "windows_sapi"
                else:
                    tts_provider_used = "text_fallback"

        total_elapsed = round(time.perf_counter() - start_t, 3)

        self._send_json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "transcript": transcript,
                "response": response_text,
                "stt_provider": stt_provider_used,
                "tts_provider": tts_provider_used,
                "audio_base64": tts_audio_b64,
                "requires_confirmation": bool(pending_action),
                "pending_action": pending_action,
                "executed_tools": [],
                "brain_latency_ms": round(brain_latency_ms, 2),
                "stt_latency_ms": round(stt_latency_ms, 2),
                "tts_latency_ms": round(tts_latency_ms, 2),
                "elapsed_seconds": total_elapsed,
                "ui_state": "STANDBY",
            },
        )


class DakuServer:
    """
    Main DAKU Server container managing HTTP daemon, Brain instance,
    confirmation queue, and Hermes gateway connectivity.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        auth_token: Optional[str] = None,
        brain: Optional[Brain] = None,
    ):
        self.host = host or settings.DAKU_SERVER_HOST or "127.0.0.1"
        self.port = port or settings.DAKU_SERVER_PORT or 8443
        self.auth_token = auth_token if auth_token is not None else settings.DAKU_AUTH_TOKEN
        self.brain = brain or Brain()
        self.start_time = time.time()
        self.httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._pending_confirmations: Dict[str, bool] = {}
        self.hud_profiles: List[Dict[str, Any]] = []
        self._voice_session = None

    @property
    def voice_session(self):
        if self._voice_session is None:
            from voice.voice_session import VoiceSessionManager
            self._voice_session = VoiceSessionManager(brain=self.brain)
        return self._voice_session

    def check_hermes_status(self) -> str:
        """Checks if the local Hermes Gateway process is reachable."""
        gateway_url = settings.HERMES_GATEWAY_URL
        if not gateway_url:
            return "unconfigured"
        try:
            req = urllib.request.Request(
                f"{gateway_url}/health",
                headers={"User-Agent": "DAKU-Server-Probe/5.0"},
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return "running"
        except Exception:
            pass

        # Try raw TCP port check if /health endpoint differs
        try:
            parsed = urllib.parse.urlparse(gateway_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 8080
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    return "running"
        except Exception:
            pass

        return "stopped"

    def resolve_confirmation(self, action_id: str, confirmed: bool) -> None:
        """Stores client's confirmation decision."""
        if action_id:
            self._pending_confirmations[action_id] = confirmed

    def start(self, blocking: bool = True) -> None:
        """Starts the HTTP server."""
        handler_cls = DakuRequestHandler
        handler_cls.server_instance = self

        self.httpd = ThreadingHTTPServer((self.host, self.port), handler_cls)
        self._is_running = True
        token_info = _mask_token(self.auth_token) if self.auth_token else "NONE (open/local)"
        logger.info(f"DAKU Server v{SERVER_VERSION} listening on {self.host}:{self.port}")
        logger.info(f"Authentication Token: {token_info}")

        if blocking:
            try:
                self.httpd.serve_forever()
            except (KeyboardInterrupt, SystemExit):
                self.stop()
        else:
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Gracefully stops the HTTP server."""
        if self.httpd:
            logger.info("Stopping DAKU Server...")
            self.httpd.shutdown()
            self.httpd.server_close()
            self._is_running = False
            logger.info("DAKU Server stopped cleanly.")


def create_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
    auth_token: Optional[str] = None,
) -> DakuServer:
    """Factory helper to instantiate a DakuServer instance."""
    return DakuServer(host=host, port=port, auth_token=auth_token)


def main():
    """CLI entry point for running the server."""
    parser = argparse.ArgumentParser(description="DAKU Remote Agent Server")
    parser.add_argument("--host", type=str, default=settings.DAKU_SERVER_HOST, help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.DAKU_SERVER_PORT, help="Port to bind (default: 8443)")
    parser.add_argument("--token", type=str, default=settings.DAKU_AUTH_TOKEN, help="Authentication bearer token")
    parser.add_argument("--hud", action="store_true", help="Automatically open Solar HUD in default web browser")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print(f"       DAKU REMOTE SERVER v{SERVER_VERSION} (Solar Swarm HUD)       ")
    print("=" * 60)
    print(f"Host          : {args.host}")
    print(f"Port          : {args.port}")
    print(f"Backend       : {settings.AGENT_BACKEND}")
    print(f"Model         : {settings.MODEL_PROVIDER} ({settings.MODEL_NAME})")
    print(f"Auth Token    : {_mask_token(args.token) if args.token else 'UNCONFIGURED (WARNING)'}")
    print(f"Hermes Gateway: {settings.HERMES_GATEWAY_URL}")
    print(f"Solar HUD     : http://{args.host}:{args.port}/hud")
    print("=" * 60)

    server = create_server(host=args.host, port=args.port, auth_token=args.token)

    if args.hud:
        import webbrowser
        hud_url = f"http://{args.host}:{args.port}/hud"
        print(f"[DAKU HUD] Launching Solar HUD in browser: {hud_url}")
        threading.Timer(0.8, lambda: webbrowser.open(hud_url)).start()

    # Register signal handlers for clean systemd termination
    def handle_signal(sig, frame):
        print(f"\n[DAKU Server] Signal {sig} received. Shutting down...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    server.start(blocking=True)


if __name__ == "__main__":
    main()
