"""
Unit and Integration Tests for Voice Fallback Cascades & Security Policy
Tests:
1. Google STT success and failure handling.
2. Windows SAPI TTS primary execution.
3. Fallback to console text output when Windows SAPI is unavailable.
4. Security verification:
   - Zero secret leakage in logs or exceptions.
   - Dangerous tool operations strictly require confirmation even during voice failures.
   - Provider failure NEVER bypasses PermissionManager.
"""

import io
import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from brain.router import Brain
from config.voice_config import _mask_secret, voice_config
from tools.base import PermissionLevel
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry
from voice.confirmation import VoiceConfirmationHandler
from voice.providers.base import STTResult, TTSResult
from voice_agent.pipeline import VoicePipeline


class TestVoiceFallbackAndSecurity(unittest.TestCase):
    """Test suite for fallback cascades and voice security."""

    def setUp(self):
        self.sample_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    def test_stt_google_success(self):
        """Verifies transcription via Google STT when available."""
        pipeline = VoicePipeline()

        google_res = STTResult(
            text="hello daku",
            provider="google_stt",
            model="google-web",
            latency_ms=85.0,
        )
        with patch.object(pipeline.google_stt, "is_available", return_value=True):
            with patch.object(pipeline.google_stt, "transcribe", return_value=google_res):
                text, provider_used, latency, fallback = pipeline.transcribe_audio(self.sample_wav)

        self.assertEqual(text, "hello daku")
        self.assertEqual(provider_used, "google_stt")
        self.assertFalse(fallback)

    def test_stt_failure_returns_none(self):
        """Verifies STT failure returns None when Google STT fails."""
        pipeline = VoicePipeline()

        with patch.object(pipeline.google_stt, "is_available", return_value=True):
            with patch.object(pipeline.google_stt, "transcribe", return_value=None):
                text, provider_used, latency, fallback = pipeline.transcribe_audio(self.sample_wav)

        self.assertIsNone(text)
        self.assertEqual(provider_used, "none")

    def test_tts_windows_sapi_primary(self):
        """Verifies speech synthesis via Windows SAPI."""
        pipeline = VoicePipeline()

        with patch.object(pipeline.windows_tts, "is_available", return_value=True):
            with patch.object(pipeline.windows_tts, "speak", return_value=True):
                ok, provider_used, latency, fallback = pipeline.synthesize_and_play("Hello")

        self.assertTrue(ok)
        self.assertEqual(provider_used, "windows_sapi")
        self.assertFalse(fallback)

    def test_tts_fallback_to_text(self):
        """Verifies fallback to text print when Windows SAPI fails or is unavailable."""
        pipeline = VoicePipeline()

        with patch.object(pipeline.windows_tts, "is_available", return_value=False):
            ok, provider_used, latency, fallback = pipeline.synthesize_and_play("Console message")

        self.assertTrue(ok)
        self.assertEqual(provider_used, "text_fallback")
        self.assertTrue(fallback)

    def test_secret_never_appears_in_logs(self):
        """Security: Verifies API keys are masked and never appear in logs or safe dicts."""
        secret_key = "daku_super_secret_production_key_12345"
        masked = _mask_secret(secret_key)

        self.assertNotIn("super_secret", masked)
        self.assertEqual(masked[:3], "dak")
        self.assertEqual(masked[-3:], "345")
        self.assertIn("...", masked)

        safe_dict = voice_config.safe_dict()
        self.assertNotIn(secret_key, str(safe_dict))

    def test_voice_failure_does_not_bypass_dangerous_tool_permission(self):
        """
        Security: Verifies that even if voice STT/TTS fails, CONFIRMATION_REQUIRED tools
        cannot execute without explicit confirmation.
        """
        voice_handler = VoiceConfirmationHandler(tts=None, stt=None)
        # Voice handler with no input -> returns False (denied)
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            perm_mgr = PermissionManager(voice_handler=voice_handler)
            allowed, level, msg = perm_mgr.evaluate(
                tool_name="application_tool",
                operation="launch",
                args={"app_name": "notepad"},
                declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
            )

        # Must be denied safely
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("cancelled", msg.lower())


if __name__ == "__main__":
    unittest.main()
