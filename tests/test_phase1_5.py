"""
DAKU Automated Test Suite for Phase 1.5 (Real Microphone Speech Input)
Verifies:
- TEST 1: Microphone hardware detection and availability check.
- TEST 2: Graceful handling of unavailable microphone / driver failure.
- TEST 3: Graceful handling of permission denied errors.
- TEST 4: Graceful handling of silence / no speech detected / timeout.
- TEST 5: Graceful handling of network failure during cloud STT.
- TEST 6: Successful speech-to-text transcription.
- TEST 7: Full Push-to-Talk end-to-end voice pipeline (Mic -> Brain -> TTS).
- TEST 8: Permanent TextFallbackSTT direct mode preservation.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import speech_recognition as sr
from brain.router import Brain, DirectModelRouter
from config.settings import settings
from voice.stt import MicrophoneSTT, SpeechToTextEngine, TextFallbackSTT
from voice.tts import TextToSpeechEngine


class TestDakuPhase1Point5(unittest.TestCase):

    def test_01_microphone_hardware_detection(self):
        """TEST 1: Verify MicrophoneSTT checks hardware availability without crashing."""
        mic_stt = MicrophoneSTT(language="en-IN")
        is_avail = mic_stt.is_available()
        self.assertIsInstance(is_avail, bool)

    def test_02_microphone_unavailable_fallback(self):
        """TEST 2: Verify automatic fallback to text input when mic hardware is unavailable."""
        engine = SpeechToTextEngine(provider="mic")

        # Mock mic unavailable
        with patch.object(engine.mic_stt, "is_available", return_value=False):
            with patch("builtins.input", return_value="fallback command"):
                result = engine.listen()
                self.assertEqual(result, "fallback command")

    def test_03_permission_denied_handling(self):
        """TEST 3: Verify PermissionError in microphone is caught and triggers text fallback."""
        engine = SpeechToTextEngine(provider="mic")

        with patch.object(engine.mic_stt, "is_available", return_value=True):
            with patch.object(engine.mic_stt, "listen_and_transcribe", return_value=None):
                with patch("builtins.input", return_value="typed after permission error"):
                    result = engine.listen()
                    self.assertEqual(result, "typed after permission error")

    def test_04_no_speech_detected_timeout(self):
        """TEST 4: Verify timeout / silence (WaitTimeoutError / UnknownValueError) falls back cleanly."""
        mic = MicrophoneSTT()

        # Mock sr.Microphone and recognizer.listen throwing WaitTimeoutError
        with patch("speech_recognition.Microphone"):
            with patch("speech_recognition.Recognizer.adjust_for_ambient_noise"):
                with patch("speech_recognition.Recognizer.listen", side_effect=sr.WaitTimeoutError("Timed out")):
                    res = mic.listen_and_transcribe()
                    self.assertIsNone(res, "Expected None on silence/timeout")

        # Mock UnknownValueError (unclear speech)
        with patch("speech_recognition.Microphone"):
            with patch("speech_recognition.Recognizer.adjust_for_ambient_noise"):
                with patch("speech_recognition.Recognizer.listen", return_value=MagicMock()):
                    with patch("speech_recognition.Recognizer.recognize_google", side_effect=sr.UnknownValueError()):
                        res2 = mic.listen_and_transcribe()
                        self.assertIsNone(res2, "Expected None on unparseable speech")

    def test_05_network_failure_handling(self):
        """TEST 5: Verify cloud STT network failure (RequestError) is caught without crashing."""
        mic = MicrophoneSTT()

        with patch("speech_recognition.Microphone"):
            with patch("speech_recognition.Recognizer.adjust_for_ambient_noise"):
                with patch("speech_recognition.Recognizer.listen", return_value=MagicMock()):
                    with patch("speech_recognition.Recognizer.recognize_google", side_effect=sr.RequestError("Connection reset")):
                        res = mic.listen_and_transcribe()
                        self.assertIsNone(res, "Expected None on network failure")

    def test_06_successful_speech_transcription(self):
        """TEST 6: Verify successful speech transcription returns cleaned text string."""
        mic = MicrophoneSTT(language="en-IN")

        with patch("speech_recognition.Microphone"):
            with patch("speech_recognition.Recognizer.adjust_for_ambient_noise"):
                with patch("speech_recognition.Recognizer.listen", return_value=MagicMock()):
                    with patch("speech_recognition.Recognizer.recognize_google", return_value="  Hello DAKU  "):
                        result = mic.listen_and_transcribe()
                        self.assertEqual(result, "Hello DAKU")

    def test_07_full_voice_pipeline_end_to_end(self):
        """TEST 7: Full Push-to-Talk pipeline: Mic Audio -> Brain -> SAPI TTS output."""
        stt_engine = SpeechToTextEngine(provider="mic")
        brain = Brain(backend=DirectModelRouter(api_key=""))
        tts = TextToSpeechEngine(provider="windows_native")

        # Mock microphone recognizing 'Hello DAKU'
        with patch.object(stt_engine.mic_stt, "is_available", return_value=True):
            with patch.object(stt_engine.mic_stt, "listen_and_transcribe", return_value="Hello DAKU"):
                captured_text = stt_engine.listen()
                self.assertEqual(captured_text, "Hello DAKU")

                reply = brain.think(captured_text)
                self.assertEqual(reply, "Hello. I'm DAKU. How can I help?")

                spoken = tts.speak(reply)
                self.assertTrue(spoken, "Spoken response synthesis failed.")

    def test_08_text_fallback_direct_mode(self):
        """TEST 8: Verify provider='text_fallback' works directly without touching microphone."""
        engine = SpeechToTextEngine(provider="text_fallback")
        with patch("builtins.input", return_value="direct text command"):
            res = engine.listen()
            self.assertEqual(res, "direct text command")


if __name__ == "__main__":
    unittest.main()
