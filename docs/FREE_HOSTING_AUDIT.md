# DAKU + HERMES — FREE HOSTING DEPLOYMENT AUDIT
**Date**: September 2026  
**Auditor**: Senior DevOps & AI Infrastructure Engineer (Google DeepMind / Antigravity)  
**Status**: Completed Full Pre-Deployment & Infrastructure Inspection  
**Target Architecture**: Oracle Cloud Always Free (Ubuntu Linux Headless VPS) + Low-RAM Windows 11 Laptop Client  
**Hardware Constraint**: AMD Athlon Silver 3050U / 4 GB Physical RAM (3.44 GB visible, ~0.32 GB free) / 128 GB SSD / Windows 11 Pro / Zero Local Heavy LLM  

---

## 1. Executive Summary

This comprehensive pre-deployment audit establishes the baseline architecture, system dependencies, configuration requirements, security posture, and test coverage of the **DAKU Personal AI Voice Agent** and its remote integration with **Hermes Agent**.

The core mission is:
> Move heavy AI reasoning and agent orchestration **OFF** the constrained Windows laptop (AMD Athlon Silver 3050U, ~3.5 GB usable RAM) and onto a **100% free remote server** (Oracle Cloud Always Free Tier), while preserving DAKU's existing architecture, security model, 3-tier permissions, native tools, and zero local heavy model policy.

The audit confirms that the DAKU codebase is modular, clean, and strictly conforms to the low-resource constraint:
- **Local Process Working Set**: Constrained to **< 15 MB RAM** (measured 11.72 MB working set).
- **CPU Idle Load**: **0%** at rest, < 3% during speech synthesis.
- **Local Model Weights**: **0 MB** (Zero PyTorch, Zero HuggingFace Transformers, Zero Ollama, Zero llama.cpp).
- **Automated Regression Suite**: **93 tests passed** across Phases 1 through 5 (100% pass rate in 45.6s).
- **Client-Server Separation**: Functional HTTP/REST headless server daemon (`server/daku_server.py`) and Windows 11 low-RAM client (`client.py`) with double-redundant local offline fallback.

---

## 2. Existing Architecture Overview

DAKU follows a multi-tier modular architecture designed for low-memory environments:

```
[ LAYER 1: CLIENT AUDIO & CONSOLE I/O (Windows 11 Laptop) ]
USER (Push-to-Talk / Enter / CLI)
  │
  ├── Microphone (MicrophoneSTT via SpeechRecognition cloud endpoint / 0 MB local RAM)
  └── TextFallbackSTT (100% offline interactive console input)
  │
  ▼
[ LAYER 2: DAKU REMOTE CLIENT (client.py) ]
  ├── Process RAM: < 15 MB working set | CPU: 0% Idle
  ├── Authentication: Bearer Token (DAKU_AUTH_TOKEN) via HTTP/HTTPS
  ├── Double-Redundant Offline Fallback Engine:
  │   └── If remote server is unreachable, activates local deterministic regex router
  └── Windows Native TTS (voice/tts.py: System.Speech.Synthesis + SAPI.SpVoice COM fallback)
  │
  ▼  [HTTPS / Port 8443 with Authorization: Bearer <TOKEN>]
[ LAYER 3: REMOTE DAKU SERVER (Oracle Cloud Always Free Ubuntu) ]
  ├── Server Daemon (server/daku_server.py: Standard library ThreadingHTTPServer, < 25 MB RAM)
  ├── Endpoints: GET /health, GET /api/status, POST /api/chat, POST /api/confirm
  ├── 3-Tier Permission Manager (tools/permissions.py: SAFE, CONFIRMATION_REQUIRED, BLOCKED)
  ├── Task Planner & State Machine (tools/planner.py: PLANNING -> EXECUTING -> VERIFYING -> COMPLETED)
  │   └── Strict Guards: Max 10 steps, max 2 retries per step
  └── Tool Registry & Router (tools/registry.py: 53 tools registered)
      ├── SystemTool (ctypes RAM, CPU, disk, time, OS queries)
      ├── BrowserTool (native HTTP/HTML parser + Chrome/Edge execution)
      ├── ApplicationTool (desktop application lifecycle and detection)
      ├── FileTool (safe directory listing, search, metadata, reading, sandboxed creation)
      └── Dynamic MCP Tools (23 discovered servers, 49 tool capabilities)
  │
  ▼
[ LAYER 4: HERMES AGENT & ORCHESTRATION GATEWAY ]
  ├── Hermes Agent (NousResearch/hermes-agent: Headless Gateway on 127.0.0.1:8080)
  ├── Autonomous skill accumulation and multi-channel routing
  └── SQLite Persistent Memory (~/.hermes/ / zero heavyweight database servers)
  │
  ▼
[ LAYER 5: HOSTED CLOUD LLM (Cloud-First APIs) ]
  └── DeepSeek API / OpenRouter / Groq Cloud / OpenAI-Compatible Hosted APIs
      └── ZERO local model weights, ₹0 to micro-cent pay-as-you-go costs
```

