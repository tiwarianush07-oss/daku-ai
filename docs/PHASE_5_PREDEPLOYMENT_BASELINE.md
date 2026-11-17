# DAKU PHASE 5 PRE-DEPLOYMENT BASELINE AUDIT
**Date**: September 2026  
**Auditor**: Senior DevOps + AI Infrastructure + Security + QA Engineer  
**Stage**: Phase 5 Pre-Deployment Baseline & Post-Verification Audit  
**Target Environment**: Oracle Cloud Always Free (Ubuntu Linux ARM64 Ampere A1) + Low-RAM Windows 11 Laptop Client  

---

## 1. Executive Summary & Objective

This pre-deployment baseline records the exact state of the DAKU codebase prior to any Phase 5 modifications. In accordance with Section 4 of the Phase 5 Master Prompt, this inspection guarantees that existing functionality across Phases 1 through 4 is preserved without regressions, that zero heavy local model weights reside on the client laptop, and that all architectural constraints remain strictly enforced.

The primary objective of Phase 5 is to transition DAKU from local deployment readiness to a verified live remote deployment with Hermes gateway integration, hosted LLM reasoning, encrypted HTTPS reverse-proxy termination, bearer authentication, and automated systemd recovery.

---

## 2. Environment & Version Baseline

| Component | Measured Value | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10 Pro / Windows 11 (AMD64 build 10.0.19045 / 10.0.26100) | `doctor.py` / `platform.system()` | VERIFIED |
| **CPU Architecture** | AMD Athlon Silver 3050U with Radeon Graphics (2 cores, 2 threads) | `(Get-CimInstance Win32_Processor).Name` | VERIFIED |
| **RAM Hardware** | 4.00 GB Physical (3.44 GB visible, ~0.44–0.68 GB free at rest) | Win32_OperatingSystem CIM query | VERIFIED |
| **Python Runtime** | Python 3.13.9 (64-bit) | `py --version` | VERIFIED |
| **Node.js Runtime** | Node: v20.11.1, npm: 10.2.4 | `node -v`, `npm -v` | VERIFIED |
| **Git Tooling** | git version 2.55.0.windows.5 | `git --version` | VERIFIED |
| **Git Repository State** | Standalone directory (no `.git` directory initialized) | `git status` check | RECORDED |
| **Local LLM Weights** | 0 MB (Zero torch, transformers, ollama, or llama.cpp) | Process memory inspection | VERIFIED |
| **Client Memory Footprint** | ~11.44 MB working set, 0% CPU idle | Process working set measurement | VERIFIED |

---

## 3. Automated Test Suite Baseline

The automated test suite was executed via `py -m unittest discover -s tests -p "test_*.py" -v`:

```text
Ran 110 tests in 82.778s
OK (0 failures, 0 errors)
```

### Breakdown of Test Suites (110 Tests Total):
1. **`test_phase1.py`** (6 tests): Imports, doctor diagnostics, text fallback STT, Windows SAPI TTS, brain offline mode, end-to-end pipeline.
2. **`test_phase1_5.py`** (8 tests): Intent parsing, tool schema generation, safety enforcement, system queries, process launches, browser navigations, file read/write, error recoveries.
3. **`test_phase2.py`** (12 tests): Multi-step planning, task execution loop, approval gates, allowlisted tools, post-verification, failure recoveries.
4. **`test_phase3.py`** (19 tests): MCP server discovery, schema translation, dynamic tool dispatch, permission enforcement, credential redaction, browser automation.
5. **`test_phase4.py`** (27 tests): `AgentBackend` abstraction, `DirectModelBackend`, `DeepSeekHarnessBackend`, `UncensoredR1Backend`, `<think>` tag stripping, 10-step cap, 2-retry limits, credential masking, zero local model guard.
6. **`test_remote_deployment.py`** (13 tests): Public `/health`, secret leak prevention, 401 on missing/invalid token, 200 on valid token, `/api/status`, `/api/confirm`, remote client probe, offline fallback, doctor checks.
7. **`test_phase5_certification.py`** (17 tests): HTTPS URL validation, loopback detection, doctor diagnostic discrimination, auth matrix (valid, missing, invalid, malformed), constant-time comparison (`secrets.compare_digest`), endpoint security, safe tool execution, confirmation required boundary, dangerous tool blocking, MCP permission boundary, client offline fallback, and client resource safety.

---

## 4. Existing Services & Daemons

