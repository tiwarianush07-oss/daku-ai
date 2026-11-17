# DAKU — TECHNICAL STACK SPECIFICATION
================================================================================

## 1. HARDWARE TARGET & CONSTRAINTS

| Parameter | Local Client Machine | Remote Server (Optional) |
|---|---|---|
| **Operating System** | Windows 10 / Windows 11 (64-bit) | Ubuntu 22.04 LTS (Oracle Cloud Always Free) |
| **Processor** | AMD Athlon Silver 3050U (2 cores, 2 threads, ~2.3 GHz) | 1-4 OCPU Ampere A1 (ARM64) or AMD x86 |
| **System Memory** | 4.00 GB DDR4 (3.44 GB usable, ~350 MB free idle) | 1 GB to 24 GB RAM |
| **Storage** | 256 GB SSD (50 GB free) | 50–200 GB Block Volume |
| **Working Set Goal** | **< 25 MB RAM total** for client agent | **< 30 MB RAM total** for server daemon |

---

## 2. SOFTWARE ARCHITECTURE & DEPENDENCY FOOTPRINT

DAKU is intentionally architected to rely almost exclusively on the **Python Standard Library**.

```text
+-------------------------------------------------------------------------+
|                               DAKU AGENT                                |
|                                                                         |
|  [Voice Pipeline]       [Brain & Reasoning]         [Security & Tools]  |
|  - Windows SAPI (COM)   - MultiPassReasoner         - PermissionManager |
|  - Push-to-Talk STT     - ReflectionEngine          - ToolRegistry      |
|  - TextFallbackSTT      - LearningEngine            - Allowlisted Tools |
|                         - TaskPlanner State Machine - Dynamic MCP Tools |
|                         - Cloud Model Backends                          |
+-------------------------------------------------------------------------+
|                   PYTHON 3.13 STANDARD LIBRARY                          |
|  - urllib.request   - json          - re         - ctypes / wintypes    |
|  - http.server      - dataclasses   - pathlib    - subprocess           |
+-------------------------------------------------------------------------+
|                             WINDOWS OS                                  |
|  - tasklist         - os.startfile  - SAPI5 TTS  - cmd / powershell     |
+-------------------------------------------------------------------------+
```

### Dependency Audit:
- **Zero Local LLM Dependencies**: No `torch`, `transformers`, `ollama`, `llama-cpp-python`, or `vllm`.
- **Zero Heavy Web Frameworks**: No `django`, `flask`, or `celery` for server daemon (uses native `http.server`).
- **Zero Database Engines**: Fast, lightweight bounded JSON storage for lessons and task states.

---

## 3. MODEL BACKENDS & INFERENCE PIPELINE

DAKU delegates all heavy neural inference to remote cloud APIs:

1. **DirectModelRouter**:
   - Protocol: OpenAI-compatible `/chat/completions` API.
   - Target Providers: DeepSeek (deepseek-chat), OpenAI, Groq, Qwen.
   - Feature: Function calling schemas generated dynamically from `ToolRegistry`.

2. **DeepSeekHarnessBackend**:
   - Protocol: Modular agent orchestration client.
   - Target: Official DeepSeek Harness architecture.
   - Feature: Remote session management and structured tool extraction.

3. **UncensoredR1Backend**:
   - Protocol: Remote DeepSeek R1 Distill execution (`/v1/inference` or `/v1/chat/completions`).
   - Feature: Automatic regex removal of `<think>...</think>` tags to keep voice output concise.

---

## 4. MODEL CONTEXT PROTOCOL (MCP) INTEGRATION

- Protocol: JSON-RPC Model Context Protocol (MCP).
- Discovery: Zero-overhead scanning across user config paths (`~/.gemini/settings.json`, `mcp_servers.json`, plugins).
- Integration: External tools adapt to DAKU's `BaseTool` via `DynamicMCPTool`.
- Security: All MCP tools inherit DAKU's 3-tier permission model (`SAFE`, `CONFIRMATION_REQUIRED`, `BLOCKED`).
- Resiliency: Gracefully functions with 0 MCP servers configured.

---

## 5. REASONING & COMPUTATION ENGINE

- **Adaptive Multi-Pass Engine**: Scalable computation loops (1–8 passes) governed by task complexity.
- **Verification-First Architecture**: Every tool execution demands real-world verification before task completion.
- **Reflection Engine**: Automated diagnosis of failure causes with safe alternative proposals.
- **Safe Self-Learning**: Bounded lesson store (`MAX_LESSONS = 500`) recording failure workarounds and success patterns.
- **Safety Constitution**: Strict prohibition on self-modifying code, privilege escalation, or security bypass.
