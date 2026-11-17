# DAKU — ADAPTIVE MULTI-PASS REASONING ENGINE
================================================================================

## 1. CORE PRINCIPLE

```text
"MORE COMPUTATION WHEN NEEDED"
instead of
"ALWAYS USE A BIGGER MODEL"
```

DAKU solves complex, uncertain, and failing desktop automation tasks not by downloading heavier local LLMs or ballooning memory usage, but by using **controlled, adaptive passes over the same lightweight reasoning and execution pipeline**.

On resource-constrained hardware (Windows 10/11, AMD Athlon Silver 3050U, 4 GB RAM), this approach achieves maximum intelligence, reliability, and recovery at a tiny memory working set (< 20 MB).

---

## 2. REASONING LIFECYCLE & PHASES

```text
       USER INPUT
           ↓
     [1. UNDERSTAND]  ← Assess task complexity (EASY / MEDIUM / HARD)
           ↓
        [2. PLAN]     ← Deterministic allowlisted decomposition (TaskPlanner)
           ↓
       [3. EXECUTE]   ← ToolRegistry.execute_tool() [Permissions Enforced]
           ↓
       [4. OBSERVE]   ← Capture ToolResult, OS telemetry, process tables
           ↓
        [5. VERIFY]   ← Real-world state verification (result.verified)
           │
      Is Verified?
      ├─ YES ────────► [8. FINALIZE] ──► Voice-Friendly Response (TTS)
      │
      └─ NO
           ↓
       [6. REFLECT]   ← ReflectionEngine: Root-cause diagnosis & alternative
           ↓
        [7. RETRY]    ← Corrected strategy (e.g. Edge instead of Chrome)
           │
           └───► Loop to EXECUTE (if passes remain within budget)
```

### Discrete Phases:
1. **UNDERSTAND**: Parses intent, detects constraints, queries known learned strategies, and sets the pass budget.
2. **PLAN**: Sequences discrete allowlisted actions mapped to native or MCP tools.
3. **EXECUTE**: Dispatches validated tool calls through `ToolRegistry` and `PermissionManager`.
4. **OBSERVE**: Collects stdout, stderr, process IDs, and system state into `ReasoningContext`.
5. **VERIFY**: Confirms real-world state changes (e.g. `tasklist` check, HTTP status, file existence).
6. **REFLECT**: Analyzes failures, contrasts expected vs actual state, and suggests alternative actions.
7. **RETRY**: Adjusts parameters or selects a backup tool (e.g. Edge when Chrome fails).
8. **FINALIZE**: Synthesizes a clean 1-2 sentence voice-friendly summary, stripping all internal `<think>` reasoning traces.

---

## 3. ADAPTIVE PASS CONTROLLER & BUDGETING

The pass controller prevents unnecessary compute while providing ample budget for failure recovery:

| Task Complexity | Example User Request | Budgeted Passes | Typical Execution Trace |
|---|---|:---:|---|
| **EASY** | `"Check RAM"`, `"What time is it?"` | **1 pass** | UNDERSTAND + EXECUTE + VERIFY in 1 fast pass (< 10ms) |
| **MEDIUM** | `"Open Notepad"`, `"Open Chrome and visit URL"` | **2–3 passes** | UNDERSTAND (P1) → EXECUTE (P2) → VERIFY (P3) |
| **HARD** | `"Open Chrome, find page title, and read text"` | **3–5 passes** | UNDERSTAND → PLAN → EXECUTE → OBSERVE → VERIFY |
| **RECOVERY** | `"Launch browser, but if something fails figure out another way"` | **4–6 passes** | UNDERSTAND → EXECUTE (Chrome fails) → REFLECT → RETRY (Edge) → VERIFY |

### Absolute Safety Limits:
- **`MAX_PASSES = 8`**: Hard safety ceiling. No execution can exceed 8 passes under any condition.
- **Repeated Action Detection**: If the identical tool call and arguments are executed repeatedly without state progress, the engine emits `REPEATED_ACTION_DETECTED` and either pivots strategy or stops safely.

---

## 4. REUSABLE COMPUTATION & `ReasoningContext`

DAKU does NOT duplicate model weights or accumulate unbounded history. It maintains a compact, lightweight data structure:

```python
class ReasoningContext:
    task_id: str
    user_request: str
    goal: str
    constraints: List[str]
    current_plan: Optional[TaskPlan]
    completed_steps: List[Dict[str, Any]]
    failed_steps: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]        # Bounded <= 20 items
    tool_results: List[Dict[str, Any]]        # Bounded <= 20 items
    verification_results: List[Dict[str, Any]]
    attempt_count: int
    confidence: float
    next_action: Optional[Dict[str, Any]]
    stop_reason: Optional[str]
```

### Bounded Memory Guarantees:
- `MAX_ACTIVE_PASSES = 8`
- `MAX_RECENT_OBSERVATIONS = 20`
- `MAX_CONTEXT_CHARS = 4000`
- Secrets automatically masked with `***REDACTED***`.

---

## 5. VERIFICATION-FIRST GATEKEEPING

```text
Tool Execution Success != Task Completion
Task Completion = Real-World State Verified
```

Every tool execution returns a structured `ToolResult`:
- `success`: Boolean execution status.
- `verified`: Real-world confirmation (e.g. process is running, file exists).
- `data`: Extracted state metadata.
- `error`: Diagnostic error message if failed.

### Confidence vs. Verification:
- Confidence score ranges:
  - `0.00 – 0.39`: LOW
  - `0.40 – 0.69`: MEDIUM
  - `0.70 – 0.89`: HIGH
  - `0.90 – 1.00`: VERIFIED / HIGH CONFIDENCE
- **Core Rule**: Verification strictly overrides confidence. If `confidence = 0.95` but `verified = False`, the step is classified as **FAILED** and routed to `ReflectionEngine`.

---

## 6. STRUCTURED OBSERVABILITY LOGGING

The multi-pass engine outputs structured events for auditable tracing:

```text
TASK_START id=task_1726543900 query='open chrome'
PASS_START number=1 phase=UNDERSTAND complexity=MEDIUM
PASS_COMPLETE number=1 phase=UNDERSTAND budget=3
PASS_START number=2 phase=EXECUTE tool=application_tool
TOOL_EXECUTION tool=application_tool
TOOL_FAILURE tool=application_tool error='Application chrome not found'
VERIFICATION_FAILURE tool=application_tool
PASS_START number=3 phase=REFLECT
REFLECTION strategy=Chrome executable resolution failed. Proposing Microsoft Edge as alternative browser.
LEARNING_EVENT recorded failure lesson: fail_1726543901 [Task: app_launch]
RETRY next_tool=application_tool
PASS_START number=4 phase=EXECUTE tool=application_tool
TOOL_EXECUTION tool=application_tool
VERIFICATION_SUCCESS tool=application_tool
PASS_COMPLETE number=4 phase=VERIFY status=VERIFIED
TASK_COMPLETE passes=4 verified=True
```

All credentials, tokens, cookies, and passwords are automatically masked before logging.

---

## 7. VOICE-FRIENDLY RESPONSE SYNTHESIS

While internal passes capture detailed step traces, user-facing speech is strictly normalized:
- **Internal Reflection**: `"Chrome executable resolution failed. Proposing Edge as alternative browser. Attempt 2 verified."`
- **Spoken Voice Output**: `"Chrome didn't open, so I tried Edge instead. It's running now."`
- Reasoning tags (`<think>...</think>`), markdown formatting, and pass numbers are stripped to preserve natural Windows SAPI speech.
