"""
Unit and Integration Tests for DAKU Voice Pipeline & TTS Normalizer
Tests end-to-end turn processing: Audio -> STT -> Brain -> Tools -> Verifier -> Normalizer -> TTS.
Validates latency metrics, privacy compliance, and Indic script preservation.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from brain.router import Brain
from tools.base import ToolResult
from tools.registry import ToolRegistry
from voice.audio import save_audio_safely
from voice.providers.base import STTResult, TTSResult
from voice_agent.normalizer import TTSNormalizer
from voice_agent.pipeline import VoicePipeline
from voice_agent.turn_manager import TurnState, VoiceTurnManager


class TestTTSNormalizer(unittest.TestCase):
    """Test suite for TTSNormalizer speech preprocessing."""

    def test_strip_think_reasoning_tags(self):
        """Verifies <think> tags from reasoning models are completely stripped."""
        text = "<think>Let me calculate the memory free on Windows</think>Your RAM has 1.2 GB free."
        clean = TTSNormalizer.clean_for_speech(text)
        self.assertNotIn("<think>", clean)
        self.assertNotIn("calculate the memory", clean)
        self.assertIn("Your RAM has 1.2 GB free.", clean)

    def test_strip_json_and_tool_metadata(self):
        """Verifies JSON payloads and internal dictionaries are removed."""
        text = '{"success": true, "verified": true} Opened notepad successfully.'
        clean = TTSNormalizer.clean_for_speech(text)
        self.assertNotIn('{"success"', clean)
        self.assertIn("Opened notepad successfully.", clean)

    def test_strip_system_prefixes_and_debug(self):
        """Verifies [DAKU (0.15s)] debug prefixes are cleaned."""
        text = "[DAKU (0.24s)]: I launched Chrome for you."
        clean = TTSNormalizer.clean_for_speech(text)
        self.assertNotIn("[DAKU", clean)
        self.assertIn("I launched Chrome for you.", clean)

    def test_url_normalization(self):
        """Verifies URLs are converted to natural spoken representations."""
        text = "Navigated to https://www.google.com and found the page."
        clean = TTSNormalizer.clean_for_speech(text)
        self.assertNotIn("https://", clean)
        self.assertIn("google dot com", clean)

    def test_ip_address_normalization(self):
        """Verifies IP addresses are spoken with 'point' instead of raw dots."""
        text = "Server is running at 127.0.0.1 on port 8443."
        clean = TTSNormalizer.clean_for_speech(text)
        self.assertIn("127 point 0 point 0 point 1", clean)

    def test_preserve_english_technical_terms(self):
        """Verifies key English technical terms are strictly preserved in Latin script."""
        text = "Aapka RAM and CPU usage normal hai, Notepad open kar diya hai."
        clean = TTSNormalizer.clean_for_speech(text, target_lang="hi-IN")
        self.assertIn("RAM", clean)
        self.assertIn("CPU", clean)
        self.assertIn("Notepad", clean)

    def test_contextual_hinglish_to_devanagari(self):
        """Verifies Hinglish phrases map to clean Devanagari while preserving English nouns."""
        text = "Aapka order confirm ho gaya hai."
        clean = TTSNormalizer.clean_for_speech(text, target_lang="hi-IN")
        # Should contain Devanagari for common words and English for technical/order words
        self.assertIn("आपका", clean)
        self.assertIn("order", clean)
        self.assertIn("confirm", clean)
        self.assertIn("हो गया है", clean)

    def test_preserve_native_indic_script(self):
        """Verifies already-Devanagari text is preserved 100% without corrupting."""
        text = "आपका order confirm हो गया है।"
        clean = TTSNormalizer.clean_for_speech(text, target_lang="hi-IN")
        self.assertEqual(clean, "आपका order confirm हो गया है।")


class TestVoicePipeline(unittest.TestCase):
    """Test suite for full VoicePipeline execution and observability."""

    def setUp(self):
        self.sample_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    def test_end_to_end_pipeline_turn(self):
        """Verifies complete turn: audio -> STT -> Brain -> Tool -> Verifier -> Normalizer -> TTS."""
        registry = ToolRegistry()
        brain = Brain(tool_registry=registry)
        pipeline = VoicePipeline(brain=brain)

        # Mock STT
        mock_stt_res = STTResult(
            text="what time is it",
            language="en-IN",
            provider="google_stt",
            model="google-web",
            latency_ms=120.0,
        )

        with patch.object(pipeline.google_stt, "is_available", return_value=True):
            with patch.object(pipeline.google_stt, "transcribe", return_value=mock_stt_res):
                with patch.object(pipeline.windows_tts, "is_available", return_value=True):
                    with patch.object(pipeline.windows_tts, "speak", return_value=True):
                        metrics = pipeline.process_turn(audio_input=self.sample_wav)

        self.assertTrue(metrics.success)
        self.assertEqual(metrics.stt_provider, "google_stt")
        self.assertEqual(metrics.tts_provider, "windows_sapi")
        self.assertGreater(metrics.total_turn_latency_ms, 0.0)
        self.assertGreater(metrics.brain_latency_ms, 0.0)

        safe_dict = metrics.to_safe_dict()
        self.assertIn("session_id", safe_dict)
        self.assertIn("turn_id", safe_dict)
        self.assertNotIn("what time is it", str(safe_dict))  # Safe logging: transcripts excluded

    def test_privacy_audio_storage_policy(self):
        """Verifies audio is NEVER saved to disk when DAKU_VOICE_STORE_AUDIO is false."""
        test_file = "data/voice/temp_test.wav"
        if os.path.exists(test_file):
            os.remove(test_file)

        saved = save_audio_safely(b"sample-audio", test_file)
        self.assertFalse(saved)
        self.assertFalse(os.path.exists(test_file))


if __name__ == "__main__":
    unittest.main()