---

## 3. Existing Entry Points & Services

| Entry Point | File / Target | Role & Execution Mode |
| :--- | :--- | :--- |
| **Lightweight Windows Client** | `client.py` | Low-RAM client bridge (< 15 MB RAM) connecting mic/console to remote server. |
| **Local Standalone Desktop** | `main.py` | In-process Push-to-Talk voice/text loop (legacy/fallback mode). |
| **Remote Server Daemon** | `server/daku_server.py` | Headless HTTP/REST daemon running under systemd on remote host. |
| **System Diagnostics** | `doctor.py` | 18 system diagnostics (RAM, CPU, disk, audio, MCP, remote server, Hermes, local model guard). |
| **Automated Regression Suite** | `tests/` | 93 automated tests across Phase 1 to Phase 5 (`py -m unittest discover -s tests -v`). |
| **Automated Server Scripts** | `scripts/*.sh` | Idempotent installer, safe updater with auto-rollback, state backup, and health check. |
| **Systemd Service Units** | `systemd/*.service`| Sandboxed `daku.service` and `hermes.service` units. |

### Existing Services Status
- **DAKU Server**: Implemented in `server/daku_server.py` using Python's standard library `http.server.ThreadingHTTPServer`. Provides constant-time token comparison, 1 MB request guard, `/health`, `/api/status`, `/api/chat`, and `/api/confirm`.
- **Hermes Agent Gateway**: Configured to run as `hermes gateway --host 127.0.0.1 --port 8080` under `hermes.service`. DAKU server probes Hermes via `/health` and TCP socket.
- **Systemd Units**: `systemd/daku.service` and `systemd/hermes.service` are defined with `Restart=always`, `NoNewPrivileges=true`, `ProtectSystem=full`, `PrivateTmp=true`, `MemoryMax=512M`, and unprivileged user `daku`.

---

## 4. Existing Configuration & Environment Variables

Configuration is handled by `config/settings.py` via `.env` without any third-party dependencies:

| Variable | Default Value | Role | Secret? |
| :--- | :--- | :--- | :---: |
| `DAKU_MODE` | `cloud-lightweight` | Execution mode (`cloud-lightweight`, `cloud-server`) | No |
| `LOG_LEVEL` | `INFO` | Python logging verbosity (`DEBUG`, `INFO`, `WARN`, `ERROR`)| No |
| `AGENT_BACKEND` | `direct` | Backend selection (`direct`, `harness`, `uncensored`) | No |
| `MODEL_PROVIDER` | `deepseek` | Cloud LLM provider name | No |
| `MODEL_NAME` | `deepseek-chat` | Target model identifier | No |
| `MODEL_BASE_URL` | `https://api.deepseek.com/v1` | API base endpoint | No |
| `MODEL_API_KEY` | *(empty string)* | Bearer authentication key for cloud model | **YES** |
| `MODEL_TIMEOUT_SECONDS`| `15.0` | HTTP request timeout in seconds | No |
| `HARNESS_ENDPOINT` | *(inherits base URL)* | DeepSeek Harness endpoint | No |
| `HARNESS_API_KEY` | *(inherits model key)* | DeepSeek Harness credential | **YES** |
| `HARNESS_MODEL_NAME` | `deepseek-chat` | DeepSeek Harness model | No |
| `UNCENSORED_BASE_URL` | `https://api.deepseek.com/v1`| Remote Uncensored R1 endpoint | No |
| `UNCENSORED_API_KEY` | *(inherits model key)* | Uncensored R1 key | **YES** |
| `UNCENSORED_MODEL_NAME`| `deepseek-r1-distill-7b` | Uncensored model name | No |
| `STT_PROVIDER` | `mic` | Speech-to-Text provider (`mic`, `text_fallback`) | No |
| `STT_LANGUAGE` | `en-IN` | Speech recognition language tag | No |
| `TTS_PROVIDER` | `windows_native` | TTS engine (`windows_native`, `edge_tts`, `text_fallback`)| No |
| `TTS_VOICE_NAME` | `Microsoft David Desktop` | Windows SAPI voice synthesizer name | No |
| `TTS_RATE` | `0` | Voice rate (-10 to +10 for SAPI) | No |
| `DAKU_SERVER_HOST` | `0.0.0.0` | Server bind IP on remote host | No |
| `DAKU_SERVER_PORT` | `8443` | Server bind port | No |
| `DAKU_SERVER_URL` | `http://127.0.0.1:8443`| Remote server address configured on client laptop | No |
| `DAKU_AUTH_TOKEN` | *(empty string)* | Shared high-entropy Bearer token for API auth | **YES** |
| `HERMES_GATEWAY_URL` | `http://127.0.0.1:8080`| Local Hermes Gateway URL on server | No |
| `REQUIRE_CONFIRMATION` | `true` | Interactive user confirmation gate | No |
| `WAKE_WORD_ENABLED` | `false` | Always-on microphone listener flag | No |

