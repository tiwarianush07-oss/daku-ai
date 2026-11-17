"""
Sarvam AI Speech-To-Text (Saaras) Provider for DAKU
Production-grade integration with official Sarvam API contract.
Default Model: saaras:v4 | Default Mode: transcribe
Supports: transcribe, translate, verbatim, translit, codemix.
Zero local AI model RAM footprint. Standard-library first networking.
"""

import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from config.voice_config import VoiceConfig, voice_config
from voice.providers.base import STTProvider, STTResult

logger = logging.getLogger("daku.voice.sarvam_stt")


class SarvamSTTProvider(STTProvider):
    """
    Production-grade Sarvam AI Saaras STT provider.
    Communicates directly with https://api.sarvam.ai/speech-to-text.
    """

    SUPPORTED_MODES = {"transcribe", "translate", "verbatim", "translit", "codemix"}
    NON_RETRY_STATUSES = {400, 401, 403, 422}
    RETRY_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        language: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ):
        cfg = voice_config
        self.api_key = (api_key or cfg.SARVAM_API_KEY).strip()
        self.model = (model or cfg.SARVAM_STT_MODEL).strip()
        self.mode = (mode or cfg.SARVAM_STT_MODE).strip().lower()
        if self.mode not in self.SUPPORTED_MODES:
            logger.warning(f"Unknown Sarvam STT mode '{self.mode}', defaulting to 'transcribe'.")
            self.mode = "transcribe"
        self.language = (language or cfg.SARVAM_LANGUAGE).strip()
        self.base_url = (base_url or cfg.SARVAM_BASE_URL).rstrip("/")
        self.timeout = timeout or cfg.SARVAM_REQUEST_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else cfg.SARVAM_MAX_RETRIES
        self.backoff_factor = backoff_factor if backoff_factor is not None else cfg.SARVAM_BACKOFF_FACTOR

    def is_available(self) -> bool:
        """Returns True if a valid API key is configured."""
        return bool(self.api_key and self.api_key != "your_sarvam_api_key_here")

    def get_provider_name(self) -> str:
        return "sarvam"

    def _build_multipart_payload(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        form_fields: Dict[str, str],
    ) -> Tuple[bytes, str]:
        """
        Builds an RFC 7578 multipart/form-data body using standard library only.
        Returns (body_bytes, boundary_header).
        """
        boundary = f"----DakuBoundary{uuid.uuid4().hex}"
        body = io.BytesIO()

        # Add form fields (model, mode, language_code)
        for key, val in form_fields.items():
            if val is not None:
                body.write(f"--{boundary}\r\n".encode("utf-8"))
                body.write(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
                body.write(f"{val}\r\n".encode("utf-8"))

        # Add file part
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.write(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.write(audio_bytes)
        body.write(b"\r\n")

        # Closing boundary
        body.write(f"--{boundary}--\r\n".encode("utf-8"))
        content_type_header = f"multipart/form-data; boundary={boundary}"
        return body.getvalue(), content_type_header

    def _extract_audio_bytes(
        self,
        audio: Union[bytes, str, Path, io.BytesIO, Any],
    ) -> Optional[Tuple[bytes, str, str]]:
        """
        Extracts raw bytes, filename, and mime-type from various audio inputs.
        """
        if not audio:
            return None

        # Check for speech_recognition.AudioData
        if hasattr(audio, "get_wav_data"):
            return audio.get_wav_data(), "audio.wav", "audio/wav"

        # Check for raw bytes
        if isinstance(audio, (bytes, bytearray)):
            if len(audio) == 0:
                return None
            return bytes(audio), "audio.wav", "audio/wav"

        # Check for BytesIO
        if isinstance(audio, io.BytesIO):
            audio.seek(0)
            data = audio.read()
            if len(data) == 0:
                return None
            return data, "audio.wav", "audio/wav"

        # Check for file path
        if isinstance(audio, (str, Path)):
            path = Path(audio)
            if not path.is_file():
                logger.warning(f"Audio file not found: {path}")
                return None
            ext = path.suffix.lower()
            mime = "audio/wav" if ext == ".wav" else "audio/mpeg" if ext in (".mp3", ".mp4") else "audio/octet-stream"
            with open(path, "rb") as f:
                data = f.read()
            if len(data) == 0:
                return None
            return data, path.name, mime

        logger.warning(f"Unsupported audio input type: {type(audio)}")
        return None

    def transcribe(
        self,
        audio: Union[bytes, str, Path, io.BytesIO, Any],
        language: Optional[str] = None,
        mode: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[STTResult]:
        """
        Transcribes audio using Sarvam Saaras API with bounded backoff retries.
        Returns normalized STTResult or None on failure/silence.
        """
        if not self.is_available():
            logger.warning("Sarvam STT requested but API key is missing.")
            return None

        audio_info = self._extract_audio_bytes(audio)
        if not audio_info:
            logger.warning("Invalid or empty audio provided to Sarvam STT.")
            return None

        audio_bytes, filename, mime_type = audio_info
        target_model = (model or self.model).strip()
        target_mode = (mode or self.mode).strip().lower()
        target_lang = (language or self.language).strip()

        form_fields = {
            "model": target_model,
            "mode": target_mode,
        }
        if target_lang:
            form_fields["language_code"] = target_lang

        payload_bytes, content_type_header = self._build_multipart_payload(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=mime_type,
            form_fields=form_fields,
        )

        endpoint = f"{self.base_url}/speech-to-text"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": content_type_header,
            "User-Agent": "DAKU-Voice-Agent/5.0",
        }

        retries = 0
        while retries <= self.max_retries:
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=payload_bytes,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    status_code = getattr(resp, "status", 200)
                    if status_code == 200:
                        body_raw = resp.read().decode("utf-8")
                        data = json.loads(body_raw)

                        transcript = data.get("transcript", "").strip()
                        if not transcript:
                            logger.info("Sarvam STT returned empty transcript.")
                            return None

                        req_id = data.get("request_id") or f"sarvam-{uuid.uuid4().hex[:12]}"
                        detected_lang = data.get("language_code") or target_lang or "hi-IN"

                        return STTResult(
                            text=transcript,
                            language=detected_lang,
                            provider="sarvam",
                            model=target_model,
                            request_id=req_id,
                            latency_ms=latency_ms,
                            metadata={"mode": target_mode, "status_code": status_code},
                        )
                    return None

            except urllib.error.HTTPError as e:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                status_code = e.code
                logger.warning(
                    f"Sarvam STT HTTP error {status_code} (attempt {retries + 1}/{self.max_retries + 1})"
                )

                if status_code in self.NON_RETRY_STATUSES:
                    # Non-retryable error (e.g. 401 Unauthorized, 403 Forbidden, 422 Unprocessable)
                    logger.error(f"Sarvam STT received non-retryable error {status_code}. Aborting.")
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
                    f"Sarvam STT network/timeout error: {e} (attempt {retries + 1}/{self.max_retries + 1})"
                )
                if retries < self.max_retries:
                    sleep_time = self.backoff_factor * (2**retries)
                    time.sleep(sleep_time)
                    retries += 1
                    continue
                return None

            except Exception as e:
                logger.error(f"Unexpected error in Sarvam STT: {e}")
                return None

        return None
