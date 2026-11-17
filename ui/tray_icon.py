"""
DAKU Phase 9: Windows Native System Tray Integration
Uses pure ctypes Win32 APIs (Shell_NotifyIconW, user32.dll).
Zero external dependencies (no pystray, no PyQt, no C extensions).
Provides:
- Native notification area icon.
- Right-click and left-click popup context menu.
- Show/Hide HUD, Toggle Click-Through, and Quit actions.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("daku.ui.tray")

# Win32 Constants
WM_USER = 0x0400
WM_TRAYMESSAGE = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_NULL = 0x0000
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IDI_APPLICATION = 32512
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020

# Command IDs
CMD_TOGGLE_VISIBLE = 1001
CMD_TOGGLE_CLICKTHROUGH = 1002
CMD_QUIT = 1003


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.wintypes.DWORD),
        ("Data2", ctypes.wintypes.WORD),
        ("Data3", ctypes.wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uID", ctypes.wintypes.UINT),
        ("uFlags", ctypes.wintypes.UINT),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.wintypes.DWORD),
        ("dwStateMask", ctypes.wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", ctypes.wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", ctypes.wintypes.HICON),
    ]


class Win32TrayIcon:
    """Manages a native Windows system tray icon on a dedicated daemon thread."""

    def __init__(
        self,
        tooltip: str = "DAKU JARVIS HUD",
        on_toggle_visible: Optional[Callable[[], None]] = None,
        on_toggle_clickthrough: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ):
        self.tooltip = tooltip
        self.on_toggle_visible = on_toggle_visible
        self.on_toggle_clickthrough = on_toggle_clickthrough
        self.on_quit = on_quit

        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._wnd_class_atom = None
        self._wnd_proc = None

    def start(self) -> None:
        """Starts the Win32 message pump thread and registers the tray icon."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_tray, daemon=True, name="DakuTrayThread")
            self._thread.start()

    def stop(self) -> None:
        """Removes the tray icon and cleans up the message window."""
        with self._lock:
            self._running = False
            hwnd = self._hwnd

        if hwnd and ctypes.windll.user32.IsWindow(hwnd):
            # Remove tray icon
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            # Post destroy message
            ctypes.windll.user32.PostMessageW(hwnd, WM_DESTROY, 0, 0)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Tray icon stopped.")

    def _show_menu(self, hwnd: int) -> None:
        """Displays the popup context menu at current cursor coordinates."""
        user32 = ctypes.windll.user32
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, MF_STRING, CMD_TOGGLE_VISIBLE, "Show / Hide HUD")
        user32.AppendMenuW(hmenu, MF_STRING, CMD_TOGGLE_CLICKTHROUGH, "Toggle Click-Through")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, CMD_QUIT, "Quit HUD")

        user32.SetForegroundWindow(hwnd)
        user32.TrackPopupMenuEx(
            hmenu,
            TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
            pt.x,
            pt.y,
            hwnd,
            None,
        )
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(hmenu)

    def _wnd_proc_callback(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Window procedure handling tray notification messages."""
        user32 = ctypes.windll.user32
        if msg == WM_TRAYMESSAGE:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
                self._show_menu(hwnd)
                return 0
        elif msg == WM_COMMAND:
            cmd_id = wparam & 0xFFFF
            if cmd_id == CMD_TOGGLE_VISIBLE:
                if self.on_toggle_visible:
                    self.on_toggle_visible()
                return 0
            elif cmd_id == CMD_TOGGLE_CLICKTHROUGH:
                if self.on_toggle_clickthrough:
                    self.on_toggle_clickthrough()
                return 0
            elif cmd_id == CMD_QUIT:
                if self.on_quit:
                    self.on_quit()
                return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run_tray(self) -> None:
        """Worker thread hosting the Win32 message loop."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long,
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        )

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.UINT),
                ("style", ctypes.wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.wintypes.HINSTANCE),
                ("hIcon", ctypes.wintypes.HICON),
                ("hCursor", ctypes.wintypes.HANDLE),
                ("hbrBackground", ctypes.wintypes.HBRUSH),
                ("lpszMenuName", ctypes.wintypes.LPCWSTR),
                ("lpszClassName", ctypes.wintypes.LPCWSTR),
                ("hIconSm", ctypes.wintypes.HICON),
            ]

        # Prevent garbage collection of callback
        self._wnd_proc = WNDPROC(self._wnd_proc_callback)
        class_name = f"DakuTrayWindowClass_{id(self)}"

        wcex = WNDCLASSEXW()
        wcex.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcex.lpfnWndProc = self._wnd_proc
        wcex.hInstance = kernel32.GetModuleHandleW(None)
        wcex.lpszClassName = class_name

        atom = user32.RegisterClassExW(ctypes.byref(wcex))
        if not atom:
            logger.warning("RegisterClassExW failed for tray window.")
            return
        self._wnd_class_atom = atom

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "DakuTrayHiddenWindow",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            wcex.hInstance,
            None,
        )
        if not hwnd:
            logger.warning("CreateWindowExW failed for tray window.")
            return

        self._hwnd = hwnd

        # Register tray icon
        hicon = user32.LoadIconW(0, IDI_APPLICATION)
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYMESSAGE
        nid.hIcon = hicon
        nid.szTip = self.tooltip[:127]

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        logger.info("Tray icon registered with Shell_NotifyIconW.")

        # Message pump loop
        msg = ctypes.wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup on loop exit
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(class_name, wcex.hInstance)
        self._hwnd = None
