"""
DAKU Adaptive Multi-Pass Reasoner & Reusable Computation Engine
Phase 6: Multi-Pass Reasoning, Verification-First Gatekeeping & Adaptive Computation

Provides:
- MultiPassReasoner: Orchestrates adaptive execution passes based on task complexity.
  EASY: 1-2 passes | MEDIUM: 3 passes | HARD: 5 passes | Recovery: 6 passes | Hard limit: 8 passes.
- PassState: Structured lifecycle of each reasoning and execution pass.
- ReasoningResult: Clean, voice-friendly outcome metadata and trace.
- ReasoningContext: Lightweight, low-RAM reusable state (< 2 MB memory footprint).
- Strict verification-first gatekeeping: Tool calls are NEVER proof of success without verified real-world state.
- Repeated action detection to eliminate infinite reasoning loops.
- Redacts all secrets and credentials in structured observability logs.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from brain.learning import LearningEngine, sanitize_data
from brain.reflection import ReflectionEngine, ReflectionResult
from config.settings import settings
from tools.base import PermissionLevel, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.multipass")


class ComplexityLevel(str, Enum):
    """Task complexity classifications determining initial pass budgets."""
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class PassPhase(str, Enum):
    """Discrete reasoning and execution phases."""
    UNDERSTAND = "UNDERSTAND"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    REFLECT = "REFLECT"
    RETRY = "RETRY"
    FINALIZE = "FINALIZE"


@dataclass
class PassState:
    """Represents the in-flight state of a discrete computation pass."""
    pass_number: int
    phase: PassPhase
    objective: str
    input_context: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    tool_result: Optional[ToolResult] = None
    verification_result: Optional[bool] = None
    error: Optional[str] = None
    confidence: float = 0.5
    completed: bool = False


@dataclass
class ReasoningResult:
    """Final output of the MultiPassReasoner."""
    success: bool
    final_answer: str
    passes_used: int
    confidence: float
    verification_status: bool
    learned_event: Optional[Dict[str, Any]] = None
    trace: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_voice_summary(self) -> str:
        """Returns clean, short, voice-friendly response (1-2 sentences)."""
        # Ensure no internal reasoning or pass metadata leaks to voice output
        clean = self.final_answer.strip()
        clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.DOTALL).strip()
        clean = re.sub(r"PASS \d+:?", "", clean)
        clean = re.sub(r"[#*`_~]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean or "I processed your request."


@dataclass
class ReasoningContext:
    """
    Lightweight, reusable task context.
    Strictly bounded to prevent memory growth on low-RAM hardware.
    """
    task_id: str
    user_request: str
    goal: str = ""
    constraints: List[str] = field(default_factory=list)
    current_plan: Optional[Any] = None
    completed_steps: List[Dict[str, Any]] = field(default_factory=list)
    failed_steps: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    verification_results: List[Dict[str, Any]] = field(default_factory=list)
    attempt_count: int = 0
    confidence: float = 0.5
    next_action: Optional[Dict[str, Any]] = None
    stop_reason: Optional[str] = None

    def add_observation(self, obs: Dict[str, Any]) -> None:
        """Adds observation with bounded retention (MAX_RECENT_OBSERVATIONS)."""
        clean_obs = sanitize_data(obs)
        self.observations.append(clean_obs)
        max_obs = getattr(settings, "MAX_RECENT_OBSERVATIONS", 20)
        if len(self.observations) > max_obs:
            self.observations = self.observations[-max_obs:]

    def add_tool_result(self, tool_name: str, args: Dict[str, Any], result: ToolResult) -> None:
        """Records executed tool result."""
        entry = {
            "tool": tool_name,
            "args": sanitize_data(args),
            "success": result.success,
            "verified": result.verified,
            "message": sanitize_data(result.message),
            "error": sanitize_data(result.error),
            "timestamp": time.time(),
        }
        self.tool_results.append(entry)
        if len(self.tool_results) > 20:
            self.tool_results = self.tool_results[-20:]


class MultiPassReasoner:
    """
    Adaptive Multi-Pass Reasoning Engine.
    Executes 'MORE COMPUTATION WHEN NEEDED' instead of loading heavier local models.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        learning_engine: Optional[LearningEngine] = None,
        reflection_engine: Optional[ReflectionEngine] = None,
        max_passes: Optional[int] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.learning_engine = learning_engine or LearningEngine()
        self.reflection_engine = reflection_engine or ReflectionEngine(learning_engine=self.learning_engine)
        self.max_passes_ceiling = min(
            max_passes or getattr(settings, "MAX_PASSES", 8),
            8,  # Hard absolute safety limit
        )
        self.active_passes: List[PassState] = []
        self._action_history: List[Tuple[str, str]] = []

    def _mask_for_logs(self, text: str) -> str:
        """Masks API keys, tokens, and credentials in structured logs."""
        clean = str(text)
        clean = re.sub(r"(?i)(api[_-]?key|token|password|secret|auth|bearer)\s*[:=]\s*['\"]?([^\s'\"]+)", r"\1=********", clean)
        clean = re.sub(r"sk-[a-zA-Z0-9]{20,}", "sk-********", clean)
        clean = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", "Bearer ********", clean)
        return clean

    def _log_event(self, event_type: str, details: str = "") -> None:
        """Structured observability logger."""
        masked_details = self._mask_for_logs(details)
        logger.info(f"{event_type} {masked_details}".strip())

    def determine_task_complexity(self, user_query: str, plan_step_count: int = 0) -> ComplexityLevel:
        """
        Calculates task complexity:
        EASY   : Single hardware metric, simple greeting, direct file search.
        MEDIUM : Single app launch, standard 2-3 step browser navigation.
        HARD   : Multi-step workflows (> 3 steps), recovery tasks, conditional instructions.
        """
        msg = user_query.strip().lower()

        # Hard complexity: conditional logic, recovery, or high step count
        if any(w in msg for w in ("if ", "but if", "figure out another way", "retry", "fallback")) or plan_step_count > 3:
            return ComplexityLevel.HARD

        # Medium complexity: browser + navigation + title/content, multi-step actions
        if (
            any(w in msg for w in ("chrome", "edge", "browser", "website", "http", ".com"))
            and any(w in msg for w in (" and ", " then ", "title", "read", "inspect", "find"))
        ) or plan_step_count in (2, 3):
            return ComplexityLevel.MEDIUM

        # Single app launch or simple file/system queries
        if any(w in msg for w in ("open", "launch", "start", "kholo")) and not any(w in msg for w in (" and ", " then ")):
            return ComplexityLevel.MEDIUM

        return ComplexityLevel.EASY

    def determine_initial_pass_budget(
        self,
        complexity: ComplexityLevel,
        has_failure_recovery: bool = False,
    ) -> int:
        """Allocates initial pass budget based on task complexity."""
        if has_failure_recovery:
            budget = 6
        elif complexity == ComplexityLevel.EASY:
            budget = 1
        elif complexity == ComplexityLevel.MEDIUM:
            budget = 3
        elif complexity == ComplexityLevel.HARD:
            budget = 5
        else:
            budget = 3

        return min(budget, self.max_passes_ceiling)

    def calculate_confidence(
        self,
        verification_status: bool,
        attempt_count: int,
        tool_success: bool,
        has_fallback: bool = False,
    ) -> float:
        """
        Lightweight confidence score:
        0.00-0.39: LOW
        0.40-0.69: MEDIUM
        0.70-0.89: HIGH
        0.90-1.00: VERIFIED / HIGH CONFIDENCE
        Verification overrides confidence: unverified actions cannot exceed 0.65.
        """
        if not tool_success:
            return 0.15

        if not verification_status:
            # Unverified cannot be high confidence
            return min(0.60, 0.70 - (attempt_count * 0.15))

        # Verified success
        base = 0.95
        if has_fallback:
            base -= 0.05
        base -= max(0, (attempt_count - 1) * 0.05)
        return max(0.75, min(1.0, base))

    def _is_repeated_action(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Detects if the identical tool call with the same arguments has been repeated consecutively.
        Prevents runaway loops on identical failures.
        """
        args_key = json.dumps(args, sort_keys=True)
        # Check last two actions
        if len(self._action_history) >= 2:
            last1 = self._action_history[-1]
            last2 = self._action_history[-2]
            if last1 == (tool_name, args_key) and last2 == (tool_name, args_key):
                return True
        return False

    def reason_and_execute(
        self,
        user_query: str,
        initial_action: Optional[Tuple[str, Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReasoningResult:
        """
        Executes adaptive multi-pass reasoning loop:
        UNDERSTAND -> PLAN -> EXECUTE -> OBSERVE -> VERIFY -> REFLECT -> RETRY -> FINALIZE
        """
        task_id = f"task_{int(time.time() * 1000)}"
        self.active_passes.clear()
        self._action_history.clear()

        ctx = ReasoningContext(
            task_id=task_id,
            user_request=user_query,
            goal=user_query,
        )
        self._log_event("TASK_START", f"id={task_id} query='{user_query}'")

        # PASS 1: UNDERSTAND
        complexity = self.determine_task_complexity(user_query)
        budget = self.determine_initial_pass_budget(complexity)
        pass_num = 1

        p1 = PassState(
            pass_number=pass_num,
            phase=PassPhase.UNDERSTAND,
            objective="Understand user intent and assess complexity",
            input_context={"query": user_query},
            output={"complexity": complexity.value, "pass_budget": budget},
            confidence=0.9,
            completed=True,
        )
        self.active_passes.append(p1)
        self._log_event("PASS_START", f"number={pass_num} phase=UNDERSTAND complexity={complexity.value}")
        self._log_event("PASS_COMPLETE", f"number={pass_num} phase=UNDERSTAND budget={budget}")

        # Check for learned successful strategy reuse
        learned_strat = self.learning_engine.get_recommended_strategy("browser_navigation" if "browser" in user_query.lower() else "app_launch")

        # Determine first action
        current_action = initial_action
        if not current_action:
            # Check offline/direct routing
            current_action = self._resolve_initial_action(user_query)

        if not current_action:
            # No tool execution required (conversational or general query)
            res = ReasoningResult(
                success=True,
                final_answer="I processed your request.",
                passes_used=pass_num,
                confidence=0.9,
                verification_status=True,
                trace=[asdict(p) for p in self.active_passes],
                metadata={"complexity": complexity.value},
            )
            self._log_event("TASK_COMPLETE", f"passes={pass_num}")
            return res

        # Single pass execution for EASY tasks (Pass 1: UNDERSTAND + EXECUTE + VERIFY)
        if budget == 1:
            tool_name, tool_args = current_action
            self._action_history.append((tool_name, json.dumps(tool_args, sort_keys=True)))
            self._log_event("TOOL_EXECUTION", f"tool={tool_name}")
            tool_result = self.tool_registry.execute_tool(tool_name, tool_args)
            p1.tool_result = tool_result
            p1.verification_result = tool_result.verified
            p1.output = tool_result.data
            ctx.add_tool_result(tool_name, tool_args, tool_result)

            if tool_result.success and tool_result.verified:
                self._log_event("VERIFICATION_SUCCESS", f"tool={tool_name}")
                p1.completed = True
                p1.confidence = 0.95
                final_answer = tool_result.to_voice_summary()
                res = ReasoningResult(
                    success=True,
                    final_answer=final_answer,
                    passes_used=1,
                    confidence=0.95,
                    verification_status=True,
                    trace=[asdict(p) for p in self.active_passes],
                    metadata={"task_id": task_id, "complexity": complexity.value, "budget": 1},
                )
                self._log_event("TASK_COMPLETE", "passes=1 verified=True")
                return res
            else:
                # If an easy task fails unexpectedly, expand budget for reflection & recovery
                budget = min(6, self.max_passes_ceiling)

        # Loop execution up to budgeted passes or ceiling
        final_answer = ""
        overall_success = False
        overall_verified = False
        last_tool_result: Optional[ToolResult] = None
        has_reflected_and_retried = False

        while pass_num <= budget and pass_num < self.max_passes_ceiling:
            pass_num += 1
            tool_name, tool_args = current_action
            args_str = json.dumps(tool_args, sort_keys=True)

            # Check Repeated Action Detection
            if self._is_repeated_action(tool_name, tool_args):
                self._log_event("REPEATED_ACTION_DETECTED", f"tool={tool_name}")
                # Trigger reflection or stop
                ref_res = self.reflection_engine.reflect_on_failure(
                    tool_name=tool_name,
                    args=tool_args,
                    tool_result=last_tool_result or ToolResult(success=False, error="Repeated identical action failed."),
                    context={"reasoning_context": ctx.task_id},
                    failed_history=[(h[0], json.loads(h[1])) for h in self._action_history],
                )
                if ref_res.should_retry and ref_res.suggested_tool and ref_res.suggested_args:
                    current_action = (ref_res.suggested_tool, ref_res.suggested_args)
                    self._log_event("RETRY", f"strategy={ref_res.explanation}")
                    continue
                else:
                    self._log_event("TASK_STOPPED", "reason=repeated_action_no_strategy")
                    final_answer = f"I stopped the task because repeated attempts to run {tool_name} were unsuccessful."
                    break

            self._action_history.append((tool_name, args_str))

            # Phase: EXECUTE
            self._log_event("PASS_START", f"number={pass_num} phase=EXECUTE tool={tool_name}")
            self._log_event("TOOL_EXECUTION", f"tool={tool_name}")
            exec_pass = PassState(
                pass_number=pass_num,
                phase=PassPhase.EXECUTE,
                objective=f"Execute tool {tool_name}",
                input_context={"tool": tool_name, "args": tool_args},
            )

            # Execute via ToolRegistry
            tool_result = self.tool_registry.execute_tool(tool_name, tool_args)
            last_tool_result = tool_result
            exec_pass.tool_result = tool_result
            ctx.add_tool_result(tool_name, tool_args, tool_result)

            # Phase: OBSERVE & VERIFY
            obs = {
                "tool": tool_name,
                "success": tool_result.success,
                "verified": tool_result.verified,
                "data": tool_result.data,
                "message": tool_result.message,
            }
            ctx.add_observation(obs)

            if tool_result.success and tool_result.verified:
                # Verification succeeded
                self._log_event("VERIFICATION_SUCCESS", f"tool={tool_name}")
                exec_pass.verification_result = True
                exec_pass.completed = True
                exec_pass.confidence = self.calculate_confidence(True, ctx.attempt_count + 1, True, has_reflected_and_retried)
                self.active_passes.append(exec_pass)
                self._log_event("PASS_COMPLETE", f"number={pass_num} phase=VERIFY status=VERIFIED")

                overall_success = True
                overall_verified = True
                final_answer = tool_result.to_voice_summary()

                # If we used recovery, create pleasant voice explanation
                if has_reflected_and_retried:
                    if tool_name == "application_tool" and tool_args.get("app_name") == "edge":
                        final_answer = "Chrome didn't open, so I tried Edge instead. It's running now."

                # Record success lesson
                task_category = "browser_navigation" if "browser" in tool_name else "app_launch"
                self.learning_engine.record_success(
                    task_type=task_category,
                    strategy_name=f"{tool_name}_verified",
                    successful_action=f"{tool_name}:{tool_args.get('action') or tool_args.get('query')}",
                    context={"user_query": user_query},
                )
                break

            else:
                # Verification failed or tool execution failed
                self._log_event("TOOL_FAILURE", f"tool={tool_name} error='{tool_result.error or tool_result.message}'")
                self._log_event("VERIFICATION_FAILURE", f"tool={tool_name}")
                exec_pass.verification_result = False
                exec_pass.error = tool_result.error or tool_result.message
                exec_pass.confidence = 0.2
                self.active_passes.append(exec_pass)

                ctx.attempt_count += 1
                ctx.failed_steps.append({"tool": tool_name, "args": tool_args, "error": exec_pass.error})

                # Check if we should expand budget for failure recovery (up to 6 passes)
                if budget < 6:
                    budget = min(6, self.max_passes_ceiling)

                # Phase: REFLECT
                pass_num += 1
                self._log_event("PASS_START", f"number={pass_num} phase=REFLECT")
                ref_res = self.reflection_engine.reflect_on_failure(
                    tool_name=tool_name,
                    args=tool_args,
                    tool_result=tool_result,
                    context={"user_query": user_query},
                    failed_history=[(h[0], json.loads(h[1])) for h in self._action_history],
                )

                ref_pass = PassState(
                    pass_number=pass_num,
                    phase=PassPhase.REFLECT,
                    objective=f"Reflect on failure of {tool_name}",
                    input_context={"tool": tool_name, "error": exec_pass.error},
                    output={"reflection": asdict(ref_res)},
                    completed=True,
                )
                self.active_passes.append(ref_pass)
                self._log_event("REFLECTION", f"strategy={ref_res.explanation}")
                self._log_event("PASS_COMPLETE", f"number={pass_num} phase=REFLECT")

                # Record failure lesson in learning engine
                self.learning_engine.record_failure(
                    task_type="app_launch" if "application" in tool_name else "general",
                    failed_action=f"{tool_name}:{tool_args}",
                    failure_reason=ref_res.failure_reason,
                    successful_alternative=ref_res.suggested_tool,
                    context={"user_query": user_query},
                )

                if ref_res.should_retry and ref_res.suggested_tool and ref_res.suggested_args:
                    # Formulate corrected strategy
                    current_action = (ref_res.suggested_tool, ref_res.suggested_args)
                    has_reflected_and_retried = True
                    self._log_event("RETRY", f"next_tool={ref_res.suggested_tool}")
                else:
                    # No safe recovery exists -> stop safely
                    self._log_event("TASK_STOPPED", "reason=no_safe_strategy")
                    final_answer = f"I couldn't complete the task. {ref_res.explanation}"
                    break

        # Check maximum pass ceiling stop condition
        if pass_num >= self.max_passes_ceiling and not overall_verified:
            self._log_event("TASK_STOPPED", "reason=max_passes_reached")
            if not final_answer:
                final_answer = "Task reached maximum reasoning pass limit without verification."

        if not final_answer and last_tool_result:
            final_answer = last_tool_result.to_voice_summary()

        final_conf = self.calculate_confidence(
            verification_status=overall_verified,
            attempt_count=ctx.attempt_count + 1,
            tool_success=overall_success,
            has_fallback=has_reflected_and_retried,
        )

        res = ReasoningResult(
            success=overall_success,
            final_answer=final_answer,
            passes_used=pass_num,
            confidence=final_conf,
            verification_status=overall_verified,
            trace=[asdict(p) for p in self.active_passes],
            metadata={
                "task_id": task_id,
                "complexity": complexity.value,
                "budget": budget,
                "attempts": ctx.attempt_count + 1,
            },
        )
        self._log_event("TASK_COMPLETE", f"passes={pass_num} verified={overall_verified}")
        return res

    def _resolve_initial_action(self, user_query: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Resolves user query to initial tool action."""
        msg = user_query.strip().lower().rstrip(".!?,")

        # Hardware queries
        if any(w in msg for w in ("ram", "memory")):
            return "system_tool", {"query": "ram"}
        if any(w in msg for w in ("cpu", "processor")):
            return "system_tool", {"query": "cpu"}
        if any(w in msg for w in ("disk", "storage")):
            return "system_tool", {"query": "disk"}
        if any(w in msg for w in ("time", "date", "clock")):
            return "system_tool", {"query": "time"}

        # Application launch
        open_match = re.search(r"(?:open|launch|start|kholo)\s+([a-zA-Z0-9\s\.\:\-_/]+)", msg)
        if open_match:
            app = open_match.group(1).replace("app", "").strip()
            if app in ("notepad", "calc", "paint", "explorer", "cmd", "edge", "chrome", "code", "taskmgr"):
                return "application_tool", {"action": "launch", "app_name": app}
            elif "." in app or app in ("google", "youtube", "github"):
                url = app if app.startswith("http") else f"https://www.{app}.com" if "." not in app else app
                return "browser_tool", {"action": "navigate", "url": url}

        # File search
        if "find" in msg or "search" in msg:
            pat = "*.pdf" if "pdf" in msg else "*.txt" if "txt" in msg else "*"
            return "file_tool", {"action": "search_files", "pattern": pat}

        return None
