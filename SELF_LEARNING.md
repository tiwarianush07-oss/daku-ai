# DAKU — SAFE SELF-LEARNING ENGINE
================================================================================

## 1. THE SELF-LEARNING SECURITY CONSTITUTION

DAKU includes safe, bounded learning from experience without autonomous model retraining or self-modification.

> **IMMUTABLE SECURITY RULES:**
> 1. **Zero Source Modification**: DAKU shall NEVER automatically rewrite or edit its own Python source files.
> 2. **Zero Security Policy Changes**: Self-learning shall NEVER modify `PermissionManager` rules, remove items from `BLOCKED_PATTERNS`, or grant unauthorized privileges.
> 3. **Zero Credential Retention**: Passwords, tokens, API keys, and private cookies must be masked with `***REDACTED***` before storing in lessons.
> 4. **Zero Unbounded Memory Growth**: Lesson storage is strictly capped at `MAX_LESSONS = 500`.

### Definition of Learning in DAKU:
```text
OBSERVE  ──► Real tool outcomes and verification results
   ↓
RECORD   ──► Compact, structured lessons (failures & successes)
   ↓
GENERALIZE ─► Identify reliable alternative tools and patterns
   ↓
REUSE SAFELY ─► Guide initial planning passes on similar future tasks
```

---

## 2. LESSON SCHEMA & DATA STRUCTURE

Each lesson is stored as a lightweight, serializable JSON record:

```json
{
  "lesson_id": "fail_1726543901_0",
  "task_type": "app_launch",
  "failed_action": "application_tool:chrome",
  "failure_reason": "Application 'chrome' not found on system path",
  "successful_action": "application_tool:edge",
  "strategy_name": null,
  "context": {
    "os": "Windows 10",
    "timestamp": 1726543901.42
  },
  "timestamp": 1726543901.42,
  "confidence": 0.85,
  "reusable": true,
  "usage_count": 2
}
```

### Success Pattern Lesson Example:
```json
{
  "lesson_id": "succ_1726543905_1",
  "task_type": "browser_navigation",
  "strategy_name": "browser_navigation_verified",
  "successful_action": "browser_tool:navigate",
  "context": {
    "site": "example.com"
  },
  "timestamp": 1726543905.18,
  "confidence": 0.95,
  "reusable": true,
  "usage_count": 5
}
```

---

## 3. HOW LESSONS ARE ACQUIRED

### 1. Learning From Failures:
When a tool execution or verification fails:
1. `ReflectionEngine` determines why the action failed (e.g. missing executable, network disconnect).
2. Proposes a safe alternative (e.g. Edge instead of Chrome).
3. If the alternative succeeds and verifies, `LearningEngine.record_failure()` stores the failure reason paired with the working alternative.
4. Next time the user asks to launch a browser, the planner checks learned lessons and selects Edge directly, eliminating unnecessary failed passes.

### 2. Learning From Successes:
When a multi-step task completes and passes real-world verification:
1. `LearningEngine.record_success()` indexes the sequence as a proven recipe.
2. Recurring tasks can look up `get_recommended_strategy()` to immediately reuse the verified strategy.

---

## 4. BOUNDED MEMORY & PRUNING

To respect low-RAM environments (4 GB system RAM):
- Maximum lessons: **500 records** (`MAX_LESSONS = 500`).
- Storage footprint: **< 150 KB** on disk (`data/lessons.json`).
- Memory footprint: **< 1 MB** in RAM.
- Eviction policy: When lesson count reaches 500, lessons with the lowest usage count and oldest timestamp are pruned automatically.

---

## 5. REUSE INTEGRATION IN BRAIN PIPELINE

```text
User Request
     ↓
MultiPassReasoner (Pass 1: UNDERSTAND)
     ↓
LearningEngine.find_failure_lesson() / get_recommended_strategy()
     ├─ Match found: Inject proven tool and arguments into initial action
     └─ No match: Proceed with standard deterministic or model routing
```

This reduces cloud model calls, lowers API latency, and guarantees that DAKU never repeats past mistakes.
