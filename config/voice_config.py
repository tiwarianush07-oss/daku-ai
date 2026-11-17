"""
DAKU Voice Configuration Module
Manages configuration for Sarvam AI, Google STT, Windows SAPI TTS,
privacy flags, latency budgets, and retry parameters.
Loads from environment variables with safe defaults.
Zero external dependencies.
"""

import os
from dataclasses import dataclass
from pathlib import Path
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

    # Sarvam Credentials
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"

    # Sarvam STT (Saaras)
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_STT_MODE: str = "transcribe"  # transcribe | translate | verbatim | translit | codemix
    SARVAM_LANGUAGE: str = "hi-IN"

    # Sarvam TTS (Bulbul)
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_SPEAKER: str = "shubh"
    SARVAM_TTS_PACE: float = 1.0
    SARVAM_TTS_TEMPERATURE: float = 0.6

    # Optional Sarvam Conversational LLM
    SARVAM_LLM_MODEL: str = "sarvam-105b-conversations"
    SARVAM_AGENTIC_MODEL: str = "sarvam-105b"

    # Active Provider Selection & Fallback Order
    # STT cascade: sarvam -> google_stt -> text_fallback
    # TTS cascade: sarvam -> windows_sapi -> text_fallback
    DAKU_STT_PROVIDER: str = "sarvam"
    DAKU_TTS_PROVIDER: str = "sarvam"
    DAKU_MODEL_PROVIDER: str = "deepseek"

    # Privacy & Storage Constraints
    DAKU_VOICE_STORE_AUDIO: bool = False
    DAKU_VOICE_STORE_TRANSCRIPTS: bool = False

    # Network, Timeouts & Retry Limits
    SARVAM_REQUEST_TIMEOUT: float = 15.0
    SARVAM_MAX_RETRIES: int = 3
    SARVAM_BACKOFF_FACTOR: float = 0.5

    # VAD & Audio Settings
    SAMPLE_RATE: int = 16000
    CHANNELS: int = 1
    VAD_ENERGY_THRESHOLD: int = 300
    VAD_SILENCE_LIMIT_SECONDS: float = 0.8

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        """Build VoiceConfig from current environment variables."""
        return cls(
            SARVAM_API_KEY=os.getenv("SARVAM_API_KEY", "").strip(),
            SARVAM_BASE_URL=os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/"),
            SARVAM_STT_MODEL=os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip(),
            SARVAM_STT_MODE=os.getenv("SARVAM_STT_MODE", "transcribe").strip().lower(),
            SARVAM_LANGUAGE=os.getenv("SARVAM_LANGUAGE", "hi-IN").strip(),
            SARVAM_TTS_MODEL=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip(),
            SARVAM_TTS_SPEAKER=os.getenv("SARVAM_TTS_SPEAKER", "shubh").strip().lower(),
            SARVAM_TTS_PACE=float(os.getenv("SARVAM_TTS_PACE", "1.0")),
            SARVAM_TTS_TEMPERATURE=float(os.getenv("SARVAM_TTS_TEMPERATURE", "0.6")),
            SARVAM_LLM_MODEL=os.getenv("SARVAM_LLM_MODEL", "sarvam-105b-conversations").strip(),
            SARVAM_AGENTIC_MODEL=os.getenv("SARVAM_AGENTIC_MODEL", "sarvam-105b").strip(),
            DAKU_STT_PROVIDER=os.getenv("DAKU_STT_PROVIDER", os.getenv("STT_PROVIDER", "sarvam")).strip().lower(),
            DAKU_TTS_PROVIDER=os.getenv("DAKU_TTS_PROVIDER", os.getenv("TTS_PROVIDER", "sarvam")).strip().lower(),
            DAKU_MODEL_PROVIDER=os.getenv("DAKU_MODEL_PROVIDER", os.getenv("MODEL_PROVIDER", "deepseek")).strip().lower(),
            DAKU_VOICE_STORE_AUDIO=os.getenv("DAKU_VOICE_STORE_AUDIO", "false").strip().lower() == "true",
            DAKU_VOICE_STORE_TRANSCRIPTS=os.getenv("DAKU_VOICE_STORE_TRANSCRIPTS", "false").strip().lower() == "true",
            SARVAM_REQUEST_TIMEOUT=float(os.getenv("SARVAM_REQUEST_TIMEOUT", "15.0")),
            SARVAM_MAX_RETRIES=int(os.getenv("SARVAM_MAX_RETRIES", "3")),
            SARVAM_BACKOFF_FACTOR=float(os.getenv("SARVAM_BACKOFF_FACTOR", "0.5")),
            SAMPLE_RATE=int(os.getenv("VOICE_SAMPLE_RATE", "16000")),
            CHANNELS=int(os.getenv("VOICE_CHANNELS", "1")),
            VAD_ENERGY_THRESHOLD=int(os.getenv("VAD_ENERGY_THRESHOLD", "300")),
            VAD_SILENCE_LIMIT_SECONDS=float(os.getenv("VAD_SILENCE_LIMIT_SECONDS", "0.8")),
        )

    def has_sarvam_key(self) -> bool:
        """Checks if a valid Sarvam API key is configured."""
        return bool(self.SARVAM_API_KEY and self.SARVAM_API_KEY != "your_sarvam_api_key_here")

    def safe_dict(self) -> dict:
        """Returns configuration dictionary with credentials masked for safe logging/doctor."""
        return {
            "sarvam_api_key_configured": self.has_sarvam_key(),
            "sarvam_api_key_masked": _mask_secret(self.SARVAM_API_KEY),
            "sarvam_stt_model": self.SARVAM_STT_MODEL,
            "sarvam_stt_mode": self.SARVAM_STT_MODE,
            "sarvam_tts_model": self.SARVAM_TTS_MODEL,
            "sarvam_tts_speaker": self.SARVAM_TTS_SPEAKER,
            "sarvam_language": self.SARVAM_LANGUAGE,
            "daku_stt_provider": self.DAKU_STT_PROVIDER,
            "daku_tts_provider": self.DAKU_TTS_PROVIDER,
            "store_audio": self.DAKU_VOICE_STORE_AUDIO,
            "store_transcripts": self.DAKU_VOICE_STORE_TRANSCRIPTS,
            "request_timeout": self.SARVAM_REQUEST_TIMEOUT,
        }


# Global singleton instance
voice_config = VoiceConfig.from_env()
