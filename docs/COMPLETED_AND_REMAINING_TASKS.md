# DAKU — Completed vs. Remaining Tasks & Roadmap
================================================================================

**Project**: DAKU (Personal Voice AI Agent & Autonomous Swarm)  
**Host Architecture**: Windows 10/11 AMD64 (AMD Athlon Silver 3050U, 4 GB RAM)  
**System Profile**: Zero-local LLM, ultra-low memory (<25 MB server working set)  
**Regression Test Status**: **231 / 231 tests passing** (0 failures, 2 skipped)  
**DeepSeek Harness (`dsh`) Status**: **INTEGRATED & VERIFIED** (Cordis Bridge Active)  
**Native Desktop HUD Status**: **COMPLETED & CERTIFIED** (Phase 9 Win32 Tkinter Overlay)  
**Date**: November 2026  

---

## 1. Executive Summary

| Category | Total Items | Completed / Ready | Remaining / Pending | Progress |
| :--- | :---: | :---: | :---: | :---: |
| **Core Architecture & Engine** | 8 Phases | 8 Phases | 0 Phases | **100%** |
| **User Interfaces (Voice, Web, CLI, Desktop)** | 4 Interfaces | 4 Interfaces | 0 Interfaces | **100%** |
| **Planned Architectural Milestones** | 5 Milestones | 3 Completed | 2 Milestones (Phases 10, 11) | **60%** |
| **Environment & Cloud Keys** | 3 Keys | 0 Active | 3 Pending Configuration | **Action Required** |
| **Production Cloud Deployment** | 5 Tasks | 0 Deployed | 5 Pending Tasks | **Action Required** |
| **Overall Project Scope** | **25 Tracked Items** | **15 Completed (60%)** | **10 Pending (40%)** | **60%** |

```mermaid
pie title DAKU Project Status Breakdown
    "Completed Capabilities & Milestones (15)" : 60
    "Pending Milestones, Keys & Deployment (10)" : 40
```

---

## 2. Completed Capabilities (What is Done)

### [COMPLETED] Phase 1: Voice MVP & Audio Pipeline
- **Push-to-Talk Speech Recognition**: Windows microphone capture via `speech_recognition` with automatic silence detection and offline fallback.
- **Native Windows Speech Synthesis (TTS)**: Built-in Windows SAPI (`Microsoft David` / `Microsoft Zira`) with double-redundant COM error handling.
- **Text Fallback**: Headless and keyboard-driven text input/output when no audio devices are available.

### [COMPLETED] Phase 2: Local Computer Agent & 3-Tier Security
- **Native OS Tool Suite**:
  - `application.py`: Detect installed apps, launch approved software, verify running processes.
  - `browser.py`: Web browsing, searching, title/text extraction, DOM inspection.
  - `file_ops.py`: Safe listing, searching, reading, creating, and metadata checks.
  - `system.py`: Hardware inspection (ctypes-based RAM, CPU load, disk usage, OS info).
- **Security Boundaries**:
  - 3-tier permission model: `SAFE` (automatic execution), `CONFIRMATION_REQUIRED` (user approval needed), and strictly `BLOCKED` (prohibited actions).
  - Absolute ban on raw PowerShell/command-line execution.
  - Automated masking and redaction of credentials in logs and outputs.

### [COMPLETED] Phase 3: Multi-Step Task Automation & State Machine
- **TaskPlanner State Machine**: Deterministic 5-stage lifecycle (`PLANNING` → `AWAITING_CONFIRMATION` → `EXECUTING` → `VERIFYING` → `COMPLETED`).
- **Safety Circuit Breakers**: Hard limits of maximum 10 steps per task and maximum 2 automatic retries per step.
- **Real-World Verification Gate**: Actions must be verified against actual OS state before reporting completion.
- **Tool Routing**: Native tools take priority; falls back gracefully to registered MCP tools.

### [COMPLETED] Phase 4: Remote Cloud Backends & Zero-Local LLM Guard
- **Backend Implementations**:
  - `DirectModelRouter`: Direct cloud LLM connection via OpenAI-compatible endpoints with function calling.
  - `DeepSeekHarnessBackend`: Session state management and tool dispatch conforming to DeepSeek Harness architecture.
  - `UncensoredR1Backend`: Support for DeepSeek R1 Distill / Uncensored endpoints with automated `<think>...</think>` tag stripping for voice output.
- **Local Model Guard**: Zero heavy local model inference (<15 MB working set memory, <1% idle CPU).

