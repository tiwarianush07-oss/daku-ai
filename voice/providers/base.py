"""
DAKU Voice Provider Abstractions
Defines standardized interfaces and data models for interchangeable
Speech-To-Text (STT) and Text-To-Speech (TTS) providers.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union
import io
from pathlib import Path
import time


@dataclass
class STTResult:
    """Normalized Speech-To-Text transcription result."""
    text: str
    language: str = "en-IN"
    provider: str = "unknown"
    model: str = "unknown"
    request_id: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts to normalized dictionary format required by DAKU."""
        return {
            "text": self.text,
            "language": self.language,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class TTSResult:
    """Normalized Text-To-Speech synthesis result."""
    audio_bytes: bytes = b""
    audio_base64: str = ""
    format: str = "wav"
    sample_rate: int = 24000
    provider: str = "unknown"
    model: str = "unknown"
    speaker: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation without raw byte payload."""
        return {
            "audio_size_bytes": len(self.audio_bytes),
            "format": self.format,
            "sample_rate": self.sample_rate,
            "provider": self.provider,
            "model": self.model,
            "speaker": self.speaker,
            "latency_ms": round(self.latency_ms, 2),
        }


class STTProvider(ABC):
    """Abstract base class for all Speech-To-Text providers."""

    @abstractmethod
    def transcribe(
        self,
        audio: Union[bytes, str, Path, io.BytesIO, Any],
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[STTResult]:
        """
        Transcribes audio data into a normalized STTResult.
        Returns STTResult on success, or None on empty/silence/failure.
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider dependencies and hardware/credentials are available."""
        return True

    def get_provider_name(self) -> str:
        """Returns human-readable name of provider."""
        return self.__class__.__name__


class TTSProvider(ABC):
    """Abstract base class for all Text-To-Speech providers."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[TTSResult]:
        """
        Synthesizes text into audio, returning a normalized TTSResult.
        Returns TTSResult on success or None on failure.
        """
        raise NotImplementedError

    @abstractmethod
    def speak(self, text: str, **kwargs: Any) -> bool:
        """
        Speaks the given text directly to the system audio output device.
        Returns True on success, False on failure.
        """
        raise NotImplementedError

    def list_voices(self) -> List[str]:
        """Returns list of available speaker voice names."""
        return []

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if provider is ready to synthesize speech."""
        return True

    def get_provider_name(self) -> str:
        """Returns human-readable name of provider."""
        return self.__class__.__name__
