"""
Windows Native SAPI TTS Provider Adapter for DAKU
Uses Windows System.Speech.Synthesis and SAPI.SpVoice.
0 MB additional RAM, 100% offline, zero external dependencies.
Part of DAKU's resilient multi-tier fallback architecture.
"""

import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any, List, Optional

from voice.providers.base import TTSProvider, TTSResult

logger = logging.getLogger("daku.voice.windows_tts")


class WindowsSapiTTSProvider(TTSProvider):
    """
    Native Windows TTS provider implementing TTSProvider interface.
    Serves as the zero-RAM, 100% offline fallback when Sarvam Bulbul is unavailable.
    """

    def __init__(self, voice_name: Optional[str] = None, rate: int = 0):
        self.voice_name = voice_name
        self.rate = max(-10, min(10, rate))

    def is_available(self) -> bool:
        """Available on Windows OS."""
        return platform.system() == "Windows"

    def get_provider_name(self) -> str:
        return "windows_sapi"

    def list_voices(self) -> List[str]:
        """List all installed Windows SAPI voices."""
        if not self.is_available():
            return []
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
                voices = [v.strip() for v in res.stdout.strip().splitlines() if v.strip()]
                if voices:
                    return voices
        except Exception:
            pass
        return ["Microsoft David Desktop", "Microsoft Zira Desktop"]

    def speak(self, text: str, **kwargs: Any) -> bool:
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
            logger.warning(f"Windows Native TTS speak failed: {e}")
            return False

    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[TTSResult]:
        """
        Synthesizes text to WAV audio using Windows System.Speech.SetOutputToWaveFile.
        """
        clean_text = text.replace("'", "''").replace("`", "``").replace('"', '`"').replace("\n", " ").strip()
        if not clean_text:
            return TTSResult(
                audio_bytes=b"",
                format="wav",
                provider="windows_sapi",
                model="sapi5",
                speaker=self.voice_name or "default",
                latency_ms=0.0,
            )

        t0 = time.perf_counter()
        # Create temp file for WAV export
        fd, temp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        voice_target = speaker or self.voice_name
        voice_script = f"$synth.SelectVoice('{voice_target}'); " if voice_target else ""
        wav_escaped = temp_wav.replace("'", "''")

        ps_code = (
            f"[System.Reflection.Assembly]::LoadWithPartialName('System.Speech') | Out-Null; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Rate = {self.rate}; "
            f"{voice_script}"
            f"$synth.SetOutputToWaveFile('{wav_escaped}'); "
            f"$synth.Speak('{clean_text}'); "
            f"$synth.Dispose();"
        )

        try:
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code], capture_output=True, text=True, timeout=20)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            if res.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 0:
                with open(temp_wav, "rb") as f:
                    audio_data = f.read()
                return TTSResult(
                    audio_bytes=audio_data,
                    format="wav",
                    sample_rate=22050,
                    provider="windows_sapi",
                    model="sapi5",
                    speaker=voice_target or "Microsoft SAPI",
                    latency_ms=latency_ms,
                )
        except Exception as e:
            logger.warning(f"Windows SAPI synthesize failed: {e}")
        finally:
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

        return None
