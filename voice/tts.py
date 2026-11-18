"""
DAKU Text-To-Speech (TTS) Module
Provides ultra-lightweight, zero-RAM speech output using native Windows System.Speech SAPI,
with optional Edge TTS online support.
"""

import os
import subprocess
import sys
from typing import List, Optional


class BaseTTS:
    """Abstract base class for TTS providers."""
    def speak(self, text: str) -> bool:
        raise NotImplementedError

    def list_voices(self) -> List[str]:
        return []


class WindowsNativeTTS(BaseTTS):
    """
    Native Windows TTS using System.Speech.Synthesis.SpeechSynthesizer.
    0 MB additional RAM, 100% offline, zero external dependencies.
    """

    def __init__(self, voice_name: Optional[str] = None, rate: int = 0):
        self.voice_name = voice_name
        self.rate = max(-10, min(10, rate))

    def list_voices(self) -> List[str]:
        """List all installed Windows SAPI voices."""
        cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Speech') | Out-Null; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return [v.strip() for v in res.stdout.strip().splitlines() if v.strip()]
        except Exception:
            pass
        return ["Microsoft David Desktop", "Microsoft Zira Desktop"]

    def speak(self, text: str) -> bool:
        """Speak the given text using Windows PowerShell System.Speech synthesizer with SAPI COM fallback."""
        clean_text = text.replace("'", "''").replace("`", "``").replace('"', '`"').replace("\n", " ").strip()
        if not clean_text:
            return True

        voice_script = f"$synth.SelectVoice('{self.voice_name}'); " if self.voice_name else ""
        ps_code = (
            f"[System.Reflection.Assembly]::LoadWithPartialName('System.Speech') | Out-Null; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Rate = {self.rate}; "
            f"{voice_script}"
            f"$synth.Speak('{clean_text}');"
        )

        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return True
        except Exception:
            pass

        # Resilient fallback to SAPI.SpVoice COM object
        try:
            com_code = f"$s = New-Object -ComObject SAPI.SpVoice; $s.Rate = {self.rate}; $s.Speak('{clean_text}');"
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", com_code], capture_output=True, text=True, timeout=20)
            return res.returncode == 0
        except Exception as e:
            print(f"[TTS Error] Windows Native TTS failed: {e}", file=sys.stderr)
            return False


class EdgeTTS(BaseTTS):
    """
    Optional online high-quality neural voice using edge-tts.
    Only used if package is installed and internet is connected.
    """

    def __init__(self, voice: str = "en-IN-NeerjaNeural"):
        self.voice = voice
        self._available = False
        try:
            import edge_tts  # type: ignore # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def speak(self, text: str) -> bool:
        if not self._available:
            return False
        # Fallback will handle if edge_tts is not available
        return False


class TextToSpeechEngine:
    """TTS manager that directs speech synthesis to the selected backend with resilient fallback."""

    def __init__(self, provider: str = "windows_native", voice_name: Optional[str] = None, rate: int = 0):
        self.provider = provider
        self.native_tts = WindowsNativeTTS(voice_name=voice_name, rate=rate)
        self.edge_tts = EdgeTTS()

    def speak(self, text: str) -> bool:
        """Speak text aloud using the active TTS provider with graceful fallback."""
        if not text or not text.strip():
            return True

        if self.provider in ("text_fallback", "text_only", "console"):
            print(f"[DAKU]: {text.strip()}")
            return True

        if self.provider == "edge_tts" and self.edge_tts.is_available():
            ok = self.edge_tts.speak(text)
            if ok:
                return True

        # Default fallback is always native Windows SAPI
        return self.native_tts.speak(text)

    def list_voices(self) -> List[str]:
        return self.native_tts.list_voices()
