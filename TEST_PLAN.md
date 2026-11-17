# DAKU — TEST PLAN & VERIFICATION STRATEGY
================================================================================

## 1. OBJECTIVES

The test plan verifies that:
1. DAKU successfully upgrades to an **Adaptive Multi-Pass Reasoning and Reusable Computation Engine**.
2. Reasoning passes adapt dynamically to task difficulty (1 pass for easy, 2–3 for medium, 3–6 for complex/recovery).
3. The absolute safety limit (`MAX_PASSES = 8`) and repeated action detection prevent infinite loops.
4. Tool verification gates completion, and failures trigger reflection and safe strategy correction.
5. The self-learning engine records lessons from failures and successes while enforcing the Security Constitution.
6. Memory limits are strictly enforced on constrained hardware (< 25 MB RAM).
7. Secrets, API keys, and credentials never appear in logs or memory.
8. Zero regressions occur across existing Phase 1–5 test suites (130 existing tests + 21 new tests = 151 total).

---

## 2. TEST MATRIX (21 CORE REQUIREMENTS)

| Req ID | Requirement Description | Test File & Method | Target Outcome |
|---|---|---|:---:|
| **REQ-01** | EASY task uses one pass | `test_01_easy_task_uses_one_pass` | Pass budget = 1, passes_used = 1 |
| **REQ-02** | MEDIUM task uses multiple passes | `test_02_medium_task_uses_multiple_passes` | Passes_used in 2..3 |
| **REQ-03** | HARD task uses bounded passes | `test_03_hard_task_uses_bounded_passes` | Passes_used in 3..6 (<= 8) |
| **REQ-04** | Early stop on verified completion | `test_04_successful_task_stops_immediately` | Stops immediately on verification |
| **REQ-05** | Failure triggers reflection | `test_05_verification_failure_triggers_reflection` | Returns `ReflectionResult` with diagnosis |
| **REQ-06** | Reflection generates new strategy | `test_06_reflection_creates_different_strategy` | Chrome fails → Pivots to Edge |
| **REQ-07** | Repeated action detection | `test_07_repeated_identical_action_detected` | Emits `REPEATED_ACTION_DETECTED` |
| **REQ-08** | Max pass ceiling enforcement | `test_08_maximum_pass_limit_enforced` | Execution capped at `MAX_PASSES = 8` |
| **REQ-09** | Zero MCP servers resilience | `test_09_zero_mcp_servers_works_gracefully` | Native tools ready with 0 MCP servers |
| **REQ-10** | Native tools functionality | `test_10_existing_native_tools_continue_working` | App, Browser, File, System tools OK |
| **REQ-11** | MCP tools functionality | `test_11_existing_mcp_tools_continue_working` | DynamicMCPTool executes and verifies |
| **REQ-12** | Permission system enforcement | `test_12_permission_system_remains_enforced` | SAFE vs CONFIRM vs BLOCKED respected |
| **REQ-13** | Blocked operations rejection | `test_13_blocked_actions_remain_blocked` | Delete/shell operations permanently blocked |
| **REQ-14** | Offline fallback mode | `test_14_offline_mode_remains_functional` | Local intent parsing works without API key |
| **REQ-15** | Learning records failure | `test_15_learning_records_failure` | Stores failure cause & working alternative |
| **REQ-16** | Learning records success | `test_16_learning_records_success` | Stores verified success strategy |
| **REQ-17** | Learned strategy reuse | `test_17_learned_strategy_can_be_reused` | Recommends proven alternative |
| **REQ-18** | Secrets protection & redaction | `test_18_secrets_never_appear_in_logs` | API keys/tokens replaced with REDACTED |
| **REQ-19** | Memory limits enforcement | `test_19_memory_limits_are_enforced` | `MAX_LESSONS` (500) & `MAX_OBS` (20) capped |
| **REQ-20** | Infinite loop prevention | `test_20_no_infinite_loop_possible` | Terminating loop guarantee |
| **REQ-21** | Voice output cleanliness | `test_21_voice_friendly_output_cleanliness` | Strips `<think>` tags and pass numbers |

---

## 3. EXECUTION COMMANDS

```powershell
# 1. Run new Multi-Pass & Self-Learning test suite
py -m unittest tests/test_multipass_reasoning.py

# 2. Run full repository regression test discovery
py -m unittest discover tests

# 3. Run DAKU system diagnostic doctor
py main.py doctor
```
