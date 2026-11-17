"""
DAKU Permission System
Enforces 3-tier security policy (SAFE, CONFIRMATION_REQUIRED, BLOCKED).
Guarantees the AI can NEVER execute arbitrary shell commands or perform unconfirmed destructive actions.
"""

from typing import Any, Callable, Dict, Optional, Tuple

from tools.base import PermissionLevel


# Actions and patterns that are strictly prohibited and will always be BLOCKED
BLOCKED_PATTERNS = [
    "delete_file",
    "delete_dir",
    "remove_file",
    "rmdir",
    "format_disk",
    "drop_table",
    "kill_system",
    "shutdown",
    "restart",
    "arbitrary_shell",
    "exec_shell",
    "powershell_raw",
    "cmd_raw",
    "dump_credentials",
    "read_password",
    "read_env_secrets",
]


class PermissionManager:
    """
    Evaluates and enforces permission levels for all tool operations.
    """

    def __init__(
        self,
        confirmation_callback: Optional[Callable[[str, str], bool]] = None,
        auto_confirm_in_test: bool = False,
        voice_handler: Optional[Any] = None,
    ):
        self.confirmation_callback = confirmation_callback
        self.auto_confirm_in_test = auto_confirm_in_test
        self.voice_handler = voice_handler

    def evaluate(
        self,
        tool_name: str,
        operation: str,
        args: Dict[str, Any],
        declared_level: PermissionLevel,
    ) -> Tuple[bool, PermissionLevel, str]:
        """
        Evaluates whether an action is permitted.
        Returns (is_allowed, effective_permission_level, reason_or_message).
        """
        # Check hard-blocked patterns first
        op_lower = operation.lower()
        tool_lower = tool_name.lower()

        for pattern in BLOCKED_PATTERNS:
            if pattern in op_lower or pattern in tool_lower:
                return (
                    False,
                    PermissionLevel.BLOCKED,
                    f"BLOCKED: Operation '{operation}' is prohibited by DAKU safety policy.",
                )

        if declared_level == PermissionLevel.BLOCKED:
            return (
                False,
                PermissionLevel.BLOCKED,
                f"BLOCKED: Tool '{tool_name}' is permanently blocked by safety policy.",
            )

        if declared_level == PermissionLevel.SAFE:
            return (True, PermissionLevel.SAFE, "Action is pre-approved and SAFE to execute.")

        # CONFIRMATION_REQUIRED level
        if declared_level == PermissionLevel.CONFIRMATION_REQUIRED:
            if self.auto_confirm_in_test:
                return (
                    True,
                    PermissionLevel.CONFIRMATION_REQUIRED,
                    "Action confirmed (test mode).",
                )

            action_desc = f"Tool '{tool_name}' wants to perform '{operation}' with parameters: {args}"
            approved = self._request_user_confirmation(tool_name, action_desc)
            if approved:
                return (
                    True,
                    PermissionLevel.CONFIRMATION_REQUIRED,
                    "Action confirmed by user.",
                )
            else:
                return (
                    False,
                    PermissionLevel.CONFIRMATION_REQUIRED,
                    "Action cancelled: User denied permission.",
                )

        return (False, PermissionLevel.BLOCKED, "Unknown permission level.")

    def _request_user_confirmation(self, tool_name: str, action_desc: str) -> bool:
        """Prompts for user confirmation via custom callback, voice handler, or interactive CLI prompt."""
        if self.confirmation_callback:
            return self.confirmation_callback(tool_name, action_desc)

        if self.voice_handler:
            return self.voice_handler.create_callback()(tool_name, action_desc)

        print("\n" + "=" * 60)
        print("  [DAKU SECURITY ALERT] Permission Confirmation Required")
        print("=" * 60)
        print(f"Details: {action_desc}")
        try:
            choice = input("Do you authorize DAKU to perform this action? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