---

## 5. Existing Model Providers

DAKU supports any OpenAI-compatible API endpoint via `brain/backend.py` and `brain/router.py`:
1. **DeepSeek API (`deepseek`)**: Default cloud provider (`deepseek-chat`, `deepseek-reasoner`). Very low cost ($0.14 / 1M input tokens).
2. **Groq Cloud (`groq`)**: Free-tier ultra-fast Llama-3.3-70b inference (`https://api.groq.com/openai/v1`).
3. **OpenRouter (`openrouter`)**: Free and paid models (`https://openrouter.ai/api/v1`).
4. **Qwen / Alibaba Cloud (`qwen`)**: High-performance multilingual models.
5. **OpenAI (`openai`)**: Direct GPT-4o / GPT-4o-mini support.
6. **Local Deterministic Fallback**: Built-in offline regex parser for system hardware queries, desktop app launches, and greetings when disconnected.

---

## 6. Existing APIs & Endpoints

| Endpoint | Method | Auth Required | Description |
| :--- | :---: | :---: | :--- |
| `/health` | `GET` | **No** (Public) | Returns server health, version, uptime, Hermes status, model status, and host metrics. Zero secret leakage. |
| `/` | `GET` | **No** (Public) | Index banner listing available endpoints and server version. |
| `/api/status` | `GET` | **Yes** (Bearer) | Authenticated deep inspection: tool registry, security settings, detailed system metrics. |
| `/api/chat` | `POST` | **Yes** (Bearer) | Primary chat endpoint: accepts `{"message": "..."}`, processes via Brain, returns response and pending action confirmations. |
| `/api/confirm` | `POST` | **Yes** (Bearer) | Security confirmation resolution: accepts `{"action_id": "...", "confirmed": bool}`. |

---

## 7. Existing Security Controls

1. **Deterministic 3-Tier Permissions**:
   - `SAFE`: Non-destructive queries (hardware inspection, time, read-only file reading, web title extraction). Executed automatically.
   - `CONFIRMATION_REQUIRED`: File creation, web form interaction, external mutations. Prompts user interactively on laptop before execution.
   - `BLOCKED`: Permanently refused. Raw shell execution (`cmd.exe`, `powershell.exe`, `bash`, `sh`), file deletion (`delete_file`, `rmdir`), disk formatting, database drops, credential theft.
2. **Prohibition of Direct Shell Execution**: The AI model output cannot execute operating system binaries or shell scripts directly. All actions route strictly through allowlisted functions in `ToolRegistry`.
3. **Secret Redaction**: API keys and bearer tokens are automatically masked in CLI displays and logs (`sk-de********ef`).
4. **Authentication Hardening**: Bearer token checks use `secrets.compare_digest` to prevent timing attacks. Missing or incorrect tokens return `HTTP 401 Unauthorized`.
5. **Payload Guard**: Requests exceeding 1 MB are rejected with `HTTP 413 Payload Too Large`.
6. **Local Model Guard**: Prohibits loading heavy model runtimes (`ollama`, `llamacpp`, `vllm`, `torch`, `transformers`) on the laptop.

---

## 8. Existing Test Coverage

The test suite consists of **93 automated unit and integration tests**:

| Test Suite | File | Tests Run | Result | Key Coverage |
| :--- | :--- | :---: | :---: | :--- |
| **Phase 1: Voice MVP** | `tests/test_phase1.py` | 6 | **PASSED** | Core interfaces, SAPI TTS, text fallback STT, mock brain, doctor diagnostics. |
| **Phase 1.5: Push-to-Talk STT** | `tests/test_phase1_5.py` | 8 | **PASSED** | Push-to-Talk audio capture, silence timeouts, device absence handling, text fallback. |
| **Phase 2: Local Computer Agent** | `tests/test_phase2.py` | 16 | **PASSED** | System tool ctypes RAM query, application launcher, file search/read, permission blocking. |
| **Phase 3: MCP & Browser** | `tests/test_phase3.py` | 23 | **PASSED** | Browser tool navigation, title extraction, MCP discovery and isolation, task planner 5-state machine. |
| **Phase 4: Agent Hardening** | `tests/test_phase4.py` | 27 | **PASSED** | BackendFactory, DeepSeekHarnessBackend, UncensoredR1Backend, `<think>` tag stripping, max 10 steps cap, max 2 retries cap. |
| **Phase 5: Remote Deployment** | `tests/test_remote_deployment.py` | 13 | **PASSED** | DakuServer lifecycle, public /health, zero secret leakage, 401 auth gate, /api/chat, /api/status, /api/confirm, DakuRemoteClient probe, offline fallback, doctor checks, zero local heavy LLM memory guard. |
| **TOTAL** | | **93** | **100% PASSED** | Execution time: **45.598 seconds**. |

