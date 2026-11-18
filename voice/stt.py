"""
DAKU Speech-To-Text (STT) Module
Phase 1.5: Push-to-Talk Real Microphone Speech Input with TextFallbackSTT.
Optimized for ultra-low memory & CPU on Windows 11.
"""

import sys
from typing import Optional


class BaseSTT:
    """Base interface for Speech-To-Text providers."""
    def listen_and_transcribe(self, prompt_text: str = "Listening...") -> Optional[str]:
        raise NotImplementedError


class TextFallbackSTT(BaseSTT):
    """
    Console text input fallback.
    Guarantees DAKU works 100% reliably even without a microphone, audio driver, or internet.
    """

    def listen_and_transcribe(self, prompt_text: str = "Enter your command") -> Optional[str]:
        try:
            print(f"\n[DAKU] {prompt_text}")
            user_input = input("You: ").strip()
            if not user_input:
                return None
            return user_input
        except (EOFError, KeyboardInterrupt):
            print("\n[DAKU] Exiting.")
            return None


class MicrophoneSTT(BaseSTT):
    """
    Push-to-Talk Microphone Speech-To-Text provider using SpeechRecognition.
    Sends captured audio to Google Web STT API endpoint (0 local model RAM).
    Gracefully handles hardware absence, permission errors, silence, and network faults.
    """

    def __init__(self, language: str = "en-IN"):
        self.language = language

    def is_available(self) -> bool:
        """Checks if speech_recognition, PyAudio, and at least one recording device are present."""
        try:
            import speech_recognition as sr
            mics = sr.Microphone.list_microphone_names()
            return bool(mics and len(mics) > 0)
        except Exception:
            return False

    def listen_and_transcribe(self, prompt_text: str = "Listening (speak now)...") -> Optional[str]:
        """
        Listens via system default microphone for a single push-to-talk utterance.
        Returns transcribed text string or None on failure.
        """
        try:
            import speech_recognition as sr
        except ImportError:
            print("[DAKU] speech_recognition library is not installed.")
            return None

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                print(f"\n[DAKU] {prompt_text}")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

            # Transcribe via lightweight cloud STT endpoint
            text = recognizer.recognize_google(audio, language=self.language)
            if not text or not str(text).strip():
                print("[DAKU] No speech detected.")
                return None

            clean_text = str(text).strip()
            print(f"You (Voice): {clean_text}")
            return clean_text

        except sr.WaitTimeoutError:
            print("[DAKU] No speech detected (timed out).")
            return None
        except sr.UnknownValueError:
            print("[DAKU] Could not understand audio (unclear speech).")
            return None
        except sr.RequestError as e:
            print(f"[DAKU] STT Network error: {e}")
            return None
        except PermissionError:
            print("[DAKU] Microphone permission denied. Check Windows Settings -> Privacy -> Microphone.")
            return None
        except (OSError, IOError, AttributeError) as e:
            print(f"[DAKU] Microphone hardware error: {e}")
            return None
        except Exception as e:
            print(f"[DAKU STT Error] {e}")
            return None


# Backward-compatible alias
CloudSTT = MicrophoneSTT


class SpeechToTextEngine:
    """STT manager routing to active STT engine with bulletproof automatic fallback."""

    def __init__(self, provider: str = "mic", language: str = "en-IN"):
        self.provider = provider
        self.language = language
        self.text_fallback = TextFallbackSTT()
        self.mic_stt = MicrophoneSTT(language=language)
        self.cloud_stt = self.mic_stt  # backward compat alias

    def listen(self, prompt_text: str = "Listening...") -> Optional[str]:
        """Captures input via active provider, automatically falling back to text console if needed."""
        if self.provider in ("mic", "cloud_stt", "google", "google_stt"):
            if not self.mic_stt.is_available():
                print("[DAKU] Voice input unavailable. Type your command instead.")
                return self.text_fallback.listen_and_transcribe(prompt_text="Enter your command")

            result = self.mic_stt.listen_and_transcribe(prompt_text)
            if result:
                return result

            # If microphone failed to capture or transcribe, offer immediate text input fallback
            print("[DAKU] Voice input unavailable. Type your command instead.")
            return self.text_fallback.listen_and_transcribe(prompt_text="Enter your command")

        # Default text fallback provider
        return self.text_fallback.listen_and_transcribe(prompt_text)
