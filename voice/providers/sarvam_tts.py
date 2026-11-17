"""
Sarvam AI Text-To-Speech (Bulbul v3) Provider for DAKU
Production-grade integration with official Sarvam API contract.
Default Model: bulbul:v3 | Default Speaker: shubh
Supports 30+ voices across 11 Indic languages and Indian English.
Strict adherence to Bulbul v3 parameters (no unsupported pitch/loudness).
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Iterator, List, Optional

from config.voice_config import VoiceConfig, voice_config
from voice.providers.base import TTSProvider, TTSResult

logger = logging.getLogger("daku.voice.sarvam_tts")


class SarvamTTSProvider(TTSProvider):
    """
    Production-grade Sarvam AI Bulbul v3 TTS provider.
    Communicates with https://api.sarvam.ai/text-to-speech.
    """

    NON_RETRY_STATUSES = {400, 401, 403, 422}
    RETRY_STATUSES = {408, 429, 500, 502, 503, 504}

    # Verified Bulbul v3 popular voices
    KNOWN_VOICES = [
        "shubh", "aditya", "ritu", "priya", "neha", "amit",
        "kavya", "ishita", "shreya", "ratan", "rohan", "pooja"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        speaker: Optional[str] = None,
        language: Optional[str] = None,
        pace: Optional[float] = None,
        temperature: Optional[float] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ):
        cfg = voice_config
        self.api_key = (api_key or cfg.SARVAM_API_KEY).strip()
        self.model = (model or cfg.SARVAM_TTS_MODEL).strip()
        self.speaker = (speaker or cfg.SARVAM_TTS_SPEAKER).strip().lower()
        self.language = (language or cfg.SARVAM_LANGUAGE).strip()
        self.pace = max(0.5, min(2.0, pace if pace is not None else cfg.SARVAM_TTS_PACE))
        self.temperature = max(0.01, min(1.0, temperature if temperature is not None else cfg.SARVAM_TTS_TEMPERATURE))
        self.base_url = (base_url or cfg.SARVAM_BASE_URL).rstrip("/")
        self.timeout = timeout or cfg.SARVAM_REQUEST_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else cfg.SARVAM_MAX_RETRIES
        self.backoff_factor = backoff_factor if backoff_factor is not None else cfg.SARVAM_BACKOFF_FACTOR

    def is_available(self) -> bool:
        """Returns True if a valid API key is configured."""
        return bool(self.api_key and self.api_key != "your_sarvam_api_key_here")

    def get_provider_name(self) -> str:
        return "sarvam"

    def list_voices(self) -> List[str]:
        """Returns list of supported Bulbul v3 voices."""
        return list(self.KNOWN_VOICES)

    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        pace: Optional[float] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[TTSResult]:
        """
        Synthesizes text into WAV audio using Sarvam Bulbul v3 REST API.
        Enforces supported parameters only (no pitch or loudness).
        """
        if not self.is_available():
            logger.warning("Sarvam TTS requested but API key is missing.")
            return None

        clean_text = (text or "").strip()
        if not clean_text:
            logger.info("Empty text passed to Sarvam TTS.")
            return None

        # Truncate to maximum characters supported by Sarvam (2500 chars)
        if len(clean_text) > 2500:
            clean_text = clean_text[:2497] + "..."

        target_model = (model or self.model).strip()
        target_speaker = (speaker or self.speaker).strip().lower()
        target_lang = (language or self.language).strip()
        target_pace = pace if pace is not None else self.pace
        target_temp = temperature if temperature is not None else self.temperature

        # Strictly build supported payload without unsupported fields
        payload: Dict[str, Any] = {
            "text": clean_text,
            "model": target_model,
            "speaker": target_speaker,
            "language_code": target_lang,
            "pace": target_pace,
            "temperature": target_temp,
        }

        endpoint = f"{self.base_url}/text-to-speech"
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "DAKU-Voice-Agent/5.0",
        }

        retries = 0
        while retries <= self.max_retries:
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    status_code = getattr(resp, "status", 200)
                    if status_code == 200:
                        body_raw = resp.read().decode("utf-8")
                        data = json.loads(body_raw)

                        audios = data.get("audios", [])
                        audio_b64 = ""
                        if isinstance(audios, list) and len(audios) > 0:
                            audio_b64 = audios[0]
                        elif "audio" in data:
                            audio_b64 = data["audio"]

                        if not audio_b64:
                            logger.warning("Sarvam TTS returned response without audio payload.")
                            return None

                        try:
                            audio_bytes = base64.b64decode(audio_b64)
                        except Exception as e:
                            logger.error(f"Failed to decode base64 audio from Sarvam TTS: {e}")
                            return None

                        return TTSResult(
                            audio_bytes=audio_bytes,
                            audio_base64=audio_b64,
                            format="wav",
                            sample_rate=24000,
                            provider="sarvam",
                            model=target_model,
                            speaker=target_speaker,
                            latency_ms=latency_ms,
                            metadata={"characters": len(clean_text), "status_code": status_code},
                        )
                    return None

            except urllib.error.HTTPError as e:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                status_code = e.code
                logger.warning(
                    f"Sarvam TTS HTTP error {status_code} (attempt {retries + 1}/{self.max_retries + 1})"
                )

                if status_code in self.NON_RETRY_STATUSES:
                    logger.error(f"Sarvam TTS non-retryable error {status_code}. Aborting.")
                    return None

                if status_code in self.RETRY_STATUSES and retries < self.max_retries:
                    sleep_time = self.backoff_factor * (2**retries)
                    time.sleep(sleep_time)
                    retries += 1
                    continue
                return None

            except (urllib.error.URLError, TimeoutError) as e:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                logger.warning(
                    f"Sarvam TTS network/timeout error: {e} (attempt {retries + 1}/{self.max_retries + 1})"
                )
                if retries < self.max_retries:
                    sleep_time = self.backoff_factor * (2**retries)
                    time.sleep(sleep_time)
                    retries += 1
                    continue
                return None

            except Exception as e:
                logger.error(f"Unexpected error in Sarvam TTS: {e}")
                return None

        return None

    def speak(self, text: str, **kwargs: Any) -> bool:
        """
        Synthesizes speech using Sarvam TTS and plays back via local audio device.
        """
        res = self.synthesize(text, **kwargs)
        if not res or not res.audio_bytes:
            return False

        from voice.audio import play_audio_bytes
        return play_audio_bytes(res.audio_bytes)

    def stream_synthesize(
        self,
        text: str,
        chunk_size_bytes: int = 4096,
        **kwargs: Any,
    ) -> Iterator[bytes]:
        """
        Streaming interface hook (Phase 2).
        Yields chunked audio bytes from synthesized result.
        """
        res = self.synthesize(text, **kwargs)
        if not res or not res.audio_bytes:
            return

        raw = res.audio_bytes
        for i in range(0, len(raw), chunk_size_bytes):
            yield raw[i : i + chunk_size_bytes]
