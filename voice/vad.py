"""
DAKU Voice Activity Detection (VAD) Module
Lightweight energy-based VAD for speech segmentation and silence detection.
Zero external heavy neural models. Minimal CPU and memory overhead.
"""

import math
import struct
from typing import List, Optional

from config.voice_config import voice_config


class EnergyVAD:
    """
    Lightweight energy/RMS based Voice Activity Detector for 16-bit PCM audio.
    Identifies speech onset and end-of-speech silence without heavy ML dependencies.
    """

    def __init__(
        self,
        threshold: Optional[int] = None,
        sample_rate: int = 16000,
        silence_limit_seconds: Optional[float] = None,
    ):
        self.threshold = threshold if threshold is not None else voice_config.VAD_ENERGY_THRESHOLD
        self.sample_rate = sample_rate
        self.silence_limit_seconds = (
            silence_limit_seconds if silence_limit_seconds is not None else voice_config.VAD_SILENCE_LIMIT_SECONDS
        )

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """
        Calculates Root Mean Square (RMS) energy of 16-bit mono PCM bytes.
        """
        if not pcm_bytes or len(pcm_bytes) < 2:
            return 0.0

        # Number of 16-bit samples
        count = len(pcm_bytes) // 2
        format_str = f"<{count}h"
        try:
            samples = struct.unpack(format_str, pcm_bytes[: count * 2])
            sum_squares = sum(s * s for s in samples)
            mean_square = sum_squares / count
            return math.sqrt(mean_square)
        except Exception:
            return 0.0

    def is_speech(self, pcm_bytes: bytes) -> bool:
        """Determines if the given audio frame contains active speech."""
        return self.calculate_rms(pcm_bytes) > self.threshold

    def trim_silence(
        self,
        pcm_bytes: bytes,
        frame_duration_ms: int = 30,
    ) -> bytes:
        """
        Trims leading and trailing silence from raw 16-bit PCM audio.
        """
        if not pcm_bytes:
            return b""

        bytes_per_sample = 2
        frame_size = int((self.sample_rate * frame_duration_ms / 1000.0) * bytes_per_sample)
        if frame_size <= 0:
            return pcm_bytes

        frames = [pcm_bytes[i : i + frame_size] for i in range(0, len(pcm_bytes), frame_size)]

        # Find first non-silent frame
        start_idx = 0
        for i, frame in enumerate(frames):
            if self.calculate_rms(frame) > self.threshold:
                start_idx = max(0, i - 1)  # Keep 1 frame prefix for natural onset
                break
        else:
            return b""  # All silence

        # Find last non-silent frame
        end_idx = len(frames)
        for i in range(len(frames) - 1, -1, -1):
            if self.calculate_rms(frames[i]) > self.threshold:
                end_idx = min(len(frames), i + 2)  # Keep trailing frame
                break

        trimmed_frames = frames[start_idx:end_idx]
        return b"".join(trimmed_frames)
