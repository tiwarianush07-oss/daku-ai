"""
DAKU Audio Management Module
Provides lightweight audio recording, WAV serialization, and system playback.
Employs standard library winsound on Windows for zero added RAM.
Strictly respects DAKU_VOICE_STORE_AUDIO privacy flag.
"""

import io
import logging
import os
import platform
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from config.voice_config import voice_config

logger = logging.getLogger("daku.voice.audio")


def play_audio_bytes(audio_bytes: bytes, format: str = "wav") -> bool:
    """
    Plays audio bytes directly through system audio output.
    On Windows, uses native winsound in memory (0 MB RAM, 0 disk I/O).
    """
    if not audio_bytes or len(audio_bytes) == 0:
        return False

    if platform.system() == "Windows":
        try:
            import winsound
            # SND_MEMORY plays WAV directly from bytes in RAM without writing to disk
            winsound.PlaySound(audio_bytes, winsound.SND_MEMORY)
            return True
        except Exception as e:
            logger.warning(f"winsound direct playback failed: {e}. Trying temp file...")

        # Secondary fallback on Windows: temporary file via winsound or powershell
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with open(temp_path, "wb") as f:
                f.write(audio_bytes)
            import winsound
            winsound.PlaySound(temp_path, winsound.SND_FILENAME)
            return True
        except Exception as e2:
            logger.warning(f"Windows temp file playback failed: {e2}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        return False

    # Linux / macOS fallback
    try:
        import subprocess
        # Check for paplay, aplay, or afplay
        for player in ("paplay", "aplay", "afplay"):
            if subprocess.run(["which", player], capture_output=True).returncode == 0:
                p = subprocess.Popen([player], stdin=subprocess.PIPE)
                p.communicate(input=audio_bytes, timeout=10)
                return p.returncode == 0
    except Exception as e:
        logger.warning(f"Linux/Unix audio playback failed: {e}")

    return False


def save_audio_safely(audio_bytes: bytes, filepath: Union[str, Path]) -> bool:
    """
    Saves audio to disk ONLY if DAKU_VOICE_STORE_AUDIO is explicitly enabled.
    Guarantees user voice privacy by default.
    """
    if not voice_config.DAKU_VOICE_STORE_AUDIO:
        logger.debug("Audio storage disabled by privacy policy (DAKU_VOICE_STORE_AUDIO=false).")
        return False

    try:
        dest = Path(filepath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"Safely stored voice recording to isolated path: {dest}")
        return True
    except Exception as e:
        logger.error(f"Failed to store audio: {e}")
        return False


def capture_mic_audio(
    timeout: float = 5.0,
    phrase_time_limit: float = 10.0,
) -> Optional[bytes]:
    """
    Captures a single speech utterance from system default microphone.
    Returns standard WAV audio bytes, or None on silence/timeout.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        logger.warning("speech_recognition library not installed.")
        return None

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = voice_config.VAD_ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone(sample_rate=voice_config.SAMPLE_RATE) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )
            return audio_data.get_wav_data()
    except sr.WaitTimeoutError:
        logger.debug("Microphone capture timed out (no speech detected).")
        return None
    except Exception as e:
        logger.warning(f"Microphone capture error: {e}")
        return None
