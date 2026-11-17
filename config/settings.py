"""
DAKU Configuration & Settings Module
Loads configuration from .env or environment variables with safe defaults.
Zero external dependencies required.
"""

import os
from pathlib import Path
from typing import Optional


def _load_env_file(env_path: Path) -> None:
    """Minimal .env file loader using standard library only."""
    if not env_path.is_file():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


class Settings:
    """Application settings with secure defaults."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.BASE_DIR = base_dir or Path(__file__).resolve().parent.parent
        _load_env_file(self.BASE_DIR / ".env")

        # Runtime mode
        self.DAKU_MODE: str = os.getenv("DAKU_MODE", "cloud-lightweight")
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.AGENT_BACKEND: str = os.getenv("AGENT_BACKEND", "direct").strip().lower()  # direct | harness | uncensored

        # Model / Brain settings
        self.MODEL_PROVIDER: str = os.getenv("MODEL_PROVIDER", "deepseek")
        self.MODEL_NAME: str = os.getenv("MODEL_NAME", "deepseek-chat")
        self.MODEL_BASE_URL: str = os.getenv("MODEL_BASE_URL", "https://api.deepseek.com/v1")
        self.MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")
        self.MODEL_TIMEOUT_SECONDS: float = float(os.getenv("MODEL_TIMEOUT_SECONDS", "15.0"))

        # DeepSeek Harness settings (orchestration mode)
        self.DEEPSEEK_HARNESS_URL: str = os.getenv("DEEPSEEK_HARNESS_URL", os.getenv("HARNESS_ENDPOINT", self.MODEL_BASE_URL)).rstrip("/")
        self.HARNESS_ENDPOINT: str = self.DEEPSEEK_HARNESS_URL
        self.HARNESS_API_KEY: str = os.getenv("HARNESS_API_KEY", self.MODEL_API_KEY)
        self.HARNESS_MODEL_NAME: str = os.getenv("HARNESS_MODEL_NAME", self.MODEL_NAME)

        # Uncensored R1 Remote Backend settings
        self.UNCENSORED_BASE_URL: str = os.getenv("UNCENSORED_BASE_URL", "https://api.deepseek.com/v1")
        self.UNCENSORED_API_KEY: str = os.getenv("UNCENSORED_API_KEY", self.MODEL_API_KEY)
        self.UNCENSORED_MODEL_NAME: str = os.getenv("UNCENSORED_MODEL_NAME", "deepseek-r1-distill-7b")

        # Voice settings
        self.STT_PROVIDER: str = os.getenv("STT_PROVIDER", os.getenv("DAKU_STT_PROVIDER", "mic"))  # mic | sarvam | cloud_stt | text_fallback
        self.STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "en-IN")
        self.TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", os.getenv("DAKU_TTS_PROVIDER", "windows_native"))  # windows_native | sarvam | edge_tts
        self.TTS_VOICE_NAME: str = os.getenv("TTS_VOICE_NAME", "Microsoft David Desktop")
        self.TTS_RATE: int = int(os.getenv("TTS_RATE", "0"))  # -10 to +10 for SAPI

        # Sarvam Voice Settings
        self.SARVAM_API_KEY: str = os.getenv("SARVAM_API_KEY", "").strip()
        self.SARVAM_BASE_URL: str = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/")
        self.SARVAM_STT_MODEL: str = os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip()
        self.SARVAM_STT_MODE: str = os.getenv("SARVAM_STT_MODE", "transcribe").strip().lower()
        self.SARVAM_LANGUAGE: str = os.getenv("SARVAM_LANGUAGE", "hi-IN").strip()
        self.SARVAM_TTS_MODEL: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()
        self.SARVAM_TTS_SPEAKER: str = os.getenv("SARVAM_TTS_SPEAKER", "shubh").strip().lower()
        self.SARVAM_TTS_PACE: float = float(os.getenv("SARVAM_TTS_PACE", "1.0"))
        self.SARVAM_TTS_TEMPERATURE: float = float(os.getenv("SARVAM_TTS_TEMPERATURE", "0.6"))
        self.SARVAM_LLM_MODEL: str = os.getenv("SARVAM_LLM_MODEL", "sarvam-105b-conversations").strip()
        self.DAKU_STT_PROVIDER: str = os.getenv("DAKU_STT_PROVIDER", self.STT_PROVIDER)
        self.DAKU_TTS_PROVIDER: str = os.getenv("DAKU_TTS_PROVIDER", self.TTS_PROVIDER)
        self.DAKU_VOICE_STORE_AUDIO: bool = os.getenv("DAKU_VOICE_STORE_AUDIO", "false").strip().lower() == "true"
        self.DAKU_VOICE_STORE_TRANSCRIPTS: bool = os.getenv("DAKU_VOICE_STORE_TRANSCRIPTS", "false").strip().lower() == "true"

        # Server & Remote Client Settings
        self.DAKU_SERVER_HOST: str = os.getenv("DAKU_SERVER_HOST", "127.0.0.1")
        self.DAKU_SERVER_PORT: int = int(os.getenv("DAKU_SERVER_PORT", "8443"))
        self.DAKU_SERVER_URL: str = os.getenv("DAKU_SERVER_URL", "http://127.0.0.1:8443").rstrip("/")
        self.DAKU_AUTH_TOKEN: str = os.getenv("DAKU_AUTH_TOKEN", "")
        self.HERMES_GATEWAY_URL: str = os.getenv("HERMES_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")

        # Security & Confirmation
        self.REQUIRE_CONFIRMATION: bool = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"
        self.WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "false").lower() == "true"

        # Multi-Pass Reasoning & Bounded Computation
        self.MAX_PASSES: int = int(os.getenv("MAX_PASSES", "8"))
        self.MAX_ACTIVE_PASSES: int = int(os.getenv("MAX_ACTIVE_PASSES", "8"))
        self.MAX_LESSONS: int = int(os.getenv("MAX_LESSONS", "500"))
        self.MAX_RECENT_OBSERVATIONS: int = int(os.getenv("MAX_RECENT_OBSERVATIONS", "20"))
        self.MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))

    def has_api_key(self) -> bool:
        """Returns whether a valid API key is configured."""
        return bool(self.MODEL_API_KEY and self.MODEL_API_KEY.strip() and self.MODEL_API_KEY != "your_api_key_here")

    def has_auth_token(self) -> bool:
        """Returns whether a server authentication token is configured."""
        return bool(self.DAKU_AUTH_TOKEN and self.DAKU_AUTH_TOKEN.strip() and self.DAKU_AUTH_TOKEN != "your_secret_auth_token_here")

    def has_sarvam_key(self) -> bool:
        """Returns whether a valid Sarvam API key is configured."""
        return bool(self.SARVAM_API_KEY and self.SARVAM_API_KEY.strip() and self.SARVAM_API_KEY != "your_sarvam_api_key_here")

    def has_harness_url(self) -> bool:
        """Returns whether a DeepSeek Harness endpoint URL is configured."""
        return bool(self.DEEPSEEK_HARNESS_URL and self.DEEPSEEK_HARNESS_URL.strip())

    def is_https_url(self, url: Optional[str] = None) -> bool:
        """Checks if a given or configured server URL uses HTTPS protocol."""
        target = (url or self.DAKU_SERVER_URL or "").strip().lower()
        return target.startswith("https://")

    def is_loopback_url(self, url: Optional[str] = None) -> bool:
        """Checks if a given or configured server URL is a local loopback/private host."""
        import urllib.parse
        target = (url or self.DAKU_SERVER_URL or "").strip().lower()
        try:
            parsed = urllib.parse.urlparse(target)
            host = (parsed.hostname or "").lower()
            return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
        except Exception:
            return False


# Singleton instance
settings = Settings()
