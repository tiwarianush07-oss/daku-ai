# DAKU — Personal Voice AI Agent

DAKU is a lightweight, modular Personal Voice AI Agent designed for Windows 11 on hardware with constrained memory (AMD Athlon Silver 3050U, 4 GB RAM).

---

## Architecture (Phase 4: DeepSeek Harness + Uncensored Backend + MCP Orchestration)

```
USER (Push-to-Talk / Enter)
 ↓
MICROPHONE (Realtek / Windows Sound Mapper) [Fallback: Text Input]
 ↓
SPEECH-TO-TEXT (SpeechRecognition Cloud STT)
 ↓
DAKU BRAIN (BackendFactory: DirectModelBackend | DeepSeekHarnessBackend | UncensoredR1Backend)
 ↓
TASK PLANNER & AGENT LOOP
 [PLANNING → AWAITING_CONFIRMATION → EXECUTING → VERIFYING → COMPLETED]
 (Failure Path: EXECUTING → FAILED → RECOVERY / REPORT)
 (Strict Guards: Max 10 steps, max 2 automatic retries per step)
 ↓
TOOL ROUTER (Priority: Native DAKU → Approved MCP → Fallback → Refusal)
 ├── BrowserTool (Launch, navigate, get_title, get_text, inspect_links, verify_page)
 ├── ApplicationTool (Launch, is_running, detect)
 ├── FileTool (List, search, metadata, read, create)
 ├── SystemTool (RAM via ctypes, CPU, disk, time, OS)
 └── Dynamic MCP Tools (chrome-devtools-mcp, code-review-graph, netlify-mcp, etc.)
 ↓
PERMISSION MANAGER (SAFE, CONFIRMATION_REQUIRED, BLOCKED)
 ↓
LOCAL / MCP VERIFIED EXECUTION (Allowlisted executor with post-action verification)
 ↓
TEXT-TO-SPEECH (Windows Native SAPI - Microsoft David/Zira Desktop)
 ↓
AUDIO OUTPUT (Spoken Response)
```

---

## Key Features

- **Phase 4 Agent Backends (`brain/backend.py`)**:
  - **`DirectModelBackend`**: Direct cloud LLM connection via OpenAI-compatible endpoints with function calling.
  - **`DeepSeekHarnessBackend`**: Modular agent orchestration client conforming to the official DeepSeek Harness architecture (session state management, remote execution, tool dispatch).
  - **`UncensoredR1Backend`**: Remote backend for DeepSeek R1 Distill / Uncensored endpoints (`/v1/inference` and `/chat/completions`) with automatic `<think>...</think>` tag stripping for voice synthesis.
- **Model Freedom vs Computer Safety**: Legitimate reasoning and planning are unrestricted, but model output **never directly executes OS commands**. Every action routes strictly through `Tool Registry → Permission Manager → Allowlisted Executor → Action Verifier`.
- **Zero Local Heavy LLM (100% Cloud-First)**: Specifically engineered for 4 GB RAM hardware (HP 255 G9, AMD Athlon Silver 3050U). Zero heavy local model inference (< 15 MB working set memory, < 1% CPU).
- **Hardened Agent Loop**: Strict 5-stage lifecycle state machine with an enforced limit of 10 task steps and max 2 retries per step.
- **Existing MCP Server Reuse**: Automatically detects and integrates existing MCP servers (`chrome-devtools-mcp`, `code-review-graph`, `netlify-mcp`, `gemini-api-docs`) without configuration duplication or secret exposure.
- **Strict Security & Secret Masking**: Prohibits arbitrary shell/PowerShell scripts, enforces 3-tier permissions (`SAFE`, `CONFIRMATION_REQUIRED`, `BLOCKED`), and redacts all secrets in logs (`API_KEY=********`).
- **Push-to-Talk Voice Pipeline**: Push-to-Talk speech recognition with automatic silence timeout, network recovery, and 100% offline text fallback.
- **Windows Native Speech**: Built-in SAPI voice synthesis with double-redundant COM fallback.
- **Complete Diagnostic Suite (`doctor.py`)**: Verifies hardware, Python, audio, MCP servers, agent backend, remote connectivity (`--remote`), and enforces the local model guard.
- **Oracle Cloud Always Free Deployment**: Remote headless server (`server/daku_server.py`) and Hermes Agent integration (`hermes gateway`) with lightweight Windows 11 client (`client.py`, < 15 MB RAM).

---

## Quick Start

### 1. System Health Check
```powershell
# Local system diagnostics
py doctor.py

# Remote server & authentication diagnostics
py doctor.py --remote
```

### 2. Run Automated Regression Suite (110 Tests)
```powershell
py -m unittest discover -s tests -v
```

### 3. Start DAKU

#### Mode A: Lightweight Windows 11 Client (Connected to Free Remote Server over HTTPS)
```powershell
py client.py
```
*Memory Working Set: < 15 MB | CPU: 0% Idle | Audio: Windows Native SAPI | Double-redundant offline fallback.*

#### Mode B: Local Standalone Desktop Agent
```powershell
py main.py
```

#### Mode C: Remote Headless Server (Behind Nginx Reverse Proxy on Oracle Always Free)
```bash
python3 server/daku_server.py --host 127.0.0.1 --port 8443
```

---

## Configuration

Copy `.env.example` to `.env` and configure your settings:
```ini
# Backend selection: direct | harness | uncensored
AGENT_BACKEND=direct

# Cloud AI credentials (Hosted API)
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-chat
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=your_api_key_here

# Remote Hosting & Client (Production uses encrypted HTTPS port 443)
DAKU_SERVER_URL=https://your-server-domain-or-ip
DAKU_AUTH_TOKEN=your_secret_auth_token_here
```

---

## Remote Hosting & Deployment Documentation

Detailed documentation is available in the `docs/` folder:
- [Phase 5 Final Certification Report](PHASE_5_FINAL_CERTIFICATION_REPORT.md): Executive certification gate report.
- [Live Certification Runbook](docs/PHASE_5_LIVE_CERTIFICATION.md): Step-by-step production deployment & verification runbook.
- [Live Certification Matrix](docs/PHASE_5_LIVE_CERTIFICATION_MATRIX.md): Complete 23-row verification matrix.
- [Security Certification Audit](docs/PHASE_5_SECURITY_CERTIFICATION.md): Reverse proxy, UFW, bearer auth, and sandboxing audit.
- [Cost Safety Verification](docs/PHASE_5_COST_VERIFICATION.md): Oracle Always Free eligibility, storage caps, and budget alerts.
- [Pre-Deployment Baseline](docs/PHASE_5_PREDEPLOYMENT_BASELINE.md): Pre-Phase 5 environment and test baseline.
- [Oracle Cloud Free Deployment Guide](docs/FREE_DEPLOYMENT_GUIDE.md): Beginner-friendly setup on Always Free Ubuntu.
- [System Architecture](docs/ARCHITECTURE.md): Component diagrams, responsibility matrix, and request flow.
- [Security Policy](docs/SECURITY.md): 3-tier permissions, server hardening, and token security.
- [Cost Control Guide](docs/COST_CONTROL.md): Free tier limits, budget alerts, and zero-cost guarantees.
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md): Decision trees, common error fixes, and logs.
- [Rollback Procedures](docs/ROLLBACK.md): Disaster recovery, snapshot restoration, and local fallback.
