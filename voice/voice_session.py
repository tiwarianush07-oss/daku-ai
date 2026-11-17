"""
DAKU Voice Session Manager
Orchestrates turn-based voice conversations:
START -> LISTEN -> RECORD -> STT -> DAKU BRAIN -> TOOL EXECUTION -> VERIFICATION -> RESPONSE -> TTS -> PLAY -> LISTEN
Maintains session ID, turn ID, and latency tracking.
"""

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

from config.voice_config import voice_config
from voice_agent.turn_manager import TurnMetrics, VoiceTurnManager

if TYPE_CHECKING:
    from voice_agent.pipeline import VoicePipeline

logger = logging.getLogger("daku.voice.session")


class VoiceSessionManager:
    """
    Manages interactive voice interaction sessions for DAKU.
    Integrates with DAKU Brain and VoicePipeline.
    """

    def __init__(
        self,
        brain: Optional[Any] = None,
        pipeline: Optional[Any] = None,
        session_id: Optional[str] = None,
    ):
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:10]}"
        self.turn_manager = VoiceTurnManager(session_id=self.session_id)
        if pipeline is None:
            from voice_agent.pipeline import VoicePipeline
            pipeline = VoicePipeline(brain=brain, turn_manager=self.turn_manager)
        self.pipeline = pipeline
        self.is_active = False

    def start_session(self) -> None:
        """Initializes a new voice conversation session."""
        self.is_active = True
        logger.info(f"Voice Session {self.session_id} started.")

    def stop_session(self) -> None:
        """Ends the active voice session."""
        self.is_active = False
        logger.info(f"Voice Session {self.session_id} ended.")

    def run_turn(
        self,
        audio_input: Optional[bytes] = None,
        text_input: Optional[str] = None,
    ) -> TurnMetrics:
        """Executes a single turn in the voice session."""
        if not self.is_active:
            self.start_session()
        return self.pipeline.process_turn(audio_input=audio_input, text_input=text_input)