### [COMPLETED] Phase 5 & 5.5: Remote Hosting & Hands-Free Voice Confirmation
- **Lightweight Server Daemon**: HTTP/REST daemon (`server/daku_server.py`) built with Python standard library (`http.server`).
- **Security & Auth**: Constant-time Bearer token verification and loopback-safe local development mode.
- **Voice Confirmation Loop**: Hands-free voice authorization parsing `YES`, `NO`, `CANCEL`, and `STOP`.
- **Cloud Infrastructure Config**: Oracle Cloud Always Free deployment scripts, UFW firewall rules, and systemd service descriptors.

### [COMPLETED] Phase 6: Adaptive Multi-Pass Reasoning & Safe Self-Learning
- **`MultiPassReasoner` (`brain/multipass.py`)**: Dynamic complexity budgeting (1 to 8 passes) based on task difficulty.
- **Loop Protection**: Repeated action detection prevents runaway loops.
- **`ReflectionEngine` (`brain/reflection.py`)**: Automatic failure diagnosis and safe strategy pivoting (e.g. Edge when Chrome fails).
- **`LearningEngine` (`brain/learning.py`)**: Compact, bounded lesson store (max 500 lessons) to remember successful strategies without code alteration.

### [COMPLETED] Phase 6.1: Sarvam AI Voice Agent Integration
- **Indian Language Support**: Integrated Sarvam Saaras:v4 STT and Bulbul:v3 TTS.
- **Resilient Fallback**: Automatic failover to Google STT and Windows SAPI if Sarvam API key is missing or network times out.

### [COMPLETED] Phase 7: Solar Swarm HUD v7.0.0 (Web Dashboard UI)
- **Celestial Visual Engine**: 2D/3D Canvas visualizer with Central Sun (DAKU Brain) and 4 planetary swarm agents (Researcher, Coder, Vision Analyst, Executive Strategist).
- **Real Voice Turn Loop**: Browser Web Audio API microphone capture, audio playback, and 10 UI status states (`STANDBY` to `OFFLINE`).
- **Telemetry & Capability Drawer**: Real-time agent status inspection via `/api/hud/agents`.
- **Safe Profile Management**: Add/switch agent profiles with privilege escalation prevention.

### [COMPLETED] Phase 8: MCP Permission Gateway Hardening
- **`brain/mcp_gateway.py` & `config/mcp_acl.json`**:
  - Declarative per-server and per-tool Access Control Lists (ACLs).
  - Unknown server safety fallback: any server not explicitly registered defaults to `CONFIRMATION_REQUIRED`.
  - Token Isolation Boundary: strips `MODEL_API_KEY`, `SARVAM_API_KEY`, `DAKU_AUTH_TOKEN`, and other secrets from child MCP process environments unless explicitly allowlisted.
  - In-Memory Token-Bucket Rate Limiter: prevents runaway tool loops using `time.monotonic()` with per-server refill rates and burst capacities.
  - Certified by 5/5 unit tests in `tests/test_mcp_gateway.py`.

### [COMPLETED] Phase 9: JARVIS Native Desktop HUD UI
- **`ui/desktop_hud.py`**:
  - Frameless, always-on-top, tool-window overlay window using `tkinter.Canvas` with Win32 `ctypes` layered transparency (`WS_EX_TOPMOST`, `WS_EX_TOOLWINDOW`, `WS_EX_LAYERED`).
  - Circular JARVIS visualizer: central core ring colored across 10 live DAKU states (`STANDBY` to `OFFLINE`).
  - 4 planetary orbit indicators synced to Solar Swarm agents (`Researcher`, `Coder`, `Vision Analyst`, `Executive Strategist`).
  - Radial pulse waveform for `LISTENING` and dynamic radiating audio bars for `SPEAKING`.
  - High-visibility inline confirmation banner for `AWAITING_CONFIRMATION` (`CONFIRMATION_REQUIRED`) with `[Y]` / `[N]` / `[C]` keyboard hotkeys.
  - Drag-to-reposition and toggleable click-through mode (`WS_EX_TRANSPARENT`).
- **`ui/hud_client.py`**:
  - Non-blocking loopback polling daemon for `/api/hud/agents` with dynamic intervals (`500ms` active, `2000ms` idle).
  - Bearer token authentication without secret leakage.
  - Smooth transition to `OFFLINE` on connection errors without CPU spikes.
  - Confirmation dispatch to `POST /api/confirm`.
- **`ui/tray_icon.py`**:
  - Pure `ctypes` Win32 notification icon via `Shell_NotifyIconW` (zero external dependencies).
  - Context popup menu: Show/Hide HUD, Toggle Click-Through, Quit.
