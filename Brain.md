# DAKU BRAIN — MASTER CAPABILITY MAP & FEATURE REGISTRY
================================================================================

**Project**: DAKU (Desktop & Autonomous Knowledge Utility)  
**Current Phase**: Adaptive Multi-Pass Reasoning + Reusable Computation Engine (Phase 6)  
**Target Hardware**: Windows 11 / Windows 10 (AMD Athlon Silver 3050U, 4 GB RAM) & Remote Linux VPS (Oracle Cloud Always Free)  
**Status**: ACTIVE PRODUCTION BASELINE  
**Verification Baseline**: 151 Automated Tests Passing (`OK`)  

---

## 1. OPERATING CONSTITUTION & CORE RULES

1. **Additive Evolution**: Never rewrite DAKU from scratch; extend modularly while preserving backwards compatibility.
2. **Zero Local Heavy LLM Guard**: Zero local PyTorch, Transformers, Ollama, or local weight loading. Total process memory strictly bounded (< 25 MB).
3. **Verification-First Gatekeeping**: DAKU never treats a tool execution or model completion as proof of success. State must be verified in the real environment.
4. **Adaptive Computation Principle**: "MORE COMPUTATION WHEN NEEDED" instead of "ALWAYS USE A BIGGER MODEL". Multi-pass computation scales dynamically from 1 to 8 passes.
5. **Immutable Security Constitution**: Self-learning, multi-pass reasoning, and subagents are strictly forbidden from modifying security policies, bypassing permission confirmation, or granting access to prohibited operations.

---

## 2. COMPLETE BRAIN CAPABILITY MAP (29 SECTIONS)

Each capability below is audited and marked with its verified operational status:
- `[BUILT]`: Fully implemented, verified against live system checks, and passing automated test suites.
- `[PARTIAL]`: Core functional logic implemented and tested; advanced ecosystem extensions in progress.
- `[PLANNED]`: Architecturally designed with specifications established; awaiting next roadmap milestone.
- `[NOT BUILT]`: Out-of-scope for the current phase.

---

### Section 1: Core Brain — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/router.py`, `brain/backend.py`, `main.py`
- **Description**: Central orchestration hub (`Brain.think()`) coordinating model routing, multi-pass reasoners, task planning, and tool registries. Manages full input-to-speech lifecycle.
- **Tests**: Verified in `test_phase1.py`, `test_phase2.py`, `test_multipass_reasoning.py`.

### Section 2: Intent Understanding — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `brain/router.py`
- **Description**: Identifies user intent across English, Hindi, and Hinglish. Analyzes single-action queries, multi-step compound commands, and conditional requests ("if something fails, do X").
- **Tests**: Verified across all test suites (`test_01`, `test_02`, `test_03`).

### Section 3: Task Planning — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/planner.py`, `brain/multipass.py`
- **Description**: Decomposes user goals into discrete, allowlisted steps mapped to registered tools. Prevents arbitrary shell generation.
- **Tests**: Verified in `test_phase3.py` (Tests 13, 14, 15).

### Section 4: Multi-Step Planning — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/planner.py`
- **Description**: Structured `TaskPlan` state machine with `TaskStep` definitions, bounded by `MAX_TASK_STEPS = 10` and `MAX_RETRIES_PER_STEP = 2`.
- **Tests**: Verified in `test_phase3.py` (Tests 15, 16, 17) and `test_phase4.py`.

### Section 5: Adaptive Multi-Pass Reasoning — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`
- **Description**: `MultiPassReasoner` dynamically calculates task complexity (`EASY`, `MEDIUM`, `HARD`) and allocates pass budgets (EASY: 1 pass, MEDIUM: 3 passes, HARD: 5 passes, Recovery: 6 passes, Hard ceiling: 8 passes). Implements reusable `ReasoningContext` and `PassState`.
- **Tests**: Verified in `test_multipass_reasoning.py` (Tests 1, 2, 3, 4, 8, 20).

### Section 6: Reflection — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/reflection.py`
- **Description**: `ReflectionEngine` dissects failed tool executions, contrasts expected vs real-world state, identifies root causes (e.g. missing executable, network timeout, disconnected MCP server), and proposes safe alternative strategies without directly executing dangerous operations.
- **Tests**: Verified in `test_multipass_reasoning.py` (Tests 5, 6).

### Section 7: Verification — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/base.py`, `brain/multipass.py`, `tools/planner.py`
- **Description**: Strict verification-first contract (`ToolResult.verified`). Requires process detection, page DOM inspection, or file confirmation before marking steps complete. Verification overrides confidence.
- **Tests**: Verified in `test_multipass_reasoning.py` (Tests 4, 5, 6) and `test_phase2.py` (Test 12).

