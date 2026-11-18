"""
DAKU Voice Providers Package
Provides factory functions and registry for interchangeable voice I/O providers.
"""

from typing import Optional

from config.voice_config import voice_config
from voice.providers.base import STTProvider, STTResult, TTSProvider, TTSResult
from voice.providers.google_stt import GoogleSTTProvider
from voice.providers.windows_tts import WindowsSapiTTSProvider


def get_stt_provider(name: Optional[str] = None, **kwargs) -> STTProvider:
    """
    Factory creating configured STT provider instance.
    Defaults to Google STT with text fallback.
    """
    provider_name = (name or voice_config.DAKU_STT_PROVIDER or "google_stt").strip().lower()

    if provider_name in ("google", "google_stt", "mic", "cloud_stt"):
        return GoogleSTTProvider(**kwargs)
    else:
        # Default to Google STT provider
        return GoogleSTTProvider(**kwargs)


def get_tts_provider(name: Optional[str] = None, **kwargs) -> TTSProvider:
    """
    Factory creating configured TTS provider instance.
    Defaults to Windows SAPI native TTS.
    """
    provider_name = (name or voice_config.DAKU_TTS_PROVIDER or "windows_sapi").strip().lower()

    if provider_name in ("windows", "windows_sapi", "windows_native", "sapi"):
        return WindowsSapiTTSProvider(**kwargs)
    else:
        return WindowsSapiTTSProvider(**kwargs)


__all__ = [
    "STTProvider",
    "TTSProvider",
    "STTResult",
    "TTSResult",
    "GoogleSTTProvider",
    "WindowsSapiTTSProvider",
    "get_stt_provider",
    "get_tts_provider",
]
