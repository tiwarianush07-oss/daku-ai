"""
DAKU Voice Confirmation Module
Implements hands-free voice authorization for CONFIRMATION_REQUIRED actions.
Conforms strictly to Section 16 of DAKU Brain specifications:
- DAKU: "I need permission to {action}. Should I continue?"
- User: "Yes." -> DAKU: "Confirmed."
- User: "No." -> DAKU: "Cancelled."
- Supports YES, NO, CANCEL, STOP (with English, Hindi, and Hinglish synonyms).
- Double-redundant fallback to keyboard console input if audio input is unavailable.
"""

import logging
import re
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger("daku.voice.confirmation")

AFFIRMATIVE_TOKENS: Set[str] = {
    "yes", "y", "yeah", "yep", "sure", "proceed", "haan", "ha", "haa",
    "sahi hai", "theek hai", "thik hai", "confirm", "authorized", "authorize",
    "do it", "allow", "ok", "okay", "kar do", "kardo"
}

NEGATIVE_TOKENS: Set[str] = {
    "no", "n", "nah", "nope", "nahi", "nahin", "na", "mat karo",
    "denied", "deny", "don't", "dont", "refuse", "reject", "never"
}

CANCEL_STOP_TOKENS: Set[str] = {
    "cancel", "stop", "halt", "abort", "ruk", "ruko", "roko",
    "chhod do", "chod do", "quit", "exit"
}


class VoiceConfirmationHandler:
    """
    Handles interactive voice authorization for DAKU permission evaluations.
    Integrates directly with PermissionManager and client loops.
    """

    def __init__(
        self,
        tts: Optional[Any] = None,
        stt: Optional[Any] = None,
        spoken_prompt_template: str = "I need permission to {action}. Should I continue?",
        max_attempts: int = 2,
    ):
        self.tts = tts
        self.stt = stt
        self.prompt_template = spoken_prompt_template
        self.max_attempts = max(1, max_attempts)

    def format_action_summary(
        self,
        tool_name: str,
        operation: str = "",
        args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Converts tool execution details into a natural, spoken action description.
        """
        args_dict = args or {}
        tool_lower = (tool_name or "").lower()
        op_lower = (operation or "").lower()

        if "file" in tool_lower:
            if op_lower in ("create_file", "write_file"):
                filename = args_dict.get("path") or args_dict.get("filename") or "this file"
                return f"create file {filename}"
            elif op_lower in ("create_dir", "mkdir"):
                dirname = args_dict.get("path") or args_dict.get("dirname") or "this folder"
                return f"create folder {dirname}"
            return "modify file system"

        if "app" in tool_lower:
            app_name = args_dict.get("app_name") or args_dict.get("name") or "this application"
            return f"launch {app_name}"

        if "browser" in tool_lower:
            if op_lower in ("type_text", "submit", "click"):
                return "perform this web action"
            url = args_dict.get("url")
            if url:
                return f"navigate to {url}"
            return "interact with the browser"

        if operation:
            return f"perform {operation} with {tool_name}"

        return f"execute {tool_name}"

    def evaluate_response(self, text: Optional[str]) -> Optional[bool]:
        """
        Evaluates transcribed utterance or typed text against confirmation tokens.
        Returns:
            True  - Confirmed (affirmative)
            False - Cancelled / Denied (negative or stop/cancel)
            None  - Unrecognized token
        """
        if not text or not str(text).strip():
            return None

        clean = re.sub(r"[^\w\s]", " ", str(text).lower()).strip()
        words = set(clean.split())

        # Exact phrase match or any recognized token in words
        if words & AFFIRMATIVE_TOKENS or clean in AFFIRMATIVE_TOKENS:
            return True

        if words & NEGATIVE_TOKENS or clean in NEGATIVE_TOKENS:
            return False

        if words & CANCEL_STOP_TOKENS or clean in CANCEL_STOP_TOKENS:
            return False

        return None

    def confirm(
        self,
        action_summary: str,
        tool_name: str = "",
        args: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Executes the voice confirmation loop:
        1. Speaks and prints: 'I need permission to {action}. Should I continue?'
        2. Captures user voice/text response.
        3. Validates against YES/NO/CANCEL/STOP.
        4. Speaks and prints: 'Confirmed.' or 'Cancelled.'
        """
        action_text = action_summary or self.format_action_summary(tool_name, args=args)
        question = self.prompt_template.format(action=action_text)

        print("\n" + "=" * 60)
        print("  [DAKU VOICE SECURITY] Permission Confirmation Required")
        print("=" * 60)
        print(f"Action   : {action_text}")
        if tool_name:
            print(f"Tool     : {tool_name}")
        if args:
            print(f"Args     : {args}")
        print(f"Prompt   : \"{question}\"")
        print("Expected : YES / NO / CANCEL / STOP")
        print("=" * 60)

        # Spoken question prompt
        if self.tts:
            try:
                self.tts.speak(question)
            except Exception as e:
                logger.warning(f"TTS prompt failed: {e}")

        for attempt in range(self.max_attempts):
            # Capture user response via STT (with fallback) or standard input
            user_response = None
            if self.stt:
                try:
                    user_response = self.stt.listen(prompt_text=question)
                except Exception as e:
                    logger.warning(f"STT capture failed: {e}")
                    user_response = None

            if not user_response:
                try:
                    user_response = input("[Voice/Text Authorization] Should I continue? [Yes/No/Cancel/Stop]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    self._speak_and_print("Cancelled.")
                    return False

            decision = self.evaluate_response(user_response)

            if decision is True:
                self._speak_and_print("Confirmed.")
                return True
            elif decision is False:
                self._speak_and_print("Cancelled.")
                return False

            # Unrecognized response
            if attempt < self.max_attempts - 1:
                clarification = "Please say Yes to confirm, or No or Cancel to abort."
                print(f"[DAKU] {clarification}")
                if self.tts:
                    try:
                        self.tts.speak(clarification)
                    except Exception:
                        pass

        # If all attempts exhausted without clear answer, default to safe refusal
        self._speak_and_print("Cancelled.")
        return False

    def _speak_and_print(self, text: str) -> None:
        """Helper to print and speak confirmation outcome."""
        print(f"[DAKU] {text}")
        if self.tts:
            try:
                self.tts.speak(text)
            except Exception as e:
                logger.warning(f"TTS confirmation response failed: {e}")

    def create_callback(self) -> Callable[[str, str], bool]:
        """
        Creates a callback function adhering to PermissionManager.confirmation_callback contract.
        Signature: (tool_name: str, action_desc: str) -> bool
        """
        def _callback(tool_name: str, action_desc: str) -> bool:
            # Parse action description for friendly summary
            summary = action_desc
            match = re.search(r"wants to perform '([^']+)'", action_desc)
            if match:
                op = match.group(1)
                summary = self.format_action_summary(tool_name, operation=op)
            return self.confirm(action_summary=summary, tool_name=tool_name)

        return _callback