### Section 8: Retry / Recovery — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `tools/planner.py`, `brain/reflection.py`
- **Description**: Adaptive failure mitigation. If Chrome fails, automatically reflects and pivots to Edge; if an MCP tool disconnects, automatically falls back to native handlers.
- **Tests**: Verified in `test_multipass_reasoning.py` (Tests 6, 7) and `test_phase3.py` (Test 16).

### Section 9: Self-Learning — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/learning.py`
- **Description**: `LearningEngine` records compact structured lessons for both failures and verified success patterns. Enables safe strategy reuse without model retraining or code rewriting. Bounded to `MAX_LESSONS = 500`.
- **Tests**: Verified in `test_multipass_reasoning.py` (Tests 15, 16, 17, 19).

### Section 10: Memory — `[PARTIAL]`
- **Status**: `[PARTIAL]`
- **Source Location**: `brain/multipass.py` (`ReasoningContext`), `brain/learning.py` (`LessonStore`)
- **Description**: In-flight task memory, bounded observation buffer (`MAX_RECENT_OBSERVATIONS = 20`), and structured failure/success memory are built and active. Long-term multi-user profile persistence and vector episodic memory remain planned for future phases.
- **Tests**: Bounded memory verified in `test_multipass_reasoning.py` (Test 19).

### Section 11: Conversation Context — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/router.py`, `brain/backend.py`
- **Description**: Rolling sliding-window interaction history (limited to 6 turns / 12 messages) for low RAM footprint (< 1 MB) and minimal API token usage.
- **Tests**: Verified in `test_phase1.py` and `test_phase4.py`.

### Section 12: Model Routing — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/backend.py`, `brain/router.py`
- **Description**: Dynamic `BackendFactory` selecting between `DirectModelRouter` (OpenAI/DeepSeek), `DeepSeekHarnessBackend` (agent orchestration), and `UncensoredR1Backend` (reasoning model with `<think>` tag stripping).
- **Tests**: Verified in `test_phase4.py` and `test_phase5_certification.py`.

### Section 13: Tool Routing — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/registry.py` (`ToolRouter`)
- **Description**: Strict 4-tier decision priority: (1) Approved native DAKU tool, (2) Approved existing MCP tool, (3) Safe fallback, (4) Refusal / Block.
- **Tests**: Verified in `test_phase3.py` (Test 12).

### Section 14: Native Tools — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/application.py`, `tools/browser.py`, `tools/file_ops.py`, `tools/system.py`
- **Description**: Allowlisted, safe tools executing Windows process inspection, native browser navigation, safe file search/reading, and system telemetry (RAM, CPU, disk, time).
- **Tests**: Verified in `test_phase2.py` and `test_multipass_reasoning.py` (Test 10).

### Section 15: MCP Tools — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/mcp_client.py`
- **Description**: Zero-overhead discovery and wrapping of Model Context Protocol tools (`DynamicMCPTool`). Discovers 23+ servers on the current machine and gracefully handles 0 MCP servers.
- **Tests**: Verified in `test_phase3.py` (Tests 1, 2, 3, 4) and `test_multipass_reasoning.py` (Tests 9, 11).

### Section 16: Browser Control — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/browser.py`
- **Description**: URL sanitization (blocks `javascript:`, `file:`, `data:`), browser launching (Chrome / Edge), HTTP title extraction, and visible text extraction with token safeguards.
- **Tests**: Verified in `test_phase3.py` (Tests 5, 6, 7, 8, 9, 10, 11).

### Section 17: Application Control — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/application.py`
- **Description**: Safe executable launching (Notepad, Calc, Paint, Explorer, Edge, Chrome, VS Code) using Windows `os.startfile` and `tasklist` process verification. Never executes arbitrary command strings.
- **Tests**: Verified in `test_phase2.py` (Tests 5, 6) and `test_multipass_reasoning.py` (Test 6).

### Section 18: File Operations — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/file_ops.py`
- **Description**: Safe directory listing, glob file searching, metadata retrieval, and safe file creation. File deletion and raw PowerShell rmdir are permanently blocked.
- **Tests**: Verified in `test_phase2.py` (Tests 3, 4, 12, 13).

### Section 19: System Information — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/system.py`
- **Description**: Real hardware querying without heavy external dependencies: Total/Free RAM, CPU processor and logical cores, Disk space, Current time, and Windows version.
- **Tests**: Verified in `test_phase2.py` (Test 7) and `test_multipass_reasoning.py` (Test 10).

