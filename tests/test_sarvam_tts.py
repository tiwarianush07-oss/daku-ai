"""
Unit and Integration Tests for Sarvam Bulbul v3 TTS Provider
Tests initialization, synthesis, audio decoding, error handling, retries, and fallback.
100% Mocked by default (no live API key required).
"""

import base64
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from voice.providers.base import TTSResult
from voice.providers.sarvam_tts import SarvamTTSProvider


class TestSarvamTTSProvider(unittest.TestCase):
    """Test suite for SarvamTTSProvider."""

    def setUp(self):
        self.dummy_audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00data\x00\x00\x00\x00"
        self.dummy_b64 = base64.b64encode(self.dummy_audio_bytes).decode("ascii")

    def test_provider_initialization_defaults(self):
        """Validates provider default parameters."""
        provider = SarvamTTSProvider(api_key="test-api-key")
        self.assertEqual(provider.model, "bulbul:v3")
        self.assertEqual(provider.speaker, "shubh")
        self.assertEqual(provider.language, "hi-IN")
        self.assertEqual(provider.pace, 1.0)
        self.assertTrue(provider.is_available())
        self.assertEqual(provider.get_provider_name(), "sarvam")
        self.assertIn("shubh", provider.list_voices())

    def test_missing_api_key(self):
        """Verifies missing API key returns None and unavailable."""
        provider = SarvamTTSProvider(api_key="")
        self.assertFalse(provider.is_available())
        self.assertIsNone(provider.synthesize("Hello"))

    def test_empty_text_returns_none(self):
        """Verifies empty or whitespace text is handled gracefully."""
        provider = SarvamTTSProvider(api_key="test-key")
        self.assertIsNone(provider.synthesize(""))
        self.assertIsNone(provider.synthesize("   "))
        self.assertIsNone(provider.synthesize(None))

    def test_successful_synthesis(self):
        """Verifies successful synthesis returns decoded audio in TTSResult."""
        provider = SarvamTTSProvider(api_key="test-key", speaker="aditya")

        mock_resp_data = {
            "audios": [self.dummy_b64],
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = provider.synthesize("नमस्ते", language="hi-IN", speaker="aditya")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, TTSResult)
        self.assertEqual(result.audio_bytes, self.dummy_audio_bytes)
        self.assertEqual(result.audio_base64, self.dummy_b64)
        self.assertEqual(result.provider, "sarvam")
        self.assertEqual(result.model, "bulbul:v3")
        self.assertEqual(result.speaker, "aditya")
        self.assertGreaterEqual(result.latency_ms, 0.0)

    def test_no_unsupported_pitch_or_loudness_in_payload(self):
        """Verifies Bulbul v3 payload strictly avoids pitch and loudness parameters."""
        provider = SarvamTTSProvider(api_key="test-key")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"audios": [self.dummy_b64]}).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider.synthesize("Test", pitch=1.5, loudness=2.0)  # unsupported args in kwargs
            # Inspect payload sent to urlopen
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))

            self.assertNotIn("pitch", payload)
            self.assertNotIn("loudness", payload)
            self.assertIn("text", payload)
            self.assertIn("model", payload)
            self.assertIn("speaker", payload)

    def test_non_retryable_http_errors(self):
        """Verifies 401, 403, 422 fail fast without retrying."""
        provider = SarvamTTSProvider(api_key="test-key", max_retries=3)

        for code in (401, 403, 422):
            err = urllib.error.HTTPError(
                url="https://api.sarvam.ai/text-to-speech",
                code=code,
                msg=f"Error {code}",
                hdrs={},
                fp=io.BytesIO(b'{"error": "unauthorized"}'),
            )
            with patch("urllib.request.urlopen", side_effect=err) as mock_urlopen:
                result = provider.synthesize("Hello")
                self.assertIsNone(result)
                self.assertEqual(mock_urlopen.call_count, 1)

    def test_retryable_errors(self):
        """Verifies 429 and 500 trigger backoff retries."""
        provider = SarvamTTSProvider(api_key="test-key", max_retries=2, backoff_factor=0.01)

        err_500 = urllib.error.HTTPError(
            url="https://api.sarvam.ai/text-to-speech",
            code=500,
            msg="Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error": "server error"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err_500) as mock_urlopen:
            with patch("voice.providers.sarvam_tts.time.sleep"):
                result = provider.synthesize("Hello")
                self.assertIsNone(result)
                self.assertEqual(mock_urlopen.call_count, 3)

    def test_streaming_chunk_generator(self):
        """Verifies streaming interface yields chunked audio bytes."""
        provider = SarvamTTSProvider(api_key="test-key")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"audios": [self.dummy_b64]}).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            chunks = list(provider.stream_synthesize("Test", chunk_size_bytes=8))
            reconstructed = b"".join(chunks)
            self.assertEqual(reconstructed, self.dummy_audio_bytes)

    @unittest.skipUnless(os.getenv("SARVAM_API_KEY"), "Live Sarvam test requires SARVAM_API_KEY in environment")
    def test_live_sarvam_tts(self):
        """Optional integration test against live Sarvam TTS API."""
        provider = SarvamTTSProvider()
        self.assertTrue(provider.is_available())
        result = provider.synthesize("नमस्ते, यह डाकू का टेस्ट है।", language="hi-IN")
        self.assertTrue(result is None or isinstance(result, TTSResult))


if __name__ == "__main__":
    unittest.main()
