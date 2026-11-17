# DAKU SYSTEM ARCHITECTURE
================================================================================

This document provides the high-level architecture specification for DAKU.
For additional deployment and hosting guides, see [docs/ARCHITECTURE.md](file:///c:/Users/anush07/Desktop/win10/DAKU/docs/ARCHITECTURE.md).

---

## 1. END-TO-END DATA FLOW

```text
       USER (Voice / Text)
               │
               ▼
       [Input Layer]
       - MicrophoneSTT (Push-to-Talk)
       - TextFallbackSTT (Headless/Offline)
               │
               ▼
        [DAKU Brain]
       - DirectModelRouter / DeepSeekHarness / UncensoredR1
               │
               ▼
   [Adaptive Multi-Pass Reasoner] (brain/multipass.py)
   - Dynamic Complexity Budgeting (1 to 8 passes)
   - Bounded ReasoningContext (< 2 MB RAM)
   - Loop & Repeated Action Protection
               │
       ┌───────┴───────┐
       ▼               ▼
  [TaskPlanner]    [LearningEngine] (brain/learning.py)
  (State Machine)  (Lesson Store <= 500 records)
       │
       ▼
 [Permission Manager] (tools/permissions.py)
 - 3-Tier Policy (SAFE, CONFIRMATION_REQUIRED, BLOCKED)
 - Voice Confirmation Loop & CLI prompt
       │
       ▼
   [ToolRegistry] (tools/registry.py)
   - Native Windows Tools (App, Browser, File, System)
   - Discovered Model Context Protocol (MCP) Tools
       │
       ▼
  [Execution & Verification] (tools/base.py)
  - Result verified in OS real-world state
       │
       ├── Verified? YES ──► [Clean Voice Output] (voice/tts.py)
       │
       └── Verified? NO  ──► [Reflection Engine] (brain/reflection.py)
                                  │
                                  ▼
                             Pivots strategy (e.g. Edge instead of Chrome)
                             Retries if passes remain within budget
```

---

## 2. KEY SUBSYSTEMS

1. **Multi-Pass Reasoner (`brain/multipass.py`)**:
   Enforces "More Computation When Needed". Allocates passes dynamically:
   - EASY: 1 pass (< 10ms fast path)
   - MEDIUM: 2–3 passes
   - HARD: 3–5 passes
   - Failure Recovery: up to 6 passes
   - Absolute Safety Ceiling: `MAX_PASSES = 8`.

2. **Reflection Engine (`brain/reflection.py`)**:
   Diagnoses root cause of failures, compares expected vs actual system state, and suggests alternative actions without executing dangerous commands.

3. **Safe Self-Learning (`brain/learning.py`)**:
   Maintains a bounded JSON lesson store (`MAX_LESSONS = 500`) with automatic secret redaction. Never modifies Python source code or alters security permissions.

4. **Verification-First Architecture**:
   No tool call is considered successful unless `result.verified` confirms the real-world outcome. Verification overrides confidence scores.

5. **Tool Registry & MCP Integration**:
   Executes allowlisted native tools and discovered MCP tools. Enforces strict 3-tier security classification. Gracefully functions with 0 MCP servers.

---

## 3. PLUGGABLE VOICE PROVIDERS & SARVAM AI

DAKU supports modular, production-grade Voice Agent providers (`voice/providers/` and `voice_agent/`):

1. **Speech-To-Text (STT)**:
   - **Primary**: Sarvam Saaras (`saaras:v4`) via REST API supporting 22 Indic languages and English.
   - **Fallback 1**: Google Web Speech API (`GoogleSTTProvider` / `MicrophoneSTT`).
   - **Fallback 2**: Text console input (`TextFallbackSTT`).

2. **Text-To-Speech (TTS)**:
   - **Primary**: Sarvam Bulbul v3 (`bulbul:v3`) supporting 30+ voices (`shubh`, `aditya`, `ritu`, etc.).
   - **Preprocessing**: `TTSNormalizer` preserves Indic native script, cleans URLs/numbers, and strips internal `<think>` reasoning tags and JSON payloads.
   - **Fallback 1**: Windows Native SAPI (`WindowsSapiTTSProvider`, 0 MB RAM).
   - **Fallback 2**: Console text output.

3. **Security Invariants**:
   - `SARVAM_API_KEY` is strictly server-side / environment-based. Never exposed to the Windows client.
   - All tool executions remain strictly guarded by `PermissionManager` (Safe, Confirmation Required, Blocked). Voice failures never bypass security confirmations.
