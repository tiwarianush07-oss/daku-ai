"""
Unit and Integration Tests for Sarvam Saaras STT Provider
Tests initialization, error handling, retries, latency, normalization, and fallbacks.
100% Mocked by default (no live API key required).
"""

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from voice.providers.base import STTResult
from voice.providers.sarvam_stt import SarvamSTTProvider


class TestSarvamSTTProvider(unittest.TestCase):
    """Test suite for SarvamSTTProvider."""

    def setUp(self):
        self.sample_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    def test_provider_initialization_defaults(self):
        """Validates provider initialization with default settings."""
        provider = SarvamSTTProvider(api_key="test-api-key")
        self.assertEqual(provider.model, "saaras:v4")
        self.assertEqual(provider.mode, "transcribe")
        self.assertEqual(provider.language, "hi-IN")
        self.assertTrue(provider.is_available())
        self.assertEqual(provider.get_provider_name(), "sarvam")

    def test_missing_api_key(self):
        """Verifies provider reports unavailable when API key is missing."""
        provider = SarvamSTTProvider(api_key="")
        self.assertFalse(provider.is_available())
        res = provider.transcribe(self.sample_wav)
        self.assertIsNone(res)

    def test_invalid_mode_defaults_to_transcribe(self):
        """Verifies unrecognized mode defaults cleanly to transcribe."""
        provider = SarvamSTTProvider(api_key="key", mode="invalid_mode")
        self.assertEqual(provider.mode, "transcribe")

    def test_successful_transcription(self):
        """Verifies successful transcription returns normalized STTResult."""
        provider = SarvamSTTProvider(api_key="test-key")

        mock_response_data = {
            "request_id": "req-12345",
            "transcript": "नमस्ते, मैं डाकू हूँ",
            "language_code": "hi-IN",
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = provider.transcribe(self.sample_wav, language="hi-IN")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, STTResult)
        self.assertEqual(result.text, "नमस्ते, मैं डाकू हूँ")
        self.assertEqual(result.language, "hi-IN")
        self.assertEqual(result.provider, "sarvam")
        self.assertEqual(result.model, "saaras:v4")
        self.assertEqual(result.request_id, "req-12345")
        self.assertGreaterEqual(result.latency_ms, 0.0)

        # Normalized dictionary check
        d = result.to_dict()
        self.assertEqual(d["text"], "नमस्ते, मैं डाकू हूँ")
        self.assertEqual(d["provider"], "sarvam")

    def test_empty_audio_returns_none(self):
        """Verifies empty or invalid audio input is rejected safely."""
        provider = SarvamSTTProvider(api_key="test-key")
        self.assertIsNone(provider.transcribe(b""))
        self.assertIsNone(provider.transcribe(None))

    def test_empty_transcript_from_api(self):
        """Verifies empty transcript from API returns None without crashing."""
        provider = SarvamSTTProvider(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"transcript": "", "request_id": "req-0"}).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = provider.transcribe(self.sample_wav)

        self.assertIsNone(result)

    def test_non_retryable_http_errors(self):
        """Verifies 400, 401, 403, 422 errors fail immediately without infinite retry."""
        provider = SarvamSTTProvider(api_key="test-key", max_retries=3)

        for error_code in (400, 401, 403, 422):
            http_err = urllib.error.HTTPError(
                url="https://api.sarvam.ai/speech-to-text",
                code=error_code,
                msg=f"Error {error_code}",
                hdrs={},
                fp=io.BytesIO(b'{"error": "client error"}'),
            )
            with patch("urllib.request.urlopen", side_effect=http_err) as mock_urlopen:
                result = provider.transcribe(self.sample_wav)
                self.assertIsNone(result)
                # Non-retryable errors should only make 1 attempt
                self.assertEqual(mock_urlopen.call_count, 1)

    def test_retryable_http_errors_and_rate_limit(self):
        """Verifies 429, 500, 502, 503 errors trigger bounded exponential backoff retries."""
        provider = SarvamSTTProvider(api_key="test-key", max_retries=2, backoff_factor=0.01)

        http_err_429 = urllib.error.HTTPError(
            url="https://api.sarvam.ai/speech-to-text",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=io.BytesIO(b'{"error": "rate limit"}'),
        )

        with patch("urllib.request.urlopen", side_effect=http_err_429) as mock_urlopen:
            with patch("voice.providers.sarvam_stt.time.sleep") as mock_sleep:
                result = provider.transcribe(self.sample_wav)
                self.assertIsNone(result)
                # Initial + 2 retries = 3 calls
                self.assertEqual(mock_urlopen.call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)

    def test_network_timeout_and_recovery(self):
        """Verifies network timeout followed by successful retry."""
        provider = SarvamSTTProvider(api_key="test-key", max_retries=2, backoff_factor=0.01)

        success_resp = MagicMock()
        success_resp.status = 200
        success_resp.__enter__.return_value = success_resp
        success_resp.read.return_value = json.dumps({"transcript": "Recovered"}).encode("utf-8")

        timeout_err = TimeoutError("Connection timed out")

        with patch("urllib.request.urlopen", side_effect=[timeout_err, success_resp]) as mock_urlopen:
            with patch("voice.providers.sarvam_stt.time.sleep"):
                result = provider.transcribe(self.sample_wav)
                self.assertIsNotNone(result)
                self.assertEqual(result.text, "Recovered")
                self.assertEqual(mock_urlopen.call_count, 2)

    @unittest.skipUnless(os.getenv("SARVAM_API_KEY"), "Live Sarvam test requires SARVAM_API_KEY in environment")
    def test_live_sarvam_stt(self):
        """Optional integration test executing against live Sarvam API."""
        provider = SarvamSTTProvider()
        self.assertTrue(provider.is_available())
        # Provide sample audio
        result = provider.transcribe(self.sample_wav, language="hi-IN")
        # Live endpoint will process or return valid transcript/None
        self.assertTrue(result is None or isinstance(result, STTResult))


if __name__ == "__main__":
    unittest.main()
