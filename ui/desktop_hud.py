"""
DAKU Phase 9: JARVIS Native Desktop HUD UI
Translucent, always-on-top, low-overhead circular overlay window built with Python stdlib (tkinter + ctypes).
Features:
- Central core ring reflecting 10 live states (STANDBY, LISTENING, THINKING, EXECUTING, AWAITING_CONFIRMATION, SPEAKING, OFFLINE, etc.).
- 4 planetary orbit indicators synced to the Solar Swarm agents (Researcher, Coder, Vision Analyst, Executive Strategist).
- Compact telemetry readout showing active dsh pass count, session ID snippet, and action status.
- Radial pulse waveform for LISTENING and dynamic audio bars for SPEAKING.
- High-visibility inline confirmation banner for AWAITING_CONFIRMATION with [Y] / [N] / [C] hotkeys.
- Smooth mouse dragging to reposition and toggleable click-through mode.
- System tray integration with context menu (Show/Hide, Click-Through, Quit).
- Throttled animation loop (<1% idle CPU, <20 MB working set RAM).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import math
import os
import sys
import time
import tkinter as tk
from typing import Any, Dict, List, Optional

from ui.hud_client import HUDTelemetryClient
from ui.tray_icon import Win32TrayIcon

# Win32 Constants for Window Styling
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

# HUD Dimension
HUD_SIZE = 260
CHROMA_KEY = "#010101"

# State Color Palette
STATE_COLORS = {
    "STANDBY": "#00d2ff",                 # Cyan
    "LISTENING": "#0077ff",               # Electric Blue
    "TRANSCRIBING": "#48cae4",            # Ice Blue
    "THINKING": "#9d4edd",                # Neon Purple
    "AWAITING_CONFIRMATION": "#ff9e00",   # Amber Alert
    "CONFIRMATION_REQUIRED": "#ff9e00",   # Amber Alert
    "EXECUTING": "#06d6a0",               # Emerald Green
    "SPEAKING": "#ffd166",                # Golden Yellow
    "FALLBACK": "#f77f00",                # Safety Orange
    "ERROR": "#d90429",                   # Crimson Red
    "OFFLINE": "#6c757d",                 # Steel Muted Gray
}

# 4 Solar Swarm Visual Agent Specs
SWARM_SPECS = [
    {"id": "researcher", "name": "Researcher", "color": "#00d2ff", "orbit_r": 58, "speed": 0.025, "size": 4.5},
    {"id": "coder", "name": "Coder", "color": "#06d6a0", "orbit_r": 74, "speed": 0.018, "size": 5.0},
    {"id": "vision", "name": "Vision", "color": "#9d4edd", "orbit_r": 90, "speed": 0.013, "size": 4.5},
    {"id": "strategist", "name": "Strategist", "color": "#ffb703", "orbit_r": 106, "speed": 0.009, "size": 5.5},
]


def get_process_working_set_mb() -> float:
    """Measures the current process private working memory in megabytes using Win32 psapi."""
    try:
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS_EX()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        get_mem = ctypes.windll.psapi.GetProcessMemoryInfo
        get_mem.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), ctypes.wintypes.DWORD]
        get_mem.restype = ctypes.wintypes.BOOL
        if get_mem(handle, ctypes.byref(pmc), pmc.cb):
            # Return private committed heap RAM in MB
            return pmc.PrivateUsage / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0


def get_process_memory_info() -> Dict[str, float]:
    """Measures total working set and private memory metrics in MB."""
    try:
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS_EX()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        get_mem = ctypes.windll.psapi.GetProcessMemoryInfo
        get_mem.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), ctypes.wintypes.DWORD]
        get_mem.restype = ctypes.wintypes.BOOL
        if get_mem(handle, ctypes.byref(pmc), pmc.cb):
            return {
                "working_set_mb": round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2),
                "private_mb": round(pmc.PrivateUsage / (1024.0 * 1024.0), 2),
            }
    except Exception:
        pass
    return {"working_set_mb": 0.0, "private_mb": 0.0}


class JarvisDesktopHUD:
    """
    JARVIS-style circular Desktop HUD Overlay.
    Renders on an always-on-top, tool-window canvas with transparent background.
    """

    def __init__(
        self,
        client: Optional[HUDTelemetryClient] = None,
        enable_tray: bool = True,
        initial_x: Optional[int] = None,
        initial_y: Optional[int] = None,
    ):
        self.client = client or HUDTelemetryClient()
        self.enable_tray = enable_tray

        # Window & Canvas
        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self.hwnd: Optional[int] = None

        # Coordinates & Layout
        self.initial_x = initial_x
        self.initial_y = initial_y
        self.cx = HUD_SIZE // 2
        self.cy = HUD_SIZE // 2

        # State & Animation Variables
        self.click_through = False
        self.visible = True
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.angle_step = 0.0
        self.pulse_phase = 0.0
        self.last_frame_time = time.monotonic()
        self._after_id = None

        # Agent Orbital Positions
        self.agent_angles = {a["id"]: (idx * math.pi / 2.0) for idx, a in enumerate(SWARM_SPECS)}

        # Tray Icon
        self.tray = None

    def setup_window(self) -> None:
        """Initializes Tkinter window, Win32 styles, and canvas."""
        self.root = tk.Tk()
        self.root.title("DAKU JARVIS HUD")
        self.root.geometry(f"{HUD_SIZE}x{HUD_SIZE}")
        self.root.overrideredirect(True)
        self.root.configure(bg=CHROMA_KEY)

        # Transparent Chroma Keying
        try:
            self.root.wm_attributes("-transparentcolor", CHROMA_KEY)
            self.root.wm_attributes("-topmost", True)
        except Exception:
            pass

        # Position window on screen
        screen_w = self.root.winfo_screenwidth()
        x = self.initial_x if self.initial_x is not None else (screen_w - HUD_SIZE - 30)
        y = self.initial_y if self.initial_y is not None else 40
        self.root.geometry(f"{HUD_SIZE}x{HUD_SIZE}+{x}+{y}")

        # Canvas
        self.canvas = tk.Canvas(
            self.root,
            width=HUD_SIZE,
            height=HUD_SIZE,
            bg=CHROMA_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Mouse Dragging Bindings
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<Button-3>", self._on_right_click)

        # Hotkeys for confirmations and toggles
        self.root.bind("<Key-y>", lambda e: self._on_confirm_key(True))
        self.root.bind("<Key-Y>", lambda e: self._on_confirm_key(True))
        self.root.bind("<Key-n>", lambda e: self._on_confirm_key(False))
        self.root.bind("<Key-N>", lambda e: self._on_confirm_key(False))
        self.root.bind("<Key-c>", lambda e: self._on_confirm_key(False))
        self.root.bind("<Key-C>", lambda e: self._on_confirm_key(False))
        self.root.bind("<Control-h>", lambda e: self.toggle_visibility())
        self.root.bind("<Control-t>", lambda e: self.toggle_click_through())

        # Apply Win32 Extended Window Styles
        self._apply_win32_styles()

        # Initialize System Tray
        if self.enable_tray:
            self.tray = Win32TrayIcon(
                tooltip="DAKU JARVIS Desktop HUD",
                on_toggle_visible=self.toggle_visibility,
                on_toggle_clickthrough=self.toggle_click_through,
                on_quit=self.quit,
            )
            self.tray.start()

    def _apply_win32_styles(self) -> None:
        """Applies WS_EX_TOPMOST, WS_EX_TOOLWINDOW, and optional WS_EX_TRANSPARENT."""
        if not self.root:
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            self.hwnd = hwnd

            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= (WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED)
            if self.click_through:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def toggle_click_through(self) -> None:
        """Toggles click-through transparency for seamless background overlay."""
        self.click_through = not self.click_through
        self._apply_win32_styles()

    def toggle_visibility(self) -> None:
        """Toggles HUD display visibility."""
        if not self.root:
            return
        if self.visible:
            self.root.withdraw()
            self.visible = False
        else:
            self.root.deiconify()
            self.visible = True

    def _on_mouse_down(self, event: tk.Event) -> None:
        if not self.click_through:
            self.drag_start_x = event.x
            self.drag_start_y = event.y

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if not self.click_through and self.root:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            new_x = self.root.winfo_x() + dx
            new_y = self.root.winfo_y() + dy
            self.root.geometry(f"+{new_x}+{new_y}")

    def _on_right_click(self, event: tk.Event) -> None:
        """Right click toggles click-through mode quickly."""
        self.toggle_click_through()

    def _on_confirm_key(self, confirmed: bool) -> None:
        """Handles keyboard confirmation dispatch when pending."""
        state = self.client.get_state()
        if state.get("status") in ("AWAITING_CONFIRMATION", "CONFIRMATION_REQUIRED") or state.get("confirmation_pending"):
            self.client.send_confirmation(confirmed)

    def render_frame(self) -> None:
        """Draws one frame of the JARVIS HUD Canvas."""
        if not self.canvas:
            return

        self.canvas.delete("all")
        state = self.client.get_state()
        status = state.get("status", "OFFLINE")
        core_color = STATE_COLORS.get(status, STATE_COLORS["STANDBY"])
        cx, cy = self.cx, self.cy

        now = time.monotonic()
        dt = max(0.001, now - self.last_frame_time)
        self.last_frame_time = now

        # Increment phase
        self.angle_step = (self.angle_step + dt * 1.5) % (2 * math.pi)
        self.pulse_phase = (self.pulse_phase + dt * 4.0) % (2 * math.pi)

        # 1. Outer Tech Compass & Calibration Ticks
        r_outer = 120
        self.canvas.create_oval(
            cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
            outline="#1c2536", width=1
        )
        for i in range(12):
            angle = i * (math.pi / 6.0) + (self.angle_step * 0.1)
            x1 = cx + (r_outer - 6) * math.cos(angle)
            y1 = cy + (r_outer - 6) * math.sin(angle)
            x2 = cx + r_outer * math.cos(angle)
            y2 = cy + r_outer * math.sin(angle)
            self.canvas.create_line(x1, y1, x2, y2, fill="#2a3b53", width=1)

        # 2. Concentric Orbit Rings for the 4 Swarm Agents
        for spec in SWARM_SPECS:
            orb_r = spec["orbit_r"]
            self.canvas.create_oval(
                cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r,
                outline="#182334", width=1
            )
            # Update and draw orbiting agent dot
            spd = spec["speed"]
            # Double speed if agent is active in telemetry
            agent_telemetry = next((a for a in state.get("agents", []) if a.get("id") == spec["id"]), None)
            if agent_telemetry and agent_telemetry.get("status") == "ACTIVE":
                spd *= 2.5

            self.agent_angles[spec["id"]] = (self.agent_angles[spec["id"]] + spd) % (2 * math.pi)
            ag_angle = self.agent_angles[spec["id"]]
            ax = cx + orb_r * math.cos(ag_angle)
            ay = cy + orb_r * math.sin(ag_angle)
            dot_r = spec["size"]

            # Orbiting Agent Dot
            self.canvas.create_oval(
                ax - dot_r, ay - dot_r, ax + dot_r, ay + dot_r,
                fill=spec["color"], outline="#ffffff", width=1
            )

        # 3. Audio Turn Visualizer (LISTENING pulse / SPEAKING waveform)
        if status == "LISTENING":
            pulse_r = 38 + 12 * math.sin(self.pulse_phase)
            self.canvas.create_oval(
                cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r,
                outline=core_color, width=2
            )
        elif status == "SPEAKING":
            # Dynamic radiating audio waveform arcs
            for offset in (0.0, 1.0, 2.0):
                w_phase = (self.pulse_phase + offset) % (2 * math.pi)
                arc_r = 38 + (w_phase / (2 * math.pi)) * 26
                alpha_width = max(1, int(3 - (w_phase / (2 * math.pi)) * 2))
                self.canvas.create_oval(
                    cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r,
                    outline=core_color, width=alpha_width
                )

        # 4. Central Core Ring (DAKU Brain)
        core_r = 36
        # Outer rotating dashed arc
        dash_angle = (self.angle_step * 57.3) % 360
        self.canvas.create_arc(
            cx - core_r - 4, cy - core_r - 4, cx + core_r + 4, cy + core_r + 4,
            start=dash_angle, extent=120, outline=core_color, width=2, style="arc"
        )
        self.canvas.create_arc(
            cx - core_r - 4, cy - core_r - 4, cx + core_r + 4, cy + core_r + 4,
            start=dash_angle + 180, extent=120, outline=core_color, width=2, style="arc"
        )

        # Central Solid Circle
        self.canvas.create_oval(
            cx - core_r, cy - core_r, cx + core_r, cy + core_r,
            fill="#090d16", outline=core_color, width=2
        )

        # Central Text Readout
        pass_count = state.get("pass_count", 0)
        sess_snippet = state.get("session_id", "")
        if sess_snippet and len(sess_snippet) > 8:
            sess_snippet = sess_snippet[-6:]

        # Line 1: Status
        self.canvas.create_text(
            cx, cy - 14,
            text=status[:14],
            fill=core_color,
            font=("Segoe UI", 7, "bold"),
            justify="center",
        )

        # Line 2: DeepSeek Harness Pass / Telemetry
        telemetry_label = f"dsh P:{pass_count}" if pass_count > 0 else "DAKU AI"
        self.canvas.create_text(
            cx, cy + 1,
            text=telemetry_label,
            fill="#e2e8f0",
            font=("Segoe UI", 8, "bold"),
            justify="center",
        )

        # Line 3: Model / Session Snippet
        model_name = state.get("sun", {}).get("model", "deepseek-chat")
        model_short = "R1-Distill" if "r1" in model_name.lower() else "V3-Chat"
        sub_text = f"{model_short} #{sess_snippet}" if sess_snippet else model_short
        self.canvas.create_text(
            cx, cy + 15,
            text=sub_text,
            fill="#94a3b8",
            font=("Segoe UI", 6),
            justify="center",
        )

        # 5. Inline Confirmation Banner (when AWAITING_CONFIRMATION)
        if status in ("AWAITING_CONFIRMATION", "CONFIRMATION_REQUIRED") or state.get("confirmation_pending"):
            self._render_confirmation_banner(cx, cy)

    def _render_confirmation_banner(self, cx: int, cy: int) -> None:
        """Renders the high-visibility confirmation prompt banner."""
        if not self.canvas:
            return

        box_w = 200
        box_h = 44
        bx1 = cx - box_w // 2
        by1 = HUD_SIZE - box_h - 10
        bx2 = cx + box_w // 2
        by2 = HUD_SIZE - 10

        # Background card
        self.canvas.create_rectangle(
            bx1, by1, bx2, by2,
            fill="#1f1406", outline="#ff9e00", width=2
        )

        # Alert header
        self.canvas.create_text(
            cx, by1 + 12,
            text="PERMISSION CONFIRMATION",
            fill="#ff9e00",
            font=("Segoe UI", 7, "bold"),
        )

        # Action cue
        self.canvas.create_text(
            cx, by1 + 28,
            text="[Y] YES    [N] NO    [C] CANCEL",
            fill="#ffffff",
            font=("Segoe UI", 8, "bold"),
        )

    def _animation_loop(self) -> None:
        """Throttled render loop capped at 60 FPS when active, 15 FPS when idle."""
        if not self.root:
            return

        self.render_frame()

        state = self.client.get_state()
        status = state.get("status", "OFFLINE")

        # Dynamic frame throttling:
        # Active states (LISTENING, SPEAKING, THINKING, EXECUTING) -> ~60 FPS (16 ms)
        # Idle states (STANDBY, OFFLINE) -> ~15 FPS (66 ms) for < 1% CPU
        if status in ("LISTENING", "SPEAKING", "THINKING", "EXECUTING"):
            delay_ms = 16
        else:
            delay_ms = 66

        self._after_id = self.root.after(delay_ms, self._animation_loop)

    def run(self) -> None:
        """Starts client poller and Tkinter event loop."""
        self.setup_window()
        self.client.start()
        self._animation_loop()
        try:
            if self.root:
                self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

    def quit(self) -> None:
        """Clean shutdown of HUD window, tray icon, and polling client."""
        if self._after_id and self.root:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass

        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass

        try:
            self.client.stop()
        except Exception:
            pass

        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None


def main() -> None:
    """CLI Entrypoint for DAKU Desktop HUD."""
    client = HUDTelemetryClient()
    hud = JarvisDesktopHUD(client=client, enable_tray=True)
    hud.run()


if __name__ == "__main__":
    main()