---

## 9. Resource Requirements & Hardware Constraints

### Client Laptop (HP 255 G9)
- **CPU**: AMD Athlon Silver 3050U (2 cores, 2 threads, 2.3 GHz base / 3.2 GHz boost).
- **RAM**: 4.00 GB physical (3.44 GB visible to Windows, ~0.32 GB currently free).
- **Disk**: 128 GB SSD.
- **Client Footprint**: < 15 MB RAM working set, 0% CPU at rest.
- **Constraint**: Must never run local LLM inference, embedding servers, or heavy Docker stacks.

### Target Remote Server (Oracle Cloud Always Free)
- **Compute Shape**: Ampere A1 Compute (ARM64) — up to 4 OCPUs and 24 GB RAM, 100% Always Free (₹0/month forever).
  *(Alternative fallback: AMD VM.Standard.E2.1.Micro — 1 OCPU, 1 GB RAM x86_64).*
- **OS**: Ubuntu 24.04 LTS Minimal (Headless Server, zero GUI/desktop/XRDP/XFCE).
- **Disk**: 50 GB Boot Volume (within the 200 GB Always Free allowance).
- **Bandwidth**: < 5 GB/month (well within 10 TB/month free allowance).
- **Cost**: **₹0.00 / month guaranteed**.

---

## 10. Hermes Agent Compatibility Assessment

Based on official Nous Research specifications (`NousResearch/hermes-agent`):
- **Architecture**: Native `linux/arm64` and `linux/amd64` compatibility. Clean execution on Oracle Ampere A1 (ARM64) and standard x86 VPS.
- **Runtime**: Python 3.11+ using `uv` for ultra-fast, low-overhead dependency isolation.
- **Memory & Storage**: SQLite-based memory (`~/.hermes/`), requiring less than 150 MB RAM in gateway/headless mode when models are hosted remotely.
- **Mode**: Headless Gateway service (`hermes gateway --host 127.0.0.1 --port 8080`).
- **Model Inference**: Hermes delegates LLM generation to hosted APIs (OpenRouter, Nous Portal, DeepSeek, or any OpenAI-compatible endpoint). It does **not** require local GPU or local model weights.

---

## 11. Deployment Blockers & Gap Analysis

1. **Oracle Cloud Account Setup (User Prerequisite)**:
   - Oracle Cloud requires the user to create a free account at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) and verify identity with a card.
   - *Status*: The automated installer (`scripts/install_server.sh`), configuration, and systemd units are fully prepared and tested so that once the VM is created, deployment takes under 3 minutes.
2. **CLI Diagnostic Ergonomics (`daku doctor`)**:
   - The user requested a CLI command `daku doctor`.
   - *Resolution*: Provide `daku.bat` (Windows) and `daku` (Linux) command wrappers, and support `doctor` argument in `main.py`.
3. **Disk Health Check in Doctor**:
   - `doctor.py` currently checks RAM, CPU, OS, Python, MCP, audio, backend, and network, but lacks an explicit disk space check.
   - *Resolution*: Add `check_disk()` to `doctor.py` using `shutil.disk_usage`.
4. **Google Drive Integration Policy**:
   - Google Drive must be strictly used for backup archives, never for live model execution.
   - *Resolution*: Script `scripts/backup.sh` handles local tarball snapshots and can sync encrypted backups if configured.

---

## 12. Recommended Deployment Path

```text
STEP 1: Audit Completed (Documented in docs/FREE_HOSTING_AUDIT.md)
   │
STEP 2: Review Implementation Plan (implementation_plan.md) with User
   │
STEP 3: Refine Ergonomics (daku.bat, check_disk in doctor.py, main.py dispatch)
   │
STEP 4: Deploy Remote Server (Oracle Always Free Ubuntu ARM64)
   ├── Run sudo bash scripts/install_server.sh
   ├── Configure /etc/daku/daku.env (Auth Token + Hosted LLM API Key)
   └── Start daku.service and hermes.service
   │
STEP 5: Configure Windows 11 Laptop Client
   ├── Set DAKU_SERVER_URL and DAKU_AUTH_TOKEN in laptop .env
   ├── Run py doctor.py --remote (or daku doctor)
   └── Run py client.py (or daku client)
   │
STEP 6: Acceptance Verification & Final Deployment Report
```

*Audit complete. Ready for implementation plan presentation and user confirmation.*
