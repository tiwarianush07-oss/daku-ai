# DAKU + HERMES SYSTEM ARCHITECTURE

## 1. High-Level Architecture Diagram

```text
               +-------------------------------------------------------+
               |               WINDOWS 11 CLIENT LAPTOP                |
               |         (AMD Athlon 3050U / 3.44 GB RAM)              |
               |                                                       |
               |  USER (Voice / Push-to-Talk / Console Text)           |
               |     │                                                 |
               |     ▼                                                 |
               |  [Input Engine: voice/stt.py]                         |
               |  - MicrophoneSTT (cloud STT / 0 local RAM)            |
               |  - TextFallbackSTT (100% offline text input)          |
               |     │                                                 |
               |     ▼                                                 |
               |  [DAKU Client: client.py]                             |
               |  - Memory Footprint: < 15 MB RAM, 0% CPU Idle         |
               |  - Bearer Token Authentication Manager                |
               |  - Local Offline Fallback Router                      |
               |  - SAPI Speech Synthesizer: voice/tts.py              |
               +---------------------------┬---------------------------+
                                           │
                                           │ HTTPS / TLS (Port 443)
                                           │ Authorization: Bearer <TOKEN>
                                           ▼
               +-------------------------------------------------------+
               |              REMOTE ORACLE CLOUD SERVER               |
               |            (Always Free Ubuntu Linux ARM64)           |
               |                                                       |
               |  [Perimeter Security: UFW Open Ports 22, 80, 443]     |
               |  - Port 22: OpenSSH Key-Based Authentication          |
               |  - Port 80: HTTP Redirect / Certbot ACME              |
               |  - Port 443: Nginx TLS Reverse Proxy                  |
               |     │                                                 |
               |     │ Internal Loopback (127.0.0.1:8443)              |
               |     ▼                                                 |
               |  [DAKU Server: server/daku_server.py]                 |
               |  - Endpoints: /health, /api/chat, /api/confirm        |
               |  - Constant-time Token Verification                   |
               |  - Non-root Execution: user 'daku'                    |
               |  - Systemd Hardening (PrivateTmp, ProtectSystem)      |
               |  - Resource Limits: Max 512 MB RAM, 80% CPU Quota     |
               |     │                                                 |
               |     ├───► [Permission Manager: tools/permissions.py]  |
               |     │     - 3-Tier Policy (SAFE / CONFIRM / BLOCKED)  |
               |     │     - Direct Shell / Dangerous Ops Refusal      |
               |     │                                                 |
               |     ├───► [Multi-Pass Reasoner: brain/multipass.py]   |
               |     │     - Adaptive Computation (1 to 8 passes)      |
               |     │     - Complexity Budgeting (EASY/MED/HARD)      |
               |     │     - Repeated Action Detection                 |
               |     │                                                 |
               |     ├───► [Reflection Engine: brain/reflection.py]    |
               |     │     - Root-Cause Failure Diagnosis              |
               |     │     - Alternative Strategy Proposals            |
               |     │                                                 |
               |     ├───► [Learning Engine: brain/learning.py]        |
               |     │     - Bounded Failure & Success Lessons (<=500) |
               |     │     - Safe Pattern Reuse (No self-mod code)     |
               |     │                                                 |
               |     ├───► [Task Planner: tools/planner.py]            |
               |     │     - State Machine: PLANNING -> EXECUTING      |
               |     │     - Step Limit: 10 steps, 2 retries max       |
               |     │                                                 |
               |     ├───► [Tool Registry: tools/registry.py]          |
               |     │     - Native System, Browser, Application Tools |
               |     │     - MCP Client & Discovery Layer              |
               |     │                                                 |
               |     └───► [Model Router: brain/router.py]             |
               |           - Provider Abstraction                      |
               |           - Response Voice Normalization              |
               |           - Session State & History                   |
               |                 │                                     |
               |                 ▼                                     |
               |  [Hermes Agent Gateway: ~/.local/bin/hermes]          |
               |  - Systemd: hermes.service (Port 8080)                |
               |  - Autonomous Skill Generation                        |
               |  - SQLite Context Memory: ~/.hermes/                  |
               +---------------------------┬---------------------------+
                                           │
                                           │ Outbound HTTPS API Calls
                                           │ (DeepSeek / OpenRouter / Groq)
                                           ▼
               +-------------------------------------------------------+
               |                HOSTED CLOUD MODEL API                 |
               |             Zero Local Weights / Free API             |
               +-------------------------------------------------------+
```

