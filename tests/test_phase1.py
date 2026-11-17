"""
DAKU Automated Test Suite for Phase 1 (Voice MVP)
Verifies:
- TEST 1: Modular imports & package resolution.
- TEST 2: System Doctor diagnostics execution.
- TEST 3: Text fallback STT without API key or microphone.
- TEST 4: Windows Native TTS initialization and voice synthesis.
- TEST 5: Cloud brain / router offline fallback & message processing.
- TEST 6: Full end-to-end pipeline (Text -> Brain -> TTS).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.backend import AgentBackend
from brain.router import Brain, DirectModelRouter
from config.settings import settings
from doctor import run_doctor
from voice.stt import SpeechToTextEngine, TextFallbackSTT
from voice.tts import TextToSpeechEngine, WindowsNativeTTS


class TestDakuPhase1(unittest.TestCase):

    def test_01_imports_and_interfaces(self):
        """TEST 1: Verify all core classes and interfaces import successfully."""
        self.assertTrue(issubclass(DirectModelRouter, AgentBackend))
        self.assertIsNotNone(settings)
        self.assertEqual(settings.DAKU_MODE, "cloud-lightweight")

    def test_02_doctor_diagnostics(self):
        """TEST 2: Verify DAKU Doctor runs and passes diagnostic checks."""
        result = run_doctor()
        self.assertTrue(result, "DAKU Doctor diagnostics failed.")

    def test_03_text_fallback_stt(self):
        """TEST 3: Verify TextFallbackSTT captures simulated user input correctly."""
        stt = TextFallbackSTT()
        with patch("builtins.input", return_value="Hello DAKU"):
            transcribed = stt.listen_and_transcribe()
            self.assertEqual(transcribed, "Hello DAKU")

    def test_04_windows_tts_synthesis(self):
        """TEST 4: Verify Windows Native TTS lists voices and generates speech without crashing."""
        tts = WindowsNativeTTS()
        voices = tts.list_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0, "No Windows SAPI voices discovered.")
        
        # Test speaking short phrase (smoke test)
        ok = tts.speak("DAKU voice initialized.")
        self.assertTrue(ok, "Windows TTS failed to speak.")

    def test_05_brain_offline_and_mock(self):
        """TEST 5: Verify Brain produces expected responses in offline mode without crashing."""
        brain = Brain(backend=DirectModelRouter(api_key=""))
        
        # Test greeting
        reply1 = brain.think("Hello DAKU")
        self.assertEqual(reply1, "Hello. I'm DAKU. How can I help?")

        # Test Hindi / Hinglish greeting
        reply2 = brain.think("DAKU kaise ho")
        self.assertIn("Main badhiya hoon", reply2)

        # Test generic offline fallback message
        reply3 = brain.think("What is the weather today?")
        self.assertIn("DAKU is running in offline demo mode", reply3)

    def test_06_full_pipeline_end_to_end(self):
        """TEST 6: Full end-to-end pipeline: Input -> Brain Reasoning -> Spoken TTS Output."""
        stt = SpeechToTextEngine(provider="text_fallback")
        brain = Brain(backend=DirectModelRouter(api_key=""))
        tts = TextToSpeechEngine(provider="windows_native")

        with patch("builtins.input", return_value="Hello DAKU"):
            user_input = stt.listen()
            self.assertEqual(user_input, "Hello DAKU")

            response = brain.think(user_input)
            self.assertEqual(response, "Hello. I'm DAKU. How can I help?")

            spoken = tts.speak(response)
            self.assertTrue(spoken, "Pipeline failed at TTS speech output.")


if __name__ == "__main__":
    unittest.main()
