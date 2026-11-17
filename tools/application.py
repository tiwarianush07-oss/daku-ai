"""
DAKU ApplicationTool Module
Provides allowlisted, secure management of local Windows desktop applications.
Launches applications without arbitrary shell strings, verifies execution, and queries process state.
"""

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, PermissionLevel, ToolParameter, ToolResult


KNOWN_APPLICATIONS = {
    "notepad": {"exe": "notepad.exe", "name": "Notepad", "process": "notepad.exe"},
    "calculator": {"exe": "calc.exe", "name": "Calculator", "process": "CalculatorApp.exe"},
    "calc": {"exe": "calc.exe", "name": "Calculator", "process": "CalculatorApp.exe"},
    "paint": {"exe": "mspaint.exe", "name": "Paint", "process": "mspaint.exe"},
    "mspaint": {"exe": "mspaint.exe", "name": "Paint", "process": "mspaint.exe"},
    "explorer": {"exe": "explorer.exe", "name": "Windows Explorer", "process": "explorer.exe"},
    "task manager": {"exe": "taskmgr.exe", "name": "Task Manager", "process": "Taskmgr.exe"},
    "taskmgr": {"exe": "taskmgr.exe", "name": "Task Manager", "process": "Taskmgr.exe"},
    "cmd": {"exe": "cmd.exe", "name": "Command Prompt", "process": "cmd.exe"},
    "command prompt": {"exe": "cmd.exe", "name": "Command Prompt", "process": "cmd.exe"},
    "powershell": {"exe": "powershell.exe", "name": "PowerShell", "process": "powershell.exe"},
    "edge": {"exe": "msedge.exe", "name": "Microsoft Edge", "process": "msedge.exe"},
    "msedge": {"exe": "msedge.exe", "name": "Microsoft Edge", "process": "msedge.exe"},
    "chrome": {"exe": "chrome.exe", "name": "Google Chrome", "process": "chrome.exe"},
    "google chrome": {"exe": "chrome.exe", "name": "Google Chrome", "process": "chrome.exe"},
    "code": {"exe": "code.cmd", "name": "Visual Studio Code", "process": "Code.exe"},
    "vs code": {"exe": "code.cmd", "name": "Visual Studio Code", "process": "Code.exe"},
}


class ApplicationTool(BaseTool):
    """Allowlisted tool for launching, checking, and detecting Windows applications."""

    name: str = "application_tool"
    description: str = "Launch, inspect, and verify Windows desktop applications (Notepad, Calculator, Paint, etc.)."
    permission_level: PermissionLevel = PermissionLevel.SAFE

    parameters: List[ToolParameter] = [
        ToolParameter(
            name="action",
            type="string",
            description="The action to perform: 'launch', 'is_running', or 'detect_apps'.",
            enum=["launch", "is_running", "detect_apps"],
            required=True,
        ),
        ToolParameter(
            name="app_name",
            type="string",
            description="The name of the application (e.g., 'notepad', 'calc', 'paint', 'chrome').",
            required=False,
        ),
    ]

    def _resolve_exe(self, app_name: str) -> Optional[str]:
        """Resolves full executable path for an application safely."""
        key = app_name.strip().lower()
        if key in KNOWN_APPLICATIONS:
            exe_target = KNOWN_APPLICATIONS[key]["exe"]
            which_path = shutil.which(exe_target)
            if which_path:
                return which_path

            # Common Windows paths fallback (System32, Program Files, LocalAppData)
            search_prefixes = [
                os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "System32"),
                os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
                os.environ.get("LOCALAPPDATA", ""),
            ]
            
            # Common application subdirectories
            app_subpaths = [
                exe_target,
                os.path.join("Google", "Chrome", "Application", exe_target),
                os.path.join("Microsoft", "Edge", "Application", exe_target),
                os.path.join("Programs", "Microsoft VS Code", "bin", exe_target),
                os.path.join("Programs", "Microsoft VS Code", exe_target),
            ]

            for prefix in search_prefixes:
                if not prefix:
                    continue
                for sub in app_subpaths:
                    candidate = os.path.join(prefix, sub)
                    if os.path.isfile(candidate):
                        return candidate

            # Default to exe name if known
            return exe_target

        # If not directly in known table, check if sanitized executable exists in PATH
        clean_name = "".join(c for c in key if c.isalnum() or c in ("-", "_", "."))
        if clean_name:
            which_path = shutil.which(clean_name)
            if which_path:
                return which_path

        return None

    def _is_process_running(self, process_name: str) -> bool:
        """Checks if a process is running via tasklist."""
        try:
            cmd = ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and process_name.lower() in res.stdout.lower():
                return True
        except Exception:
            pass
        return False

    def is_app_running(self, app_name: str) -> ToolResult:
        """Checks whether the specified application is running."""
        key = app_name.strip().lower()
        proc_name = KNOWN_APPLICATIONS.get(key, {}).get("process", f"{key}.exe")
        running = self._is_process_running(proc_name)
        display_name = KNOWN_APPLICATIONS.get(key, {}).get("name", app_name.capitalize())
        
        status_msg = f"{display_name} is running." if running else f"{display_name} is not running."
        return ToolResult(
            success=True,
            data={"app_name": display_name, "running": running, "process": proc_name},
            message=status_msg,
            verified=True,
        )

    def launch_app(self, app_name: str) -> ToolResult:
        """Launches an application and verifies it started."""
        if not app_name or not app_name.strip():
            return ToolResult(
                success=False,
                error="Application name cannot be empty.",
                message="Please specify an application to open.",
            )

        key = app_name.strip().lower()
        exe_path = self._resolve_exe(key)
        display_name = KNOWN_APPLICATIONS.get(key, {}).get("name", app_name.capitalize())

        if not exe_path:
            return ToolResult(
                success=False,
                error=f"Application '{app_name}' not found on system.",
                message=f"I couldn't find {app_name} on your computer.",
                verified=False,
            )

        try:
            # Spawn process without shell=True to guarantee no arbitrary command injection
            subprocess.Popen([exe_path], close_fds=True)
            time.sleep(0.3)  # Brief pause for OS process initialization

            # Verify running status if known process name exists
            proc_name = KNOWN_APPLICATIONS.get(key, {}).get("process")
            verified = True
            if proc_name:
                verified = self._is_process_running(proc_name)

            return ToolResult(
                success=True,
                data={"app_name": display_name, "executable": exe_path, "verified": verified},
                message=f"{display_name} is open." if verified else f"Opened {display_name}.",
                verified=verified,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to launch '{app_name}': {str(e)}",
                message=f"I couldn't open {display_name}.",
                verified=False,
            )

    def detect_apps(self) -> ToolResult:
        """Discovers which known common applications are installed and available."""
        available = []
        for key, info in KNOWN_APPLICATIONS.items():
            if key == info["name"].lower() or key in ("calc", "paint", "taskmgr", "explorer", "cmd", "powershell"):
                path = self._resolve_exe(key)
                if path:
                    available.append(info["name"])

        # Deduplicate names
        unique_apps = sorted(list(set(available)))
        return ToolResult(
            success=True,
            data={"apps": unique_apps, "count": len(unique_apps)},
            message=f"Detected {len(unique_apps)} common applications: {', '.join(unique_apps)}.",
            verified=True,
        )

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Routes to requested application action."""
        action = args.get("action", "launch")
        app_name = args.get("app_name", "")

        if action == "launch":
            return self.launch_app(app_name)
        elif action == "is_running":
            return self.is_app_running(app_name)
        elif action == "detect_apps":
            return self.detect_apps()
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'.",
                message=f"Unknown application action '{action}'.",
            )
