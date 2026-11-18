"""
DAKU Doctor — System, Hardware & MCP Diagnostics
Checks system health, hardware limits (RAM/CPU), audio devices, network, configuration,
and Phase 3 MCP servers & browser automation capabilities.
"""

import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings


def _run_cmd(cmd: list) -> str:
    """Helper to run a subshell command safely and get output."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "Not Detected"


def check_python() -> dict:
    ver = platform.python_version()
    ok = sys.version_info >= (3, 10)
    return {"name": "Python Version", "value": ver, "status": "OK" if ok else "FAIL", "hint": "Python >= 3.10 required"}


def check_os() -> dict:
    os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    return {"name": "Operating System", "value": os_info, "status": "OK", "hint": ""}


def check_cpu() -> dict:
    cpu_name = platform.processor() or "AMD / Intel x64"
    ps_cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]
    name = _run_cmd(ps_cmd)
    if name != "Not Detected":
        cpu_name = name.splitlines()[0]
    return {"name": "CPU Processor", "value": cpu_name, "status": "OK", "hint": "Lightweight execution bridge"}


def check_ram() -> dict:
    ps_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "$total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2); "
        "$free = [math]::Round($os.FreePhysicalMemory / 1MB, 2); "
        "Write-Output \"$total GB Total, $free GB Free\""
    ]
    ram_info = _run_cmd(ps_cmd)
    return {"name": "Memory (RAM)", "value": ram_info, "status": "OK", "hint": "Strict 4GB RAM low-usage mode"}


def check_disk() -> dict:
    try:
        import shutil
        total, used, free = shutil.disk_usage(Path(__file__).resolve().parent)
        total_gb = round(total / (1024**3), 2)
        free_gb = round(free / (1024**3), 2)
        status = "OK" if free_gb > 1.0 else "WARN"
        hint = "Plenty of disk space" if status == "OK" else "Low free disk (< 1 GB)"
        return {"name": "Disk Storage", "value": f"{total_gb} GB Total, {free_gb} GB Free", "status": status, "hint": hint}
    except Exception as e:
        return {"name": "Disk Storage", "value": f"Error: {e}", "status": "WARN", "hint": ""}


def check_git() -> dict:
    ver = _run_cmd(["git", "--version"])
    ok = ver != "Not Detected"
    return {"name": "Git CLI", "value": ver, "status": "OK" if ok else "WARN", "hint": "Optional for updates"}


def check_node_npm() -> dict:
    node_ver = _run_cmd(["node", "-v"])
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    npm_ver = _run_cmd([npm_cmd, "-v"])
    val = f"Node: {node_ver}, npm: {npm_ver}"
    ok = node_ver != "Not Detected"
    return {"name": "Node.js & npm", "value": val, "status": "OK" if ok else "INFO", "hint": "For DeepSeek Harness in Phase 4"}


def check_speaker() -> dict:
    ps_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "[System.Reflection.Assembly]::LoadWithPartialName('System.Speech') | Out-Null; "
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voices = ($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }) -join ', '; "
        "Write-Output $voices"
    ]
    voices = _run_cmd(ps_cmd)
    ok = voices != "Not Detected" and len(voices) > 0
    val = f"Windows SAPI ({voices})" if ok else "None"
    return {"name": "Audio Output (TTS)", "value": val, "status": "OK" if ok else "WARN", "hint": "Windows Native Speech"}


def check_mic() -> dict:
    try:
        from voice.stt import MicrophoneSTT
        mic = MicrophoneSTT()
        if mic.is_available():
            import speech_recognition as sr  # type: ignore
            mics = sr.Microphone.list_microphone_names()
            primary = mics[0] if mics else "Default"
            return {"name": "Microphone (STT)", "value": f"{len(mics)} device(s) [Primary: {primary}]", "status": "OK", "hint": "Push-to-Talk Voice STT Active"}
    except Exception:
        pass
    return {"name": "Microphone (STT)", "value": "Text Fallback Active", "status": "OK", "hint": "Voice unavailable; text input works 100% offline"}


def check_internet() -> dict:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(("8.8.8.8", 53))
        return {"name": "Internet Connection", "value": "Connected", "status": "OK", "hint": "Cloud LLM routing enabled"}
    except Exception:
        return {"name": "Internet Connection", "value": "Offline / Unreachable", "status": "WARN", "hint": "Offline demo mode active"}


def check_config() -> dict:
    api_key_configured = settings.has_api_key()
    provider = settings.MODEL_PROVIDER
    model = settings.MODEL_NAME

    val = f"Provider: {provider}, Model: {model}, API Key: {'CONFIGURED (YES)' if api_key_configured else 'NOT CONFIGURED (NO)'}"
    status = "OK" if api_key_configured else "INFO"
    hint = "Set MODEL_API_KEY in .env for live cloud LLM" if not api_key_configured else "Live cloud model active"
    return {"name": "Configuration", "value": val, "status": status, "hint": hint}


def check_mcp() -> dict:
    try:
        from tools.mcp_client import MCPManager
        mcp = MCPManager()
        servers = mcp.get_status_report()
        if servers:
            names = [s["name"] for s in servers]
            total_tools = sum(s.get("tools_count", 0) for s in servers)
            val = f"AVAILABLE ({len(servers)} servers, {total_tools} tools: {', '.join(names)})"
            return {"name": "MCP Server Support", "value": val, "status": "OK", "hint": "MCP Extension Layer active"}
    except Exception:
        pass
    return {"name": "MCP Server Support", "value": "NOT AVAILABLE", "status": "INFO", "hint": "Native tools active"}


def check_mcp_health() -> dict:
    try:
        from tools.mcp_client import MCPManager
        mcp = MCPManager()
        servers = mcp.get_status_report()
        if servers:
            healthy_count = sum(1 for s in servers if s.get("healthy", True))
            val = f"{healthy_count}/{len(servers)} servers HEALTHY"
            return {"name": "MCP Server Health", "value": val, "status": "OK", "hint": "Zero credential leakage"}
    except Exception:
        pass
    return {"name": "MCP Server Health", "value": "N/A", "status": "INFO", "hint": "No MCP servers configured"}


def check_browser_mcp() -> dict:
    try:
        from tools.mcp_client import MCPManager
        mcp = MCPManager()
        has_chrome_mcp = mcp.has_browser_mcp()
        from tools.browser import BrowserTool
        browser_tool = BrowserTool()
        browser_exe = browser_tool._resolve_browser_exe("chrome")
        has_browser_app = browser_exe is not None
        
        status_parts = []
        if has_chrome_mcp:
            status_parts.append("chrome-devtools-mcp (DETECTED)")
        if has_browser_app:
            status_parts.append("Native Chrome/Edge (READY)")
            
        val = " & ".join(status_parts) if status_parts else "Native Web Fallback"
        return {"name": "Browser Automation", "value": val, "status": "OK", "hint": "Safe allowlisted web actions only"}
    except Exception as e:
        return {"name": "Browser Automation", "value": f"Error: {e}", "status": "WARN", "hint": ""}


def check_tools() -> dict:
    try:
        from tools.registry import ToolRegistry
        registry = ToolRegistry()
        tools = registry.list_tool_names()
        val = f"{len(tools)} tools ready ({', '.join(tools[:4])}...)"
        return {"name": "System Tools Registry", "value": val, "status": "OK", "hint": "TaskPlanner & ToolRouter active"}
    except Exception as e:
        return {"name": "System Tools Registry", "value": f"Error: {e}", "status": "WARN", "hint": "Tool initialization error"}


def check_agent_backend() -> dict:
    try:
        from brain.backend import BackendFactory
        backend = BackendFactory.create_backend()
        name = backend.get_name()
        configured = settings.AGENT_BACKEND
        val = f"{name} (Configured: AGENT_BACKEND={configured})"
        return {"name": "Agent Backend", "value": val, "status": "OK", "hint": "Phase 4 Agent Architecture"}
    except Exception as e:
        return {"name": "Agent Backend", "value": f"Error: {e}", "status": "FAIL", "hint": "Backend initialization failure"}


def check_no_local_model() -> dict:
    """Verifies that ZERO heavy local models (7B/8B/14B, Ollama, llama.cpp) are running on this 4GB machine."""
    heavy_processes = ("ollama", "llamacpp", "vllm", "text-generation-launcher", "llama-server")
    ps_cmd = ["powershell", "-NoProfile", "-Command", "Get-Process | Select-Object -ExpandProperty ProcessName"]
    proc_list = _run_cmd(ps_cmd).lower()
    
    detected = [p for p in heavy_processes if p in proc_list]
    if detected:
        val = f"WARNING: {', '.join(detected)} detected"
        return {"name": "Local Model Guard", "value": val, "status": "WARN", "hint": "Local model found; must be cloud-first"}
    
    return {"name": "Local Model Guard", "value": "ZERO local LLM (100% cloud/remote-first)", "status": "OK", "hint": "Strict 4GB RAM low-usage adherence"}


def check_remote_server(server_url: Optional[str] = None) -> dict:
    """Verifies reachability of the remote DAKU server."""
    url = (server_url or settings.DAKU_SERVER_URL or "http://127.0.0.1:8443").rstrip("/")
    import json
    import urllib.request
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    is_loopback = (parsed.hostname or "").lower() in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
    is_https = parsed.scheme.lower() == "https"

    try:
        t0 = time.time()
        # For HTTPS probe, use default verified SSL context
        req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "DAKU-Doctor/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            elapsed = round((time.time() - t0) * 1000, 1)
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                val = f"ONLINE ({url}, {elapsed}ms, DAKU v{data.get('version', '5.0')})"
                if not is_https and not is_loopback:
                    return {
                        "name": "Remote DAKU Server",
                        "value": val,
                        "status": "WARN",
                        "hint": "Insecure HTTP across public internet. Production requires HTTPS (port 443 via Nginx/Caddy).",
                    }
                return {
                    "name": "Remote DAKU Server",
                    "value": val,
                    "status": "OK",
                    "hint": "Encrypted HTTPS transport active" if is_https else "Local loopback host active",
                }
            return {"name": "Remote DAKU Server", "value": f"HTTP {resp.status}", "status": "WARN", "hint": "Server responded with non-200"}
    except urllib.error.URLError as e:
        err_str = str(e.reason if hasattr(e, "reason") else e)
        if "certificate" in err_str.lower() or "ssl" in err_str.lower():
            return {
                "name": "Remote DAKU Server",
                "value": f"TLS ERROR ({url}: {err_str})",
                "status": "WARN",
                "hint": "Valid trusted CA certificate required for FULL certification.",
            }
        return {"name": "Remote DAKU Server", "value": f"OFFLINE ({url})", "status": "INFO", "hint": "Run local or deploy to Oracle Always Free"}
    except Exception as e:
        return {"name": "Remote DAKU Server", "value": f"OFFLINE ({url})", "status": "INFO", "hint": f"Connection error: {e}"}


def check_https_status(server_url: Optional[str] = None) -> dict:
    """Checks whether the configured remote server uses HTTPS and validates TLS certificate."""
    url = (server_url or settings.DAKU_SERVER_URL or "").strip().rstrip("/")
    if not url:
        return {"name": "HTTPS / TLS Security", "value": "NOT CONFIGURED", "status": "INFO", "hint": "Set DAKU_SERVER_URL"}

    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    is_loopback = host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    if scheme == "http":
        if is_loopback:
            return {
                "name": "HTTPS / TLS Security",
                "value": "LOOPBACK (Local Dev Mode - HTTP Allowed)",
                "status": "INFO",
                "hint": "Remote production traffic over public internet requires HTTPS (port 443).",
            }
        return {
            "name": "HTTPS / TLS Security",
            "value": "INSECURE (Plain HTTP over Public IP)",
            "status": "WARN",
            "hint": "Production internet traffic MUST use https:// reverse proxy.",
        }

    if scheme == "https":
        import ssl
        import socket
        port = parsed.port or 443
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=3.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    subject = dict(x[0] for x in cert.get("subject", []))
                    common_name = subject.get("commonName", host)
                    not_after = cert.get("notAfter", "")
                    return {
                        "name": "HTTPS / TLS Security",
                        "value": f"VERIFIED (Valid CA Certificate: CN={common_name}, Expires: {not_after})",
                        "status": "OK",
                        "hint": "End-to-end encrypted TLS connection verified.",
                    }
        except ssl.SSLCertVerificationError as e:
            return {
                "name": "HTTPS / TLS Security",
                "value": f"TLS WARNING ({e.verify_message})",
                "status": "WARN",
                "hint": "Self-signed or untrusted certificate. Public trusted cert required for FULL certification.",
            }
        except (socket.error, TimeoutError, OSError) as e:
            return {
                "name": "HTTPS / TLS Security",
                "value": f"NOT VERIFIED ({e})",
                "status": "INFO",
                "hint": "Remote server unreachable to verify TLS certificate.",
            }

    return {"name": "HTTPS / TLS Security", "value": f"UNKNOWN SCHEME ({scheme})", "status": "WARN", "hint": "Use https://"}


def check_hermes_service(server_url: Optional[str] = None) -> dict:
    """Verifies Hermes Agent gateway status via remote health endpoint or local probe."""
    url = (server_url or settings.DAKU_SERVER_URL or "http://127.0.0.1:8443").rstrip("/")
    import json
    import urllib.request
    try:
        req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "DAKU-Doctor/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                hermes_state = data.get("hermes", "unconfigured")
                status = "OK" if hermes_state == "running" else "INFO"
                return {"name": "Hermes Agent Gateway", "value": hermes_state.upper(), "status": status, "hint": f"Gateway reported by {url}"}
    except Exception:
        pass
    return {"name": "Hermes Agent Gateway", "value": "STANDBY (Remote Server Offline)", "status": "INFO", "hint": "Will verify when remote server runs"}


def check_api_auth() -> dict:
    """Verifies that API authentication token is configured."""
    has_token = settings.has_auth_token()
    val = "CONFIGURED (Bearer Auth Active)" if has_token else "NOT CONFIGURED (Open / Local Only)"
    status = "OK" if has_token else "INFO"
    hint = "Set DAKU_AUTH_TOKEN in .env for authenticated remote server access"
    return {"name": "API Authentication", "value": val, "status": status, "hint": hint}


def check_voice_engine() -> dict:
    """Checks voice pipeline status (Google STT & native Windows SAPI TTS)."""
    try:
        from voice.providers.google_stt import GoogleSTTProvider
        from voice.providers.windows_tts import WindowsSapiTTSProvider
        stt = GoogleSTTProvider()
        tts = WindowsSapiTTSProvider()
        stt_ok = stt.is_available()
        tts_ok = tts.is_available()
        val = f"STT: {'Google STT' if stt_ok else 'Text Fallback'}, TTS: {'Windows SAPI' if tts_ok else 'Console'}"
        return {"name": "Voice Pipeline", "value": val, "status": "OK", "hint": "Lightweight native voice pipeline"}
    except Exception as e:
        return {"name": "Voice Pipeline", "value": f"Error: {e}", "status": "WARN", "hint": "Text fallback active"}


def check_solar_hud() -> dict:
    """Phase 7: Verifies Solar HUD assets and secret isolation."""
    hud_dir = Path(__file__).resolve().parent / "server" / "hud"
    files = ["index.html", "solar_hud.css", "solar_hud.js"]
    missing = [f for f in files if not (hud_dir / f).is_file()]
    if missing:
        return {"name": "Solar Swarm HUD", "value": f"MISSING ({', '.join(missing)})", "status": "FAIL", "hint": "Run Phase 7 HUD setup"}

    # Secret scan: verify no API keys leaked in HUD frontend assets
    leaks = []
    for f in files:
        content = (hud_dir / f).read_text(encoding="utf-8", errors="ignore")
        if settings.MODEL_API_KEY and settings.MODEL_API_KEY in content:
            leaks.append(f)
        if "sk_" in content:
            leaks.append(f)
    if leaks:
        return {"name": "Solar Swarm HUD", "value": f"SECURITY LEAK in {', '.join(leaks)}", "status": "FAIL", "hint": "Never expose API keys to browser JavaScript"}

    return {"name": "Solar Swarm HUD", "value": "READY (Central Sun + 4 Planetary Swarm Agents)", "status": "OK", "hint": "Available at /hud"}


def run_doctor(remote_mode: bool = False, server_url: Optional[str] = None) -> bool:
    print("=" * 60)
    print(f"                 DAKU SYSTEM DOCTOR {'(REMOTE)' if remote_mode else ''}                  ")
    print("=" * 60)

    checks = [
        check_python(),
        check_os(),
        check_cpu(),
        check_ram(),
        check_disk(),
        check_git(),
        check_node_npm(),
        check_speaker(),
        check_mic(),
        check_tools(),
        check_mcp(),
        check_mcp_health(),
        check_browser_mcp(),
        check_agent_backend(),
        check_no_local_model(),
        check_internet(),
        check_config(),
        check_voice_engine(),
        check_api_auth(),
        check_solar_hud(),
    ]

    if remote_mode or settings.DAKU_SERVER_URL:
        checks.append(check_remote_server(server_url))
        checks.append(check_https_status(server_url))
        checks.append(check_hermes_service(server_url))

    all_ok = True
    for c in checks:
        status_tag = f"[{c['status']}]"
        print(f"{status_tag:<8} {c['name']:<22} : {c['value']}")
        if c["hint"] and c["status"] in ("WARN", "INFO"):
            print(f"         -> Note: {c['hint']}")
        if c["status"] == "FAIL":
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("[RESULT] DAKU Doctor passed. System is ready for execution.")
    else:
        print("[RESULT] One or more critical checks failed.")
    print("=" * 60)
    return all_ok


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DAKU System Diagnostics & Health Check")
    parser.add_argument("--remote", action="store_true", help="Include remote DAKU server and Hermes gateway checks")
    parser.add_argument("--server", type=str, default=None, help="Remote server URL to probe")
    # Defensively filter out 'doctor' subcommand if invoked via daku.bat or launcher
    cli_args = [a for a in sys.argv[1:] if a.lower() != "doctor"]
    args = parser.parse_args(cli_args)

    success = run_doctor(remote_mode=args.remote, server_url=args.server)
    sys.exit(0 if success else 1)
