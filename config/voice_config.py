"""
DAKU Voice Configuration Module
Manages configuration for Google STT, Windows SAPI TTS,
privacy flags, latency budgets, and audio parameters.
Loads from environment variables with safe defaults.
Zero external dependencies.
"""

import os
from dataclasses import dataclass
from typing import Optional


def _mask_secret(val: Optional[str]) -> str:
    """Masks secret token/key for secure logging. Never prints full secret."""
    if not val:
        return "<not-set>"
    s = str(val).strip()
    if len(s) <= 8:
        return "********"
    return f"{s[:3]}...{s[-3:]}"


@dataclass
class VoiceConfig:
    """Voice configuration settings container."""

    # Active Provider Selection
    # STT cascade: google_stt -> text_fallback
    # TTS cascade: windows_sapi -> text_fallback
    DAKU_STT_PROVIDER: str = "google_stt"
    DAKU_TTS_PROVIDER: str = "windows_sapi"
    DAKU_MODEL_PROVIDER: str = "deepseek"
    VOICE_LANGUAGE: str = "en-IN"

    # Privacy & Storage Constraints
    DAKU_VOICE_STORE_AUDIO: bool = False
    DAKU_VOICE_STORE_TRANSCRIPTS: bool = False

    # VAD & Audio Settings
    SAMPLE_RATE: int = 16000
    CHANNELS: int = 1
    VAD_ENERGY_THRESHOLD: int = 300
    VAD_SILENCE_LIMIT_SECONDS: float = 0.8
    REQUEST_TIMEOUT: float = 10.0

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        """Build VoiceConfig from current environment variables."""
        return cls(
            DAKU_STT_PROVIDER=os.getenv("DAKU_STT_PROVIDER", os.getenv("STT_PROVIDER", "google_stt")).strip().lower(),
            DAKU_TTS_PROVIDER=os.getenv("DAKU_TTS_PROVIDER", os.getenv("TTS_PROVIDER", "windows_sapi")).strip().lower(),
            DAKU_MODEL_PROVIDER=os.getenv("DAKU_MODEL_PROVIDER", os.getenv("MODEL_PROVIDER", "deepseek")).strip().lower(),
            VOICE_LANGUAGE=os.getenv("STT_LANGUAGE", "en-IN").strip(),
            DAKU_VOICE_STORE_AUDIO=os.getenv("DAKU_VOICE_STORE_AUDIO", "false").strip().lower() == "true",
            DAKU_VOICE_STORE_TRANSCRIPTS=os.getenv("DAKU_VOICE_STORE_TRANSCRIPTS", "false").strip().lower() == "true",
            SAMPLE_RATE=int(os.getenv("VOICE_SAMPLE_RATE", "16000")),
            CHANNELS=int(os.getenv("VOICE_CHANNELS", "1")),
            VAD_ENERGY_THRESHOLD=int(os.getenv("VAD_ENERGY_THRESHOLD", "300")),
            VAD_SILENCE_LIMIT_SECONDS=float(os.getenv("VAD_SILENCE_LIMIT_SECONDS", "0.8")),
            REQUEST_TIMEOUT=float(os.getenv("VOICE_REQUEST_TIMEOUT", "10.0")),
        )

    def safe_dict(self) -> dict:
        """Returns configuration dictionary for safe logging/doctor."""
        return {
            "daku_stt_provider": self.DAKU_STT_PROVIDER,
            "daku_tts_provider": self.DAKU_TTS_PROVIDER,
            "voice_language": self.VOICE_LANGUAGE,
            "store_audio": self.DAKU_VOICE_STORE_AUDIO,
            "store_transcripts": self.DAKU_VOICE_STORE_TRANSCRIPTS,
            "sample_rate": self.SAMPLE_RATE,
            "channels": self.CHANNELS,
        }


# Global singleton instance
voice_config = VoiceConfig.from_env()