---

## 2. Component Responsibility Matrix

| Responsibility | Windows Laptop Client | Remote Cloud Server | Hosted Cloud LLM |
| :--- | :---: | :---: | :---: |
| **Microphone Capture & STT** | **Primary** | - | - |
| **Local Text Fallback Input** | **Primary** | - | - |
| **Windows Desktop App Launching** | **Primary (Local tool)** | - | - |
| **Windows SAPI Audio Synthesis (TTS)** | **Primary** | - | - |
| **AI Reasoning & Chat Completions** | - | - | **Primary** |
| **Agent State & Multi-Step Planning** | - | **Primary** | - |
| **Hermes Gateway & Skill Generation** | - | **Primary** | - |
| **3-Tier Permission Verification** | Secondary (Prompts) | **Primary (Enforces)** | - |
| **Persistent SQLite Memory** | - | **Primary** | - |
| **Systemd Automatic Recovery** | - | **Primary** | - |

---

## 3. Request Lifecycle

```text
1. USER SPEAKS OR TYPES
   └── Microphone captures PCM audio; SpeechRecognition transcribes text (or user types in console).

2. CLIENT TRANSMISSION
   └── client.py constructs JSON payload {"message": "..."} with Bearer auth token.
   └── Sends HTTP POST to https://<server-domain-or-ip>/api/chat (port 443 TLS terminated by Nginx).

3. SECURITY & AUTHENTICATION (Remote Server)
   └── DAKU server verifies Bearer token using secrets.compare_digest.
   └── Rejects unauthorized calls with HTTP 401.

4. BRAIN & INTENT ORCHESTRATION
   └── Brain.think() consults ModelRouter / Hermes Gateway.
   └── If tool execution is needed, routes to TaskPlanner and ToolRegistry.

5. PERMISSION EVALUATION
   └── PermissionManager evaluates action against 3-tier rules:
       - SAFE: Executes immediately and verifies result.
       - CONFIRMATION_REQUIRED: Suspends execution; returns requires_confirmation=True.
       - BLOCKED: Permanently refuses and logs safety event.

6. RESPONSE SYNTHESIS & SPEECH OUTPUT
   └── Server normalizes response text (stripping markdown, symbols, and <think> tags).
   └── Client receives clean text and speaks aloud via Windows SAPI.
```

---

## 4. Double-Redundant Offline Fallback

If network connectivity is disrupted or the remote server is stopped:
```text
Client Connection Probe (4s timeout)
          │
          ├──► Server Available: Routes to Remote Cloud Server (Full Intelligence)
          │
          └──► Server Unreachable:
                    │
                    ▼
               Activates Local Offline Fallback Engine
                    │
                    ├── Deterministic Local Regex Parser (DirectModelRouter)
                    ├── Queries Real Local RAM, CPU, Disk via Windows APIs
                    ├── Launches Whitelisted Windows Desktop Applications
                    └── Explains offline state without crashing or downloading weights
```

---

## 5. Pluggable Voice Architecture & Sarvam AI Integration

For full details, see [docs/SARVAM_VOICE_AGENT.md](file:///c:/Users/anush07/Desktop/win10/DAKU/docs/SARVAM_VOICE_AGENT.md).

DAKU integrates Sarvam AI as an interchangeable, production-grade Indian-language voice provider:

1. **Speech-To-Text (STT)**:
   - Primary: Sarvam Saaras (`saaras:v4`) supporting 22 Indic languages + Global/Indian English.
   - Automatic fallback to Google Web Speech API (`GoogleSTTProvider`), then to local text console.

2. **Text-To-Speech (TTS)**:
   - Primary: Sarvam Bulbul v3 (`bulbul:v3`) supporting 30+ voices (`shubh`, `aditya`, etc.).
   - `TTSNormalizer` cleans model responses (Indic script preservation, number/URL expansion, `<think>` tag and JSON stripping).
   - Automatic fallback to Windows Native SAPI (`WindowsSapiTTSProvider`, 0 MB RAM), then to console text.

3. **Credential & Boundary Security**:
   - `SARVAM_API_KEY` remains strictly server-side / environment-based.
   - Client-server architecture delegates STT/TTS to remote server gateway endpoints (`/api/voice/transcribe`, `/api/voice/synthesize`), keeping the Windows client credential-free.
   - 3-tier permissions (`SAFE`, `CONFIRMATION_REQUIRED`, `BLOCKED`) remain strictly enforced before executing any tool.
