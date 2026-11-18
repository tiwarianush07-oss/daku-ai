"""
Google Speech-To-Text Provider Adapter for DAKU
Wraps Google Web Speech API endpoint via SpeechRecognition.
Part of DAKU's resilient multi-tier fallback architecture.
Zero local neural RAM footprint.
"""

import io
import logging
import time
from pathlib import Path
from typing import Any, Optional, Union

from voice.providers.base import STTProvider, STTResult

logger = logging.getLogger("daku.voice.google_stt")


class GoogleSTTProvider(STTProvider):
    """
    Google Web STT provider implementing STTProvider interface.
    Serves as the primary cloud STT provider with offline text fallback.
    """

    def __init__(self, language: str = "en-IN"):
        self.language = language

    def is_available(self) -> bool:
        """Checks if speech_recognition library is installed."""
        try:
            import speech_recognition as sr  # noqa: F401
            return True
        except ImportError:
            return False

    def get_provider_name(self) -> str:
        return "google_stt"

    def transcribe(
        self,
        audio: Union[bytes, str, Path, io.BytesIO, Any],
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[STTResult]:
        """
        Transcribes audio data using Google Web STT.
        Accepts raw WAV bytes, file path, BytesIO, or speech_recognition.AudioData.
        """
        try:
            import speech_recognition as sr
        except ImportError:
            logger.warning("speech_recognition package not installed.")
            return None

        lang = language or self.language
        recognizer = sr.Recognizer()
        t0 = time.perf_counter()

        try:
            sr_audio: Optional[sr.AudioData] = None

            if isinstance(audio, sr.AudioData):
                sr_audio = audio
            elif isinstance(audio, (bytes, bytearray)):
                # Read WAV from memory
                wav_io = io.BytesIO(audio)
                with sr.AudioFile(wav_io) as source:
                    sr_audio = recognizer.record(source)
            elif isinstance(audio, (str, Path)):
                with sr.AudioFile(str(audio)) as source:
                    sr_audio = recognizer.record(source)
            elif isinstance(audio, io.BytesIO):
                audio.seek(0)
                with sr.AudioFile(audio) as source:
                    sr_audio = recognizer.record(source)
            else:
                logger.warning(f"Unsupported audio type for Google STT: {type(audio)}")
                return None

            if sr_audio is None:
                return None

            text = recognizer.recognize_google(sr_audio, language=lang)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            if not text or not str(text).strip():
                return None

            clean_text = str(text).strip()
            return STTResult(
                text=clean_text,
                language=lang,
                provider="google_stt",
                model="google-web",
                request_id=f"google-{int(time.time()*1000)}",
                latency_ms=latency_ms,
            )

        except sr.UnknownValueError:
            logger.debug("Google STT: speech unclear / unknown value.")
            return None
        except sr.RequestError as e:
            logger.warning(f"Google STT network error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Google STT error: {e}")
            return None