### Section 20: Voice Input (STT) — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `voice/stt.py`
- **Description**: Microphone push-to-talk speech recognition with double-redundant TextFallbackSTT when audio hardware is unavailable or in headless environments.
- **Tests**: Verified in `test_phase1.py` and `doctor.py`.

### Section 21: Voice Output (TTS) — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `voice/tts.py`
- **Description**: Windows Native SAPI speech synthesis (`pywin32` / COM) with zero additional RAM overhead (< 1 MB). Normalizes text and strips reasoning traces for natural 1-2 sentence speech.
- **Tests**: Verified in `test_phase1.py` and `test_multipass_reasoning.py` (Test 21).

### Section 22: Offline Mode — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/router.py`, `client.py`
- **Description**: Double-redundant offline fallback parsing intents locally when API keys are missing or cloud network is disconnected. Never requires local LLM downloads.
- **Tests**: Verified in `test_phase1_5.py` and `test_multipass_reasoning.py` (Test 14).

### Section 23: Security — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/permissions.py`, `doctor.py`
- **Description**: Permanent blocked list: `arbitrary_shell`, `powershell_raw`, `cmd_raw`, `delete_file`, `format_disk`, `drop_table`, `kill_system`, `dump_credentials`, `read_env_secrets`.
- **Tests**: Verified in `test_phase2.py` (Test 10) and `test_multipass_reasoning.py` (Test 13).

### Section 24: Permissions — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `tools/permissions.py`, `voice/confirmation.py`
- **Description**: 3-tier security classification (`SAFE`, `CONFIRMATION_REQUIRED`, `BLOCKED`). Hands-free voice confirmation and console authorization prompts.
- **Tests**: Verified in `test_voice_confirmation.py` and `test_multipass_reasoning.py` (Test 12).

### Section 25: Secrets Protection — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `brain/learning.py`, `tools/mcp_client.py`
- **Description**: Automatic regex redaction of API keys, bearer tokens, passwords, cookies, and credentials from structured logs, lesson stores, and console output.
- **Tests**: Verified in `test_multipass_reasoning.py` (Test 18) and `test_phase3.py` (Test 21).

### Section 26: Observability — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `doctor.py`
- **Description**: Structured lifecycle event logging (`PASS_START`, `PASS_COMPLETE`, `TOOL_EXECUTION`, `TOOL_FAILURE`, `VERIFICATION_SUCCESS`, `VERIFICATION_FAILURE`, `REFLECTION`, `RETRY`, `LEARNING_EVENT`, `TASK_COMPLETE`, `TASK_STOPPED`). Comprehensive system diagnostic suite in `doctor.py`.
- **Tests**: Verified across doctor checks and multi-pass event logs.

### Section 27: Error Handling — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `brain/backend.py`, `brain/router.py`
- **Description**: Graceful degradation on HTTP errors (401, 429, 500), network timeouts, missing executables, or unparseable responses.
- **Tests**: Verified in `test_phase4.py` and `test_multipass_reasoning.py`.

### Section 28: Performance Optimization — `[BUILT]`
- **Status**: `[BUILT]`
- **Source Location**: `brain/multipass.py`, `config/settings.py`
- **Description**: Single-pass fast path for EASY tasks (< 10ms latency). Bounded memory retention (`MAX_PASSES = 8`, `MAX_LESSONS = 500`, `MAX_RECENT_OBSERVATIONS = 20`). Zero large model memory footprint.
- **Tests**: Verified via benchmark (EASY: 8.1ms, MEDIUM: 86.4ms, RECOVERY: 95.8ms).

### Section 29: Future Capabilities — `[PLANNED]`
- **Status**: `[PLANNED]`
- **Description**:
  - `UI-01`: JARVIS Low-RAM Desktop HUD interface (`[PLANNED]`).
  - `MON-01` to `MON-03`: Money Opportunity Engine & Analytics (`[PLANNED]`).
  - `SCL-01`: Multi-agent collaborative swarm (`[PLANNED]`).
  - `SKL-01`: Versioned skill packaging format (`[PLANNED]`).

---

## 3. MASTER STATUS SUMMARY

| Category | Total Capabilities | Built | Partial | Planned | Not Built |
|---|:---:|:---:|:---:|:---:|:---:|
| **Core Architecture (1–12)** | 12 | 11 | 1 | 0 | 0 |
| **Tools & Subsystems (13–19)** | 7 | 7 | 0 | 0 | 0 |
| **Voice, Security & Ops (20–28)** | 9 | 9 | 0 | 0 | 0 |
| **Future Extensions (29)** | 1 | 0 | 0 | 1 | 0 |
| **TOTAL** | **29** | **27** | **1** | **1** | **0** |
