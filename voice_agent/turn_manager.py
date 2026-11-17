"""
DAKU Voice Turn Manager & Observability
Manages the lifecycle, state transitions, and latency metrics of voice turns.
Safe observability: never logs API keys, credentials, or raw audio by default.
"""

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.voice_config import voice_config

logger = logging.getLogger("daku.voice.turn")


class TurnState(str, enum.Enum):
    """Lifecycle states of an individual voice interaction turn."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    RECORDING = "RECORDING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    CONFIRMING = "CONFIRMING"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


@dataclass
class TurnMetrics:
    """Latency and execution metrics for a single turn."""
    turn_id: str
    session_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    stt_latency_ms: float = 0.0
    brain_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    total_turn_latency_ms: float = 0.0
    time_to_first_audio_ms: float = 0.0
    stt_provider: str = ""
    tts_provider: str = ""
    fallback_used: bool = False
    success: bool = True
    error_message: Optional[str] = None

    def finalize(self) -> None:
        """Calculates total turn latency upon completion."""
        self.end_time = time.time()
        self.total_turn_latency_ms = round((self.end_time - self.start_time) * 1000.0, 2)

    def to_safe_dict(self) -> Dict[str, Any]:
        """Returns safe observability dictionary without sensitive data or transcripts."""
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "stt_provider": self.stt_provider,
            "tts_provider": self.tts_provider,
            "stt_latency_ms": round(self.stt_latency_ms, 2),
            "brain_latency_ms": round(self.brain_latency_ms, 2),
            "tool_latency_ms": round(self.tool_latency_ms, 2),
            "tts_latency_ms": round(self.tts_latency_ms, 2),
            "total_turn_latency_ms": round(self.total_turn_latency_ms, 2),
            "time_to_first_audio_ms": round(self.time_to_first_audio_ms, 2),
            "fallback_used": self.fallback_used,
            "success": self.success,
            "error": self.error_message,
        }


class VoiceTurnManager:
    """
    Orchestrates turn state transitions, timeout tracking, and safe metrics logging.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
        self.turn_counter = 0
        self.current_state = TurnState.IDLE
        self.active_metrics: Optional[TurnMetrics] = None
        self.history: List[TurnMetrics] = []

    def start_turn(self) -> TurnMetrics:
        """Begins a new voice turn and initializes metrics."""
        self.turn_counter += 1
        turn_id = f"turn-{self.turn_counter:04d}"
        self.active_metrics = TurnMetrics(turn_id=turn_id, session_id=self.session_id)
        self.transition_to(TurnState.LISTENING)
        return self.active_metrics

    def transition_to(self, new_state: TurnState) -> None:
        """Transitions to next turn state."""
        self.current_state = new_state
        logger.debug(f"[{self.session_id}][{self.current_turn_id}] State -> {new_state.value}")

    @property
    def current_turn_id(self) -> str:
        return self.active_metrics.turn_id if self.active_metrics else "turn-0000"

    def complete_turn(self, success: bool = True, error: Optional[str] = None) -> TurnMetrics:
        """Finalizes the turn and records safe metrics."""
        if not self.active_metrics:
            self.start_turn()

        metrics = self.active_metrics
        metrics.success = success
        metrics.error_message = error
        metrics.finalize()

        self.transition_to(TurnState.COMPLETED if success else TurnState.ERROR)
        self.history.append(metrics)
        self.current_state = TurnState.IDLE

        # Safe log without transcripts or credentials
        logger.info(f"Turn {metrics.turn_id} completed in {metrics.total_turn_latency_ms:.1f}ms (STT: {metrics.stt_latency_ms:.1f}ms, Brain: {metrics.brain_latency_ms:.1f}ms, TTS: {metrics.tts_latency_ms:.1f}ms)")
        return metrics
