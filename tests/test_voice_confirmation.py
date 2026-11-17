"""
Unit and Integration Tests for DAKU Voice Confirmation (P0 Feature)
Tests Section 16 requirements:
- Spoken prompt: "I need permission to {action}. Should I continue?"
- User affirmative: "Yes" -> DAKU: "Confirmed." -> Returns True
- User negative: "No" -> DAKU: "Cancelled." -> Returns False
- User cancel/stop: "Cancel" / "Stop" -> DAKU: "Cancelled." -> Returns False
- Hindi / Hinglish tokens ("haan", "nahi", "ruko", etc.)
- Integration with PermissionManager, ToolRegistry, and DakuRemoteClient
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional

from tools.base import PermissionLevel, ToolResult
from tools.permissions import PermissionManager
from tools.registry import ToolRegistry
from voice.confirmation import (
    AFFIRMATIVE_TOKENS,
    CANCEL_STOP_TOKENS,
    NEGATIVE_TOKENS,
    VoiceConfirmationHandler,
)
from client import DakuRemoteClient


class MockTTS:
    """Mock Text-To-Speech engine recording spoken utterances."""

    def __init__(self):
        self.spoken_phrases: List[str] = []

    def speak(self, text: str) -> bool:
        self.spoken_phrases.append(text)
        return True


class MockSTT:
    """Mock Speech-To-Text engine returning predefined responses."""

    def __init__(self, responses: Optional[List[Optional[str]]] = None):
        self.responses: List[Optional[str]] = responses or []
        self.index: int = 0
        self.prompts: List[str] = []

    def listen(self, prompt_text: str = "") -> Optional[str]:
        self.prompts.append(prompt_text)
        if self.index < len(self.responses):
            res = self.responses[self.index]
            self.index += 1
            return res
        return None


class TestVoiceConfirmation(unittest.TestCase):
    """Test suite for VoiceConfirmationHandler and its integrations."""

    def setUp(self):
        self.mock_tts = MockTTS()

    # -------------------------------------------------------------------------
    # 1. Token Evaluation Unit Tests
    # -------------------------------------------------------------------------

    def test_affirmative_tokens(self):
        handler = VoiceConfirmationHandler(tts=self.mock_tts)
        for token in ["yes", "Yes", "YES", "y", "yeah", "yep", "sure", "proceed", "haan", "theek hai", "confirm", "authorized"]:
            with self.subTest(token=token):
                self.assertTrue(handler.evaluate_response(token), f"Token '{token}' should be affirmative")

    def test_negative_tokens(self):
        handler = VoiceConfirmationHandler(tts=self.mock_tts)
        for token in ["no", "No", "NO", "n", "nah", "nope", "nahi", "mat karo", "denied", "reject", "never"]:
            with self.subTest(token=token):
                self.assertFalse(handler.evaluate_response(token), f"Token '{token}' should be negative")

    def test_cancel_and_stop_tokens(self):
        handler = VoiceConfirmationHandler(tts=self.mock_tts)
        for token in ["cancel", "Cancel", "stop", "Stop", "STOP", "halt", "abort", "ruk", "roko", "chhod do", "quit", "exit"]:
            with self.subTest(token=token):
                self.assertFalse(handler.evaluate_response(token), f"Token '{token}' should be cancel/stop")

    def test_unrecognized_tokens(self):
        handler = VoiceConfirmationHandler(tts=self.mock_tts)
        for token in ["banana", "maybe", "what", "", None, "   "]:
            with self.subTest(token=token):
                self.assertIsNone(handler.evaluate_response(token), f"Token '{token}' should be unrecognized (None)")

    # -------------------------------------------------------------------------
    # 2. Action Summary Formatting Unit Tests
    # -------------------------------------------------------------------------

    def test_format_action_summary_file(self):
        handler = VoiceConfirmationHandler()
        summary = handler.format_action_summary("file_tool", "create_file", {"path": "test.txt"})
        self.assertIn("create file test.txt", summary)

    def test_format_action_summary_app(self):
        handler = VoiceConfirmationHandler()
        summary = handler.format_action_summary("application_tool", "launch", {"app_name": "notepad"})
        self.assertIn("launch notepad", summary)

    def test_format_action_summary_browser(self):
        handler = VoiceConfirmationHandler()
        summary = handler.format_action_summary("browser_tool", "navigate", {"url": "https://example.com"})
        self.assertIn("navigate to https://example.com", summary)

    # -------------------------------------------------------------------------
    # 3. Interactive Confirmation Loop Tests
    # -------------------------------------------------------------------------

    def test_confirm_yes_flow(self):
        mock_stt = MockSTT(responses=["yes"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)

        result = handler.confirm(action_summary="create this file")

        self.assertTrue(result)
        # Verify prompt spoken
        self.assertTrue(any("I need permission to create this file" in p for p in self.mock_tts.spoken_phrases))
        # Verify confirmed spoken
        self.assertIn("Confirmed.", self.mock_tts.spoken_phrases)

    def test_confirm_no_flow(self):
        mock_stt = MockSTT(responses=["no"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)

        result = handler.confirm(action_summary="create this file")

        self.assertFalse(result)
        self.assertTrue(any("I need permission to create this file" in p for p in self.mock_tts.spoken_phrases))
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    def test_confirm_stop_flow(self):
        mock_stt = MockSTT(responses=["stop"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)

        result = handler.confirm(action_summary="launch this application")

        self.assertFalse(result)
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    def test_confirm_cancel_flow(self):
        mock_stt = MockSTT(responses=["cancel"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)

        result = handler.confirm(action_summary="launch this application")

        self.assertFalse(result)
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    def test_confirm_hindi_haan_flow(self):
        mock_stt = MockSTT(responses=["haan"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)

        result = handler.confirm(action_summary="modify settings")

        self.assertTrue(result)
        self.assertIn("Confirmed.", self.mock_tts.spoken_phrases)

    def test_confirm_retry_then_affirm(self):
        # First attempt is unclear ("what"), second attempt is "yes"
        mock_stt = MockSTT(responses=["what is this", "yes"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt, max_attempts=2)

        result = handler.confirm(action_summary="create this file")

        self.assertTrue(result)
        self.assertTrue(any("Please say Yes to confirm" in p for p in self.mock_tts.spoken_phrases))
        self.assertIn("Confirmed.", self.mock_tts.spoken_phrases)

    def test_confirm_exhausted_attempts_cancels_safely(self):
        # Both attempts are unrecognized
        mock_stt = MockSTT(responses=["gibberish", "unknown"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt, max_attempts=2)

        result = handler.confirm(action_summary="dangerous action")

        self.assertFalse(result)
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    # -------------------------------------------------------------------------
    # 4. Integration with PermissionManager
    # -------------------------------------------------------------------------

    def test_permission_manager_safe_bypasses_voice_confirmation(self):
        mock_stt = MockSTT(responses=["no"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        perm = PermissionManager(voice_handler=handler)

        allowed, level, msg = perm.evaluate(
            tool_name="system_tool",
            operation="ram",
            args={"query": "ram"},
            declared_level=PermissionLevel.SAFE,
        )

        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)
        self.assertEqual(len(self.mock_tts.spoken_phrases), 0)

    def test_permission_manager_blocked_bypasses_voice_confirmation(self):
        mock_stt = MockSTT(responses=["yes"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        perm = PermissionManager(voice_handler=handler)

        # Attempt to delete file or run shell
        allowed, level, msg = perm.evaluate(
            tool_name="system_tool",
            operation="arbitrary_shell",
            args={"cmd": "whoami"},
            declared_level=PermissionLevel.SAFE,
        )

        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.BLOCKED)
        self.assertIn("prohibited", msg.lower())
        # Voice handler should NEVER be prompted for blocked operations
        self.assertEqual(len(self.mock_tts.spoken_phrases), 0)

    def test_permission_manager_confirmation_required_granted(self):
        mock_stt = MockSTT(responses=["yes"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        perm = PermissionManager(voice_handler=handler)

        allowed, level, msg = perm.evaluate(
            tool_name="application_tool",
            operation="launch",
            args={"app_name": "notepad"},
            declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
        )

        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("Confirmed.", self.mock_tts.spoken_phrases)

    def test_permission_manager_confirmation_required_denied(self):
        mock_stt = MockSTT(responses=["no"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        perm = PermissionManager(voice_handler=handler)

        allowed, level, msg = perm.evaluate(
            tool_name="application_tool",
            operation="launch",
            args={"app_name": "notepad"},
            declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
        )

        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.CONFIRMATION_REQUIRED)
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    # -------------------------------------------------------------------------
    # 5. Integration with ToolRegistry
    # -------------------------------------------------------------------------

    def test_tool_registry_denied_via_voice_confirmation(self):
        mock_stt = MockSTT(responses=["stop"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        perm = PermissionManager(voice_handler=handler)
        registry = ToolRegistry(permission_manager=perm)

        # file_tool create_file triggers CONFIRMATION_REQUIRED
        result = registry.execute_tool(
            "file_tool",
            {"action": "create_file", "path": "unauthorized_test.txt", "content": "hello"}
        )

        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("denied", result.error.lower())
        self.assertIn("Cancelled.", self.mock_tts.spoken_phrases)

    # -------------------------------------------------------------------------
    # 6. Integration with DakuRemoteClient
    # -------------------------------------------------------------------------

    def test_client_prompt_confirmation_uses_voice_handler(self):
        mock_stt = MockSTT(responses=["yes"])
        handler = VoiceConfirmationHandler(tts=self.mock_tts, stt=mock_stt)
        client = DakuRemoteClient(voice_handler=handler)

        action_spec = {
            "name": "application_tool",
            "description": "launch notepad",
            "args": {"app_name": "notepad"},
        }
        approved = client._prompt_confirmation(action_spec)

        self.assertTrue(approved)
        self.assertIn("Confirmed.", self.mock_tts.spoken_phrases)


if __name__ == "__main__":
    unittest.main()
