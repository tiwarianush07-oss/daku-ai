"""
DAKU Voice Providers Package
Provides factory functions and registry for interchangeable voice I/O providers.
"""

from typing import Optional

from config.voice_config import voice_config
from voice.providers.base import STTProvider, STTResult, TTSProvider, TTSResult
from voice.providers.google_stt import GoogleSTTProvider
from voice.providers.sarvam_stt import SarvamSTTProvider
from voice.providers.sarvam_tts import SarvamTTSProvider
from voice.providers.windows_tts import WindowsSapiTTSProvider


def get_stt_provider(name: Optional[str] = None, **kwargs) -> STTProvider:
    """
    Factory creating configured STT provider instance.
    Defaults to Sarvam STT if available or configured, otherwise Google STT.
    """
    provider_name = (name or voice_config.DAKU_STT_PROVIDER or "sarvam").strip().lower()

    if provider_name in ("sarvam", "sarvam_stt", "saaras"):
        sarvam = SarvamSTTProvider(**kwargs)
        if sarvam.is_available():
            return sarvam
        # If Sarvam key is missing, return Sarvam anyway so caller can inspect or fallback
        return sarvam
    elif provider_name in ("google", "google_stt", "mic", "cloud_stt"):
        return GoogleSTTProvider(**kwargs)
    else:
        # Default to Sarvam provider
        return SarvamSTTProvider(**kwargs)


def get_tts_provider(name: Optional[str] = None, **kwargs) -> TTSProvider:
    """
    Factory creating configured TTS provider instance.
    Defaults to Sarvam Bulbul if available or configured, otherwise Windows SAPI.
    """
    provider_name = (name or voice_config.DAKU_TTS_PROVIDER or "sarvam").strip().lower()

    if provider_name in ("sarvam", "sarvam_tts", "bulbul"):
        sarvam = SarvamTTSProvider(**kwargs)
        return sarvam
    elif provider_name in ("windows", "windows_sapi", "windows_native", "sapi"):
        return WindowsSapiTTSProvider(**kwargs)
    else:
        return SarvamTTSProvider(**kwargs)


__all__ = [
    "STTProvider",
    "TTSProvider",
    "STTResult",
    "TTSResult",
    "SarvamSTTProvider",
    "SarvamTTSProvider",
    "GoogleSTTProvider",
    "WindowsSapiTTSProvider",
    "get_stt_provider",
    "get_tts_provider",
]
