"""
DAKU TaskPlanner & Task State Machine Module
Provides lightweight deterministic planning, validation, state management, execution verification,
and automatic failure recovery for multi-step tasks.
Ensures zero arbitrary shell generation and enforces that only registered tools can be scheduled.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.base import PermissionLevel, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.planner")


MAX_TASK_STEPS = 10
MAX_RETRIES_PER_STEP = 2


class TaskState(Enum):
    """Lifecycle states for multi-step task execution."""
    PLANNING = "PLANNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERY = "RECOVERY"


@dataclass
class TaskStep:
    """Represents a discrete, structured step in a multi-step task plan."""
    step_id: int
    description: str
    tool_name: str
    action: str
    args: Dict[str, Any]
    expected: Optional[str] = None
    status: str = "PENDING"  # PENDING, EXECUTING, VERIFIED, FAILED, RETRYING, SKIPPED
    retries: int = 0
    max_retries: int = MAX_RETRIES_PER_STEP
    result: Optional[ToolResult] = None
    verified: bool = False


@dataclass
class TaskPlan:
    """Structured plan composed of sequential steps with state tracking."""
    plan_id: str
    raw_query: str
    steps: List[TaskStep] = field(default_factory=list)
    state: TaskState = TaskState.PLANNING
    error: Optional[str] = None
    final_message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        return self.state == TaskState.COMPLETED

    def is_failed(self) -> bool:
        return self.state == TaskState.FAILED


class TaskPlanner:
    """
    Lightweight deterministic TaskPlanner & State Machine Executor.
    Converts user requests into safe, verified tool execution plans.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        reflection_engine: Optional[Any] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        if reflection_engine is not None:
            self.reflection_engine = reflection_engine
        else:
            try:
                from brain.reflection import ReflectionEngine
                self.reflection_engine = ReflectionEngine()
            except Exception:
                self.reflection_engine = None

    def _extract_urls(self, text: str) -> List[str]:
        """Extracts domains or full URLs mentioned in user text."""
        # Matches domain.com, sub.domain.org, https://example.com/path
        domain_pattern = r"(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]*)?"
        matches = re.findall(domain_pattern, text)
        clean_urls = []
        for m in matches:
            # Filter out file extensions like .py or .txt if not a web domain
            if m.endswith((".py", ".txt", ".json", ".exe", ".dll", ".tmp")):
                continue
            if not m.startswith("http://") and not m.startswith("https://"):
                m = f"https://{m}"
            clean_urls.append(m)
        return clean_urls

    def create_plan(self, user_query: str) -> TaskPlan:
        """
        Parses natural language user query and constructs a validated TaskPlan.
        Guarantees that every step uses an allowlisted tool registered in ToolRegistry.
        """
        query = user_query.strip()
        query_lower = query.lower()
        plan_id = f"plan_{int(time.time() * 1000)}"
        plan = TaskPlan(plan_id=plan_id, raw_query=query, state=TaskState.PLANNING)

        steps: List[TaskStep] = []
        step_counter = 1

        # Check for multi-step browser scenarios
        has_browser_kw = any(w in query_lower for w in ("chrome", "browser", "edge", "google", "website", "webpage", "site"))
        urls = self._extract_urls(query)

        # Case 1: Browser + URL + Title query (e.g. "open Chrome, go to bhartiyarishtey.com and tell me the page title")
        if (has_browser_kw or urls) and any(w in query_lower for w in ("title", "page title", "heading", "name of page")):
            target_url = urls[0] if urls else "https://www.google.com"
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description="Launch Chrome browser",
                    tool_name="application_tool",
                    action="launch",
                    args={"action": "launch", "app_name": "chrome"},
                    expected="Chrome",
                )
            )
            step_counter += 1
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description=f"Navigate to {target_url}",
                    tool_name="browser_tool",
                    action="navigate",
                    args={"action": "navigate", "url": target_url},
                    expected=target_url,
                )
            )
            step_counter += 1
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description=f"Retrieve title of {target_url}",
                    tool_name="browser_tool",
                    action="get_title",
                    args={"action": "get_title", "url": target_url},
                )
            )
            step_counter += 1

        # Case 2: Browser + URL + Text/Inspect query
        elif (has_browser_kw or urls) and any(w in query_lower for w in ("read text", "page text", "summary", "read content", "content")):
            target_url = urls[0] if urls else "https://www.google.com"
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description="Launch Chrome browser",
                    tool_name="application_tool",
                    action="launch",
                    args={"action": "launch", "app_name": "chrome"},
                )
            )
            step_counter += 1
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description=f"Navigate to {target_url}",
                    tool_name="browser_tool",
                    action="navigate",
                    args={"action": "navigate", "url": target_url},
                )
            )
            step_counter += 1
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description=f"Read visible text from {target_url}",
                    tool_name="browser_tool",
                    action="get_text",
                    args={"action": "get_text", "url": target_url, "max_chars": 1000},
                )
            )
            step_counter += 1

        # Case 3: Browser + URL navigation (e.g. "open Chrome and open bhartiyarishtey.com" or "open Chrome and visit Google")
        elif has_browser_kw or urls:
            target_url = urls[0] if urls else ("https://www.google.com" if "google" in query_lower else None)
            
            # Step 1: Launch application
            steps.append(
                TaskStep(
                    step_id=step_counter,
                    description="Launch Chrome browser",
                    tool_name="application_tool",
                    action="launch",
                    args={"action": "launch", "app_name": "chrome"},
                    expected="Chrome",
                )
            )
            step_counter += 1

            # Step 2: Navigate if URL specified or implied
            if target_url:
                steps.append(
                    TaskStep(
                        step_id=step_counter,
                        description=f"Navigate browser to {target_url}",
                        tool_name="browser_tool",
                        action="navigate",
                        args={"action": "navigate", "url": target_url},
                    )
                )
                step_counter += 1
                domain_short = urllib.parse.urlparse(target_url).netloc.replace("www.", "").split(".")[0]
                steps.append(
                    TaskStep(
                        step_id=step_counter,
                        description=f"Verify webpage {domain_short}",
                        tool_name="browser_tool",
                        action="verify_page",
                        args={"action": "verify_page", "expected": domain_short, "url": target_url},
                    )
                )
                step_counter += 1

        # Case 4: Compound System / Application / File query (e.g. "open notepad and check ram")
        elif " and " in query_lower or " aur " in query_lower or " then " in query_lower:
            parts = re.split(r"\s+(?:and|aur|then|\+)\s+", query_lower)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # App launch
                if any(w in part for w in ("open", "launch", "start", "kholo")):
                    app_name = part.replace("open", "").replace("launch", "").replace("start", "").replace("kholo", "").replace("app", "").strip()
                    steps.append(
                        TaskStep(
                            step_id=step_counter,
                            description=f"Launch application {app_name}",
                            tool_name="application_tool",
                            action="launch",
                            args={"action": "launch", "app_name": app_name},
                        )
                    )
                    step_counter += 1
                # System query
                elif any(w in part for w in ("ram", "memory")):
                    steps.append(
                        TaskStep(
                            step_id=step_counter,
                            description="Check RAM memory",
                            tool_name="system_tool",
                            action="ram",
                            args={"query": "ram"},
                        )
                    )
                    step_counter += 1
                elif any(w in part for w in ("cpu", "processor")):
                    steps.append(
                        TaskStep(
                            step_id=step_counter,
                            description="Check CPU information",
                            tool_name="system_tool",
                            action="cpu",
                            args={"query": "cpu"},
                        )
                    )
                    step_counter += 1
                elif any(w in part for w in ("search", "find", "dhundo")):
                    pattern = "*.pdf" if "pdf" in part else "*.txt" if "txt" in part else "*"
                    steps.append(
                        TaskStep(
                            step_id=step_counter,
                            description=f"Search files with pattern {pattern}",
                            tool_name="file_tool",
                            action="search_files",
                            args={"action": "search_files", "pattern": pattern},
                        )
                    )
                    step_counter += 1

        # Validate that all planned steps reference registered tools
        valid_steps = []
        for s in steps:
            if self.tool_registry.get_tool(s.tool_name):
                # Ensure each step adheres to retry limits
                s.max_retries = min(s.max_retries, MAX_RETRIES_PER_STEP)
                valid_steps.append(s)
            else:
                logger.warning(f"Plan validation rejected unregistered tool: {s.tool_name}")

        # Enforce maximum task step limit (max 10 steps) to prevent runaway execution
        if len(valid_steps) > MAX_TASK_STEPS:
            logger.warning(f"Plan steps exceeded {MAX_TASK_STEPS}. Truncating to {MAX_TASK_STEPS} steps.")
            valid_steps = valid_steps[:MAX_TASK_STEPS]

        plan.steps = valid_steps
        return plan

    def execute_plan(self, plan: TaskPlan) -> Dict[str, Any]:
        """
        Executes a TaskPlan through the task state machine with step verification and failure recovery.
        Enforces:
        - Max 10 steps per task
        - Max 2 automatic retries per step
        - Transitions: PLANNING -> AWAITING_CONFIRMATION -> EXECUTING -> VERIFYING -> COMPLETED / FAILED -> RECOVERY
        """
        if not plan.steps:
            plan.state = TaskState.COMPLETED
            plan.final_message = "No actions required."
            return {"success": True, "state": plan.state.value, "message": plan.final_message}

        # Enforce maximum 10 steps limit
        if len(plan.steps) > MAX_TASK_STEPS:
            plan.steps = plan.steps[:MAX_TASK_STEPS]

        # Check if any step requires user confirmation
        requires_confirmation = False
        for s in plan.steps:
            tool = self.tool_registry.get_tool(s.tool_name)
            if tool and tool.permission_level == PermissionLevel.CONFIRMATION_REQUIRED:
                requires_confirmation = True
                break

        if requires_confirmation:
            plan.state = TaskState.AWAITING_CONFIRMATION

        plan.state = TaskState.EXECUTING
        accumulated_messages = []
        last_title = None

        for step in plan.steps:
            step.status = "EXECUTING"
            step.max_retries = min(step.max_retries, MAX_RETRIES_PER_STEP)
            step_success = False

            # Execution with automatic retry (max 2 retries)
            for attempt in range(step.max_retries + 1):
                step.retries = attempt
                if attempt > 0:
                    step.status = "RETRYING"
                    time.sleep(0.2)

                result = self.tool_registry.execute_tool(step.tool_name, step.args)
                step.result = result

                # Step verification check
                plan.state = TaskState.VERIFYING
                if result.success and result.verified:
                    step_success = True
                    step.status = "VERIFIED"
                    step.verified = True
                    if result.data and "title" in result.data:
                        last_title = result.data["title"]
                    accumulated_messages.append(result.to_voice_summary())
                    break
                else:
                    logger.warning(f"Step {step.step_id} attempt {attempt + 1} failed: {result.error or result.message}")

            if not step_success:
                # Check if reflection engine can suggest a safe alternative strategy
                if self.reflection_engine and step.result:
                    plan.state = TaskState.RECOVERY
                    ref_res = self.reflection_engine.reflect_on_failure(
                        tool_name=step.tool_name,
                        args=step.args,
                        tool_result=step.result,
                        expected=step.expected,
                    )
                    if ref_res.should_retry and ref_res.suggested_tool and ref_res.suggested_args:
                        logger.info(f"TaskPlanner attempting reflection recovery: {ref_res.explanation}")
                        rec_res = self.tool_registry.execute_tool(ref_res.suggested_tool, ref_res.suggested_args)
                        if rec_res.success and rec_res.verified:
                            step_success = True
                            step.status = "VERIFIED"
                            step.verified = True
                            step.tool_name = ref_res.suggested_tool
                            step.args = ref_res.suggested_args
                            step.result = rec_res
                            accumulated_messages.append(rec_res.to_voice_summary())

            if not step_success:
                # Failure Path
                plan.state = TaskState.FAILED
                step.status = "FAILED"
                plan.error = step.result.error if step.result else f"Step {step.step_id} failed."

                # Initiate Recovery / Report
                plan.state = TaskState.RECOVERY
                failure_report = f"Task stopped at step '{step.description}'. {step.result.message if step.result else 'Operation failed.'}"
                plan.final_message = failure_report
                return {
                    "success": False,
                    "state": plan.state.value,
                    "error": plan.error,
                    "message": failure_report,
                    "steps": [s.__dict__ for s in plan.steps],
                }

        # All steps verified and completed
        plan.state = TaskState.COMPLETED

        # Synthesize clear, voice-friendly summary
        if last_title:
            plan.final_message = f"The page title is {last_title}."
        elif len(accumulated_messages) == 1:
            plan.final_message = accumulated_messages[0]
        else:
            plan.final_message = " ".join(accumulated_messages)

        return {
            "success": True,
            "state": plan.state.value,
            "message": plan.final_message,
            "steps": [s.__dict__ for s in plan.steps],
        }