- **Budget Compliance**: Verified `<15 MB` private RAM working set, `<1%` idle CPU, 9/9 unit tests passing.

### [COMPLETED] Phase 14: AI Tools & MCP Ecosystem
- **Ponytail (v4.10.0)**: Over-engineering auditor and complexity reviewer.
- **Context7 (v4.5.0)**: Up-to-date documentation resolution MCP server.
- **Playwright MCP (v0.0.82)**: Headless browser automation engine.
- **Graphify (v0.9.64)**: Codebase AST knowledge graph generator.
- **Google ADK (v2.13.0)**: Agent Development Kit installed in `.venv-adk` with 7 official skills and ADK Docs MCP.
- **MCP Discovery**: 32 MCP servers with 270 tools discovered and healthy.

### [COMPLETED] DeepSeek Harness (`dsh`) Integration & Cordis Plugin Bridge
- **`brain/deepseek_harness_bridge.py`**:
  - Exposes DAKU native tools (`application`, `browser`, `filesystem`, `system`) and MCP servers as Cordis plugins.
  - Multi-turn session state with monotonic append-only event logging (`session/created`, `turn/start`, `tool/executing`, etc.).
  - 3-tier security gate dispatch enforcing `SAFE`, `CONFIRMATION_REQUIRED`, and `BLOCKED`.
  - `<think>...</think>` reasoning trace extraction for HUD telemetry with automatic voice stripping for clean speech synthesis.
- **Server HUD Telemetry Sync**: `/api/hud/agents` synced with active DeepSeek Harness pass count, session ID, and plugin mappings.
- **Verification Script**: `scripts/verify_harness_live.py` passed all 7 validation gates.

### [COMPLETED] Milestone 4: Structured 10-Tier Memory Persistence Engine
- **`brain/memory_store.py`**:
  - Zero-dependency unified persistence on Python's built-in `sqlite3` + `FTS5`.
  - Low-RAM speed & safety pragmas: `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-4000;` (capped at ~4 MB RAM).
  - Complete 10-Tier schema: `WORKING_BUFFER`, `SHORT_TERM_SESSION`, `EPISODIC_EVENTS`, `SEMANTIC_FACTS` (BM25 ranking), `PROCEDURAL_LESSONS`, `USER_PROFILE`, `SECURITY_AUDIT_LOG`, `AGENT_SWARM_STATE`, `MCP_TOOL_CACHE`, `ARCHIVAL_SUMMARY`.
  - Certified by 7/7 unit tests in `tests/test_memory_store.py`.

---

## 3. Pending Tasks (The Exact Pending List)

There are **10 pending items** categorized across three operational groups:

### Group A: Live Credentials & Configuration (3 Pending Tasks)
1. **[PENDING] Set `MODEL_API_KEY` in `.env`**: Required to unlock live cloud LLM reasoning with DeepSeek (`deepseek-chat`) or OpenAI. Currently falling back gracefully to local deterministic intent matching.
2. **[PENDING] Set `SARVAM_API_KEY` in `.env`**: Required to activate Sarvam AI's Saaras:v4 (speech-to-text) and Bulbul:v3 (text-to-speech) for Hindi and Indian regional languages. Currently operating on Google STT and Windows SAPI fallback.
3. **[PENDING] Set `DAKU_AUTH_TOKEN` in `.env`**: Required to enforce constant-time Bearer authentication before exposing the DAKU daemon to remote clients or public internet traffic. Currently running in open local development mode.

### Group B: Planned Architectural Milestones (2 Pending Milestones)
4. **[PENDING] Phase 10: Skill Architecture & Reusable Registry**: Standalone, versioned automation skill modules; standard skill manifest (`SKILL.md`); plug-and-play skill registry.
5. **[PENDING] Phase 11: Money Engine & Opportunity Scanner**: Autonomous web opportunity finder; bounty/freelance scanner; ROI calculation engine and lead discovery.

### Group C: Production Cloud Hosting Deployment (5 Pending Tasks)
6. **[PENDING] Provision Oracle Cloud Compute Instance**: Setup Always Free ARM Ampere / x64 Ubuntu VM.
7. **[PENDING] Firewall Hardening (UFW)**: Allow inbound traffic only on ports 22, 80, 443; block port 8443 from WAN.
8. **[PENDING] SSL/TLS Reverse Proxy**: Configure Nginx reverse proxy with automated Let's Encrypt certificates.
9. **[PENDING] Systemd Daemon Service**: Install and enable `daku.service` for 24/7 background operation.
10. **[PENDING] Public DNS Record**: Bind domain / subdomain to the Oracle Cloud instance public IP.
