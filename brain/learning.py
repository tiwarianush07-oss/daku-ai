"""
DAKU Self-Learning Engine Module
Phase 6: Adaptive Multi-Pass Reasoning & Safe Self-Learning

Provides:
- LearningEngine: Records compact, structured lessons from mistakes and successful strategies.
- Bounded memory storage (MAX_LESSONS = 500) with automatic secret redaction.
- Safe reuse of validated lessons to inform future planning passes.
- Strict Security Constitution: Never alters source code, permissions, or security policies.
"""

from dataclasses import asdict, dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger("daku.learning")


# Sensitive keys and patterns that must never be recorded into memory or persistent lessons
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret|auth|bearer|credential|cookie)"),
    re.compile(r"(?i)(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]{15,})"),
]


def sanitize_data(val: Any) -> Any:
    """Recursively redacts secrets, credentials, tokens, and passwords from lesson data."""
    if isinstance(val, str):
        masked = val
        for pat in SENSITIVE_PATTERNS:
            masked = pat.sub(r"***REDACTED***", masked)
        return masked
    elif isinstance(val, dict):
        clean_dict = {}
        for k, v in val.items():
            if any(p.search(str(k)) for p in SENSITIVE_PATTERNS):
                clean_dict[k] = "***REDACTED***"
            else:
                clean_dict[k] = sanitize_data(v)
        return clean_dict
    elif isinstance(val, list):
        return [sanitize_data(item) for item in val]
    return val


@dataclass
class Lesson:
    """Compact structured record of a failure recovery or proven success strategy."""
    lesson_id: str
    task_type: str
    failed_action: Optional[str] = None
    failure_reason: Optional[str] = None
    successful_action: Optional[str] = None
    strategy_name: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.8
    reusable: bool = True
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lesson":
        return cls(
            lesson_id=data.get("lesson_id", f"lesson_{int(time.time()*1000)}"),
            task_type=data.get("task_type", "general"),
            failed_action=data.get("failed_action"),
            failure_reason=data.get("failure_reason"),
            successful_action=data.get("successful_action"),
            strategy_name=data.get("strategy_name"),
            context=data.get("context", {}),
            timestamp=data.get("timestamp", time.time()),
            confidence=data.get("confidence", 0.8),
            reusable=data.get("reusable", True),
            usage_count=data.get("usage_count", 0),
        )


class LearningEngine:
    """
    Lightweight, bounded self-learning engine for DAKU.
    Operates under DAKU's Self-Learning Security Constitution:
    1. OBSERVE execution outcomes and verification results.
    2. RECORD compact structured lessons for failures and successes.
    3. GENERALIZE proven alternative strategies (e.g. Edge when Chrome fails).
    4. REUSE SAFELY during future planning passes without model retraining.
    5. NEVER rewrite Python code, alter security policies, or grant permissions.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        max_lessons: Optional[int] = None,
    ):
        self.max_lessons = max_lessons or getattr(settings, "MAX_LESSONS", 500)
        base_dir = getattr(settings, "BASE_DIR", Path.cwd())
        self.storage_path = storage_path or (base_dir / "data" / "lessons.json")
        self._lessons: List[Lesson] = []
        self._load_lessons()

    def _load_lessons(self) -> None:
        """Loads persisted lessons from disk if available."""
        if not self.storage_path.is_file():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            self._lessons.append(Lesson.from_dict(sanitize_data(item)))
                    self._enforce_bounds()
        except Exception as e:
            logger.warning(f"Could not load lessons from {self.storage_path}: {e}")

    def _save_lessons(self) -> None:
        """Persists lessons to disk safely."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            serializable = [l.to_dict() for l in self._lessons]
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not persist lessons to {self.storage_path}: {e}")

    def _enforce_bounds(self) -> None:
        """Enforces bounded memory constraint (MAX_LESSONS) using FIFO / usage eviction."""
        if len(self._lessons) > self.max_lessons:
            # Sort by usage count + timestamp and keep top max_lessons
            self._lessons = sorted(
                self._lessons,
                key=lambda x: (x.usage_count, x.timestamp),
                reverse=True,
            )[: self.max_lessons]

    def record_failure(
        self,
        task_type: str,
        failed_action: str,
        failure_reason: str,
        successful_alternative: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        confidence: float = 0.85,
    ) -> Lesson:
        """
        Records a failed attempt and optional working alternative.
        Sanitizes all data to guarantee zero credential leakage.
        """
        clean_ctx = sanitize_data(context or {})
        clean_failed = sanitize_data(failed_action)
        clean_reason = sanitize_data(failure_reason)
        clean_alt = sanitize_data(successful_alternative) if successful_alternative else None

        lesson_id = f"fail_{int(time.time() * 1000)}_{len(self._lessons)}"
        lesson = Lesson(
            lesson_id=lesson_id,
            task_type=task_type,
            failed_action=str(clean_failed),
            failure_reason=str(clean_reason),
            successful_action=str(clean_alt) if clean_alt else None,
            context=clean_ctx,
            timestamp=time.time(),
            confidence=confidence,
            reusable=True,
        )

        self._lessons.append(lesson)
        self._enforce_bounds()
        self._save_lessons()
        logger.info(f"LEARNING_EVENT recorded failure lesson: {lesson_id} [Task: {task_type}]")
        return lesson

    def record_success(
        self,
        task_type: str,
        strategy_name: str,
        successful_action: str,
        context: Optional[Dict[str, Any]] = None,
        confidence: float = 0.95,
    ) -> Lesson:
        """Records a successful strategy to be reused on subsequent requests."""
        clean_ctx = sanitize_data(context or {})
        clean_strat = sanitize_data(strategy_name)
        clean_action = sanitize_data(successful_action)

        lesson_id = f"succ_{int(time.time() * 1000)}_{len(self._lessons)}"
        lesson = Lesson(
            lesson_id=lesson_id,
            task_type=task_type,
            strategy_name=str(clean_strat),
            successful_action=str(clean_action),
            context=clean_ctx,
            timestamp=time.time(),
            confidence=confidence,
            reusable=True,
        )

        self._lessons.append(lesson)
        self._enforce_bounds()
        self._save_lessons()
        logger.info(f"LEARNING_EVENT recorded success lesson: {lesson_id} [Strategy: {strategy_name}]")
        return lesson

    def find_failure_lesson(self, task_type: str, failed_action: str) -> Optional[Lesson]:
        """Looks up if a known failure matches the current action and task type."""
        for lesson in reversed(self._lessons):
            if (
                lesson.reusable
                and lesson.failed_action
                and lesson.task_type.lower() == task_type.lower()
                and (
                    lesson.failed_action.lower() == failed_action.lower()
                    or failed_action.lower() in lesson.failed_action.lower()
                )
            ):
                lesson.usage_count += 1
                return lesson
        return None

    def get_recommended_strategy(
        self,
        task_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Lesson]:
        """Returns the highest confidence successful strategy for a given task type."""
        candidates = [
            l for l in self._lessons
            if l.reusable
            and l.successful_action
            and l.task_type.lower() == task_type.lower()
        ]
        if not candidates:
            return None

        # Return highest confidence / highest usage candidate
        best = max(candidates, key=lambda l: (l.confidence, l.usage_count))
        best.usage_count += 1
        return best

    def get_lessons(self) -> List[Lesson]:
        """Returns copy of all active lessons."""
        return list(self._lessons)

    def clear(self) -> None:
        """Clears in-memory lessons (useful for isolated tests)."""
        self._lessons.clear()
        if self.storage_path.is_file():
            try:
                self.storage_path.unlink()
            except Exception:
                pass