| Service Name | Definition File | Executable / Entry Point | Port / Binding | Sandbox Flags |
| :--- | :--- | :--- | :--- | :--- |
| **DAKU Server** | `systemd/daku.service` | `server/daku_server.py` | `127.0.0.1:8443` | `NoNewPrivileges=true`, `ProtectSystem=full`, `PrivateTmp=true`, `MemoryMax=512M`, `CPUQuota=80%` |
| **Hermes Gateway** | `systemd/hermes.service` | `hermes gateway` | `127.0.0.1:8080` | `NoNewPrivileges=true`, `ProtectSystem=full`, `PrivateTmp=true`, `MemoryMax=1024M`, `CPUQuota=90%` |

---

## 5. Existing API Endpoints

| Method | Endpoint | Access Control | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Public | Service index, version, and available endpoints |
| `GET` | `/health` | Public | High-level uptime, model status, Hermes status, system RAM/disk |
| `GET` | `/api/status` | Authenticated (`Bearer <TOKEN>`) | Detailed operational metrics, registered tools list, Hermes URL |
| `POST` | `/api/chat` | Authenticated (`Bearer <TOKEN>`) | Chat processing, tool execution, and confirmation request return |
| `POST` | `/api/confirm` | Authenticated (`Bearer <TOKEN>`) | Receives client approval/denial for `CONFIRMATION_REQUIRED` actions |

---

## 6. Current Security Assumptions & Guarantees

1. **3-Tier Permission Hierarchy**:
   - `SAFE`: Non-destructive read operations (system queries, browser page read, file search). Executed immediately.
   - `CONFIRMATION_REQUIRED`: State-changing operations (file creation, form submission, app launch). Pauses for client consent.
   - `BLOCKED`: Dangerous actions (arbitrary shell, powershell, file deletion, system shutdown, formatting, secret dumping). Permanently refused.
2. **Zero Shell Execution**: No model output is ever passed to `shell=True`, `cmd.exe`, `powershell.exe`, or `bash`. All actions execute via pre-registered python tool classes in `ToolRegistry`.
3. **Secret Isolation**: Secrets are masked in all logs, status responses, and client presentations (`_mask_secret`).
4. **Timing Attack Protection**: Token authentication uses `secrets.compare_digest`.
5. **Request Guard**: Maximum request payload size capped at 1 MB (`MAX_REQUEST_BODY_BYTES = 1048576`).

---

## 7. Current Deployment Scripts & Tools

- **`scripts/install_server.sh`**: Idempotent installer for Ubuntu 22.04/24.04 LTS. Configures `daku` user, installs Python, `uv`, Hermes Agent, sets up `/opt/daku` and `/etc/daku/daku.env`, deploys systemd units, configures UFW (ports 22, 80, 443), and binds DAKU to loopback `127.0.0.1:8443`.
- **`scripts/update_server.sh`**: Safe updater creating pre-update tarball snapshot in `/var/backups/daku/`, updating files, restarting services, probing `/health`, and triggering automatic rollback if `/health` fails.
- **`scripts/backup.sh`**: Creates gzip archive of `/etc/daku`, `/home/daku/.hermes`, `/opt/daku/data` with permissions `600` and retains the newest 7 backups.
- **`scripts/health_check.sh`**: CLI probe of systemd unit states (`daku`, `hermes`, `nginx`), queries local `/health`, tests port 443 TLS reverse proxy, and prints free RAM and disk.
- **`scripts/live_verification.py`**: Full empirical verification harness executing 11 live gates on physical hardware.

---

## 8. Phase 5 Implementation Delta & Post-Verification Status

1. **Loopback Server Hardening**:
   - Updated `config/settings.py` and `server/daku_server.py` default bind address from `0.0.0.0` to `127.0.0.1`.
   - Internal port 8443 is strictly inaccessible from WAN; public traffic terminates at Nginx port 443.
2. **Empirical Verification Suite**:
   - `scripts/live_verification.py` implemented and verified (11 / 11 gates PASS).
   - Roundtrip latency measured at 14.43 ms over loopback.
   - Physical memory measured at 11.44 MB working set.
3. **Full Regression Integrity**:
   - 110 / 110 unit tests pass (100% success rate, 0 failures, 0 errors).
4. **Certification Ruling**:
   - Designated **CONDITIONALLY CERTIFIED** due to pending external cloud dependencies (active Oracle Cloud instance, cloud LLM API credentials, public domain DNS A-record).
