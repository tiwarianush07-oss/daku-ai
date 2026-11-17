"""
DAKU SystemTool Module
Queries real local Windows hardware and OS metrics with zero overhead.
Uses ctypes / standard library for 0-RAM, instant RAM/CPU/Disk/Time/Network queries.
"""

import ctypes
import datetime
import os
import platform
import shutil
import socket
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, PermissionLevel, ToolParameter, ToolResult


class MEMORYSTATUSEX(ctypes.Structure):
    """Windows API structure for querying system RAM."""
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


class SystemTool(BaseTool):
    """Allowlisted tool for local system, hardware, and environment diagnostics."""

    name: str = "system_tool"
    description: str = "Query real local hardware metrics: RAM, CPU, disk space, Windows version, current time, and network."
    permission_level: PermissionLevel = PermissionLevel.SAFE

    parameters: List[ToolParameter] = [
        ToolParameter(
            name="query",
            type="string",
            description="The metric to query: 'ram', 'cpu', 'disk', 'windows_ver', 'time', 'network', or 'all'.",
            enum=["ram", "cpu", "disk", "windows_ver", "time", "network", "all"],
            required=True,
        ),
        ToolParameter(
            name="drive",
            type="string",
            description="Drive letter (e.g., 'C:\\') for disk space query.",
            required=False,
            default="C:\\",
        ),
    ]

    def get_ram_info(self) -> ToolResult:
        """Queries physical RAM via Windows GlobalMemoryStatusEx (0 extra RAM)."""
        try:
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

            total_gb = round(stat.ullTotalPhys / (1024 ** 3), 2)
            avail_gb = round(stat.ullAvailPhys / (1024 ** 3), 2)
            used_gb = round(total_gb - avail_gb, 2)
            load_pct = stat.dwMemoryLoad

            data = {
                "total_gb": total_gb,
                "free_gb": avail_gb,
                "used_gb": used_gb,
                "load_percent": load_pct,
            }
            msg = f"You have approximately {avail_gb} GB of free RAM out of {total_gb} GB total."
            return ToolResult(success=True, data=data, message=msg, verified=True)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to query RAM: {str(e)}",
                message="Unable to read system memory status.",
            )

    def get_cpu_info(self) -> ToolResult:
        """Queries CPU processor model and logical core count."""
        processor = platform.processor() or "AMD / Intel x64"
        cores = os.cpu_count() or 2
        arch = platform.machine()

        data = {
            "processor": processor,
            "logical_cores": cores,
            "architecture": arch,
        }
        msg = f"CPU is {processor} with {cores} logical cores on {arch}."
        return ToolResult(success=True, data=data, message=msg, verified=True)

    def get_disk_info(self, drive: str = "C:\\") -> ToolResult:
        """Queries total, used, and free disk space."""
        try:
            drive_root = drive if os.path.exists(drive) else "C:\\"
            usage = shutil.disk_usage(drive_root)

            total_gb = round(usage.total / (1024 ** 3), 2)
            free_gb = round(usage.free / (1024 ** 3), 2)
            used_gb = round(usage.used / (1024 ** 3), 2)

            data = {
                "drive": drive_root,
                "total_gb": total_gb,
                "free_gb": free_gb,
                "used_gb": used_gb,
            }
            msg = f"Drive {drive_root} has {free_gb} GB free out of {total_gb} GB total."
            return ToolResult(success=True, data=data, message=msg, verified=True)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Disk query error: {str(e)}",
                message="Unable to check disk space.",
            )

    def get_windows_version(self) -> ToolResult:
        """Queries Windows OS edition and build."""
        os_name = f"{platform.system()} {platform.release()}"
        ver = platform.version()
        arch = platform.machine()

        data = {"os": os_name, "version": ver, "architecture": arch}
        msg = f"Running on {os_name} (Build {ver}, {arch})."
        return ToolResult(success=True, data=data, message=msg, verified=True)

    def get_current_time(self) -> ToolResult:
        """Returns formatted local time and date."""
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d, %Y")

        data = {"time": time_str, "date": date_str, "iso": now.isoformat()}
        msg = f"The current time is {time_str} on {date_str}."
        return ToolResult(success=True, data=data, message=msg, verified=True)

    def get_network_status(self) -> ToolResult:
        """Checks internet connectivity without large payload."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(("8.8.8.8", 53))
            connected = True
            msg = "Internet connection is active and connected."
        except Exception:
            connected = False
            msg = "Computer appears to be offline or network is unreachable."

        return ToolResult(
            success=True,
            data={"connected": connected},
            message=msg,
            verified=True,
        )

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Routes to requested system query."""
        query = args.get("query", "ram").lower()
        drive = args.get("drive", "C:\\")

        if query in ("ram", "memory"):
            return self.get_ram_info()
        elif query in ("cpu", "processor"):
            return self.get_cpu_info()
        elif query in ("disk", "storage", "drive"):
            return self.get_disk_info(drive)
        elif query in ("windows_ver", "os", "version"):
            return self.get_windows_version()
        elif query in ("time", "date", "clock"):
            return self.get_current_time()
        elif query in ("network", "internet", "wifi"):
            return self.get_network_status()
        elif query == "all":
            ram = self.get_ram_info().data
            cpu = self.get_cpu_info().data
            disk = self.get_disk_info().data
            time_info = self.get_current_time().data
            return ToolResult(
                success=True,
                data={"ram": ram, "cpu": cpu, "disk": disk, "time": time_info},
                message=f"System OK: {ram['free_gb']} GB RAM free, {disk['free_gb']} GB disk free. Time: {time_info['time']}.",
                verified=True,
            )
        else:
            return ToolResult(
                success=False,
                error=f"Unknown system query: '{query}'.",
                message=f"Unknown system metric '{query}'.",
            )
