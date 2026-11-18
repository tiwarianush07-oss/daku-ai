"""
DAKU End-to-End Voice Agent Pipeline
Integrates:
Microphone / Audio -> VAD -> Google STT -> Transcript ->
DAKU Brain / Router -> Planner -> Permission Manager -> Tools -> Verifier ->
Response -> TTS Normalizer -> Windows SAPI TTS -> Audio Playback.

Multi-tier Fallbacks:
- STT: Google STT -> Console Text Input
- TTS: Windows SAPI -> Console Print
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple, Union

from config.voice_config import voice_config
from voice.audio import capture_mic_audio, play_audio_bytes
from voice.providers import (
    GoogleSTTProvider,
    STTProvider,
    TTSProvider,
    WindowsSapiTTSProvider,
)
from voice.vad import EnergyVAD
from voice_agent.normalizer import TTSNormalizer
from voice_agent.turn_manager import TurnMetrics, TurnState, VoiceTurnManager

logger = logging.getLogger("daku.voice.pipeline")


class VoicePipeline:
    """
    Production-grade Voice Agent pipeline executing turn-based interactions
    with automatic provider fallback and strict security boundaries.
    """

    def __init__(
        self,
        brain: Optional[Any] = None,
        stt_provider: Optional[STTProvider] = None,
        tts_provider: Optional[TTSProvider] = None,
        turn_manager: Optional[VoiceTurnManager] = None,
        vad: Optional[EnergyVAD] = None,
    ):
        self.brain = brain
        self.turn_manager = turn_manager or VoiceTurnManager()
        self.vad = vad or EnergyVAD()
        self.normalizer = TTSNormalizer()

        # Primary and fallback providers
        self.stt_provider = stt_provider or GoogleSTTProvider()
        self.google_stt = self.stt_provider
        self.tts_provider = tts_provider or WindowsSapiTTSProvider()
        self.windows_tts = self.tts_provider

        # Configured preference
        self.preferred_stt = voice_config.DAKU_STT_PROVIDER
        self.preferred_tts = voice_config.DAKU_TTS_PROVIDER

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
    ) -> Tuple[Optional[str], str, float, bool]:
        """
        Transcribes audio through Google STT.
        Returns (transcript, provider_used, latency_ms, fallback_used).
        """
        lang = language or getattr(voice_config, "LANGUAGE", "en-IN")
        fallback_used = False

        if self.google_stt and self.google_stt.is_available():
            t0 = time.perf_counter()
            res = self.google_stt.transcribe(audio_bytes, language=lang)
            if res and res.text:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return res.text, "google_stt", latency_ms, False

        return None, "none", 0.0, fallback_used

    def synthesize_and_play(
        self,
        text: str,
        language: Optional[str] = None,
    ) -> Tuple[bool, str, float, bool]:
        """
        Synthesizes and plays speech through TTS cascade:
        1. Windows SAPI (native zero-RAM primary)
        2. Console print fallback
        Returns (success, provider_used, latency_ms, fallback_used).
        """
        if not text or not text.strip():
            return True, "none", 0.0, False

        # Normalize text for speech output
        clean_text = self.normalizer.clean_for_speech(text, target_lang=language or getattr(voice_config, "LANGUAGE", "en-IN"))
        fallback_used = False

        # Primary: Windows Native SAPI
        if self.windows_tts and self.windows_tts.is_available():
            t0 = time.perf_counter()
            spoken = self.windows_tts.speak(clean_text)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if spoken:
                return True, "windows_sapi", latency_ms, False
            fallback_used = True

        # Fallback: Console print
        print(f"[Spoken Output Fallback]: {clean_text}")
        return True, "text_fallback", 0.0, True

    def process_turn(
        self,
        audio_input: Optional[bytes] = None,
        text_input: Optional[str] = None,
    ) -> TurnMetrics:
        """
        Executes a complete voice agent turn:
        Audio capture/VAD -> STT -> Brain -> Tools -> Verifier -> Normalizer -> TTS -> Playback.
        """
        metrics = self.turn_manager.start_turn()

        # Step 1: Capture or obtain audio
        audio_bytes = audio_input
        transcript = text_input

        if not transcript:
            if not audio_bytes:
                self.turn_manager.transition_to(TurnState.RECORDING)
                audio_bytes = capture_mic_audio()

            if not audio_bytes:
                self.turn_manager.complete_turn(success=False, error="No audio captured")
                return metrics

            # Step 2: Speech-To-Text
            self.turn_manager.transition_to(TurnState.TRANSCRIBING)
            text, stt_prov, stt_lat, stt_fallback = self.transcribe_audio(audio_bytes)
            metrics.stt_latency_ms = stt_lat
            metrics.stt_provider = stt_prov
            if stt_fallback:
                metrics.fallback_used = True

            if not text:
                self.turn_manager.complete_turn(success=False, error="STT produced no transcript")
                return metrics
            transcript = text

        # Step 3: DAKU Brain Thinking & Tool Execution
        self.turn_manager.transition_to(TurnState.THINKING)
        reply = ""
        t_brain = time.perf_counter()
        if self.brain:
            try:
                reply = self.brain.think(transcript)
            except Exception as e:
                logger.error(f"DAKU Brain execution failed: {e}")
                reply = f"I encountered an error processing your request: {e}"
        else:
            reply = f"Echo: {transcript}"
        metrics.brain_latency_ms = (time.perf_counter() - t_brain) * 1000.0

        # Step 4: TTS Normalization & Speech Playback
        self.turn_manager.transition_to(TurnState.SYNTHESIZING)
        t_first_audio = time.perf_counter()
        tts_ok, tts_prov, tts_lat, tts_fallback = self.synthesize_and_play(reply)
        metrics.time_to_first_audio_ms = (time.perf_counter() - t_first_audio) * 1000.0
        metrics.tts_latency_ms = tts_lat
        metrics.tts_provider = tts_prov
        if tts_fallback:
            metrics.fallback_used = True

        self.turn_manager.complete_turn(success=tts_ok)
        return metrics
