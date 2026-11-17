"""
DAKU Phase 9: Non-Blocking Loopback Telemetry Poller
Polls http://127.0.0.1:<port>/api/hud/agents on a daemon thread using urllib.request.
Provides:
- State management across the 10 DAKU UI states.
- Dynamic polling intervals (500ms active, 2000ms idle).
- Bearer token authentication without secret leakage.
- Clean transition to OFFLINE state without CPU spikes.
- Confirmation dispatch to /api/confirm.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger("daku.ui.client")

# Recognized DAKU 10 UI States
UI_STATES = (
    "STANDBY",
    "LISTENING",
    "TRANSCRIBING",
    "THINKING",
    "AWAITING_CONFIRMATION",
    "EXECUTING",
    "SPEAKING",
    "FALLBACK",
    "ERROR",
    "OFFLINE",
)


class HUDTelemetryClient:
    """Non-blocking telemetry client querying the local DAKU server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        auth_token: Optional[str] = None,
        active_interval_ms: int = 500,
        idle_interval_ms: int = 2000,
    ):
        self.host = host
        self.port = port or getattr(settings, "SERVER_PORT", 8443)
        self.auth_token = auth_token if auth_token is not None else getattr(settings, "DAKU_AUTH_TOKEN", "")
        self.active_interval = max(0.1, active_interval_ms / 1000.0)
        self.idle_interval = max(0.5, idle_interval_ms / 1000.0)

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

        # State storage
        self.status: str = "OFFLINE"
        self.is_connected: bool = False
        self.last_poll_time: float = 0.0
        self.sun_data: Dict[str, Any] = {
            "id": "brain",
            "name": "DAKU Central Brain",
            "status": "OFFLINE",
            "model": "deepseek-chat",
            "pass_count": 0,
            "session_id": "",
            "last_think_trace": "",
            "active_plugins": [],
        }
        self.agents_data: List[Dict[str, Any]] = []
        self.sarvam_available: bool = False
        self.confirmation_pending: Optional[Dict[str, Any]] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a callback function to receive telemetry updates."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Removes a registered callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, state_snapshot: Dict[str, Any]) -> None:
        """Notifies all registered listeners of an updated state snapshot."""
        for cb in list(self._listeners):
            try:
                cb(state_snapshot)
            except Exception as e:
                logger.debug(f"Error in telemetry listener callback: {e}")

    def build_headers(self) -> Dict[str, str]:
        """Constructs headers, attaching Bearer token if configured."""
        headers = {
            "User-Agent": "DAKU-Desktop-HUD/1.0",
            "Accept": "application/json",
        }
        if self.auth_token and self.auth_token.strip():
            headers["Authorization"] = f"Bearer {self.auth_token.strip()}"
        return headers

    def poll_once(self) -> Dict[str, Any]:
        """
        Executes a single HTTP GET to /api/hud/agents.
        Updates internal state and returns the snapshot dictionary.
        """
        url = f"{self.base_url}/api/hud/agents"
        headers = self.build_headers()
        req = urllib.request.Request(url, headers=headers, method="GET")

        now = time.time()
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    raw_data = resp.read().decode("utf-8")
                    data = json.loads(raw_data)
                    return self._process_success_payload(data, now)
                else:
                    return self._process_error_state(f"HTTP {resp.status}", now)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            return self._process_error_state(str(e), now)
        except Exception as e:
            return self._process_error_state(f"Unexpected: {e}", now)

    def _process_success_payload(self, data: Dict[str, Any], timestamp: float) -> Dict[str, Any]:
        """Processes a valid 200 OK response from /api/hud/agents."""
        with self._lock:
            self.is_connected = True
            self.last_poll_time = timestamp

            sun = data.get("sun", {})
            self.sun_data = sun
            self.agents_data = data.get("agents", [])
            self.sarvam_available = bool(data.get("sarvam_available", False))

            # Determine composite HUD state
            server_sun_status = sun.get("status", "ONLINE").upper()
            harness_status = sun.get("harness_status", "STANDBY").upper()

            if self.confirmation_pending:
                self.status = "AWAITING_CONFIRMATION"
            elif harness_status == "ACTIVE":
                # Active reasoning/executing
                active_plugins = sun.get("active_plugins", [])
                if any("application" in p for p in active_plugins):
                    self.status = "EXECUTING"
                else:
                    self.status = "THINKING"
            elif server_sun_status == "ONLINE":
                self.status = "STANDBY"
            else:
                self.status = server_sun_status if server_sun_status in UI_STATES else "STANDBY"

            snapshot = self.get_state()

        self._notify_listeners(snapshot)
        return snapshot

    def _process_error_state(self, error_msg: str, timestamp: float) -> Dict[str, Any]:
        """Handles connection failure by transitioning to OFFLINE without crashing."""
        with self._lock:
            self.is_connected = False
            self.last_poll_time = timestamp
            self.status = "OFFLINE"
            self.sun_data["status"] = "OFFLINE"
            snapshot = self.get_state()

        self._notify_listeners(snapshot)
        return snapshot

    def set_confirmation_state(self, pending_data: Optional[Dict[str, Any]]) -> None:
        """Manually or externally updates confirmation pending state."""
        with self._lock:
            self.confirmation_pending = pending_data
            if pending_data:
                self.status = "AWAITING_CONFIRMATION"
            elif self.is_connected:
                self.status = "STANDBY"
            else:
                self.status = "OFFLINE"
            snapshot = self.get_state()
        self._notify_listeners(snapshot)

    def send_confirmation(self, confirmed: bool) -> bool:
        """
        Dispatches confirmation decision to POST /api/confirm.
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/api/confirm"
        headers = self.build_headers()
        headers["Content-Type"] = "application/json; charset=utf-8"
        payload = json.dumps({"confirmed": bool(confirmed)}).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                success = (resp.status == 200)
                if success:
                    self.set_confirmation_state(None)
                return success
        except Exception as e:
            logger.warning(f"Failed to dispatch confirmation to {url}: {e}")
            return False

    def get_state(self) -> Dict[str, Any]:
        """Thread-safe snapshot of the current telemetry state."""
        return {
            "status": self.status,
            "is_connected": self.is_connected,
            "last_poll_time": self.last_poll_time,
            "sun": dict(self.sun_data),
            "agents": list(self.agents_data),
            "sarvam_available": self.sarvam_available,
            "confirmation_pending": dict(self.confirmation_pending) if self.confirmation_pending else None,
            "pass_count": self.sun_data.get("pass_count", 0),
            "session_id": self.sun_data.get("session_id", ""),
            "last_think_trace": self.sun_data.get("last_think_trace", ""),
        }

    def start(self) -> None:
        """Starts the background telemetry polling daemon thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="DakuHUDPoller")
            self._thread.start()
            logger.info(f"HUD Telemetry Poller started for {self.base_url}")

    def stop(self) -> None:
        """Signals the background polling loop to terminate cleanly."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("HUD Telemetry Poller stopped.")

    def _poll_loop(self) -> None:
        """Worker loop running on the daemon thread."""
        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                logger.debug(f"Exception in HUD poll loop: {e}")

            # Dynamic interval: 500ms when active/connected, 2000ms when idle/offline
            interval = self.active_interval if (self.is_connected and self.status != "STANDBY") else self.idle_interval
            
            # Sleep in small slices to allow rapid shutdown
            end_time = time.monotonic() + interval
            while self._running and time.monotonic() < end_time:
                time.sleep(0.05)
