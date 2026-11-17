"""
DAKU Tool Base Classes & Data Structures
Defines the standard contract for all local tools and MCP tools.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PermissionLevel(str, Enum):
    """3-tier security classification for all tool actions."""
    SAFE = "SAFE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass
class ToolParameter:
    """Definition of a single parameter accepted by a tool."""
    name: str
    type: str  # string, integer, boolean, etc.
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


@dataclass
class ToolResult:
    """Structured result returned by every tool execution."""
    success: bool
    data: Any = None
    message: str = ""
    raw_output: str = ""
    error: Optional[str] = None
    verified: bool = False

    def to_voice_summary(self) -> str:
        """Returns a concise, voice-friendly summary string."""
        if self.message:
            return self.message
        if self.success:
            return "Operation completed successfully."
        return f"Operation failed: {self.error or 'Unknown error'}"


class BaseTool:
    """Base abstract class for all DAKU system and MCP tools."""

    name: str = "base_tool"
    description: str = "Base tool description"
    permission_level: PermissionLevel = PermissionLevel.SAFE
    parameters: List[ToolParameter] = []

    def get_schema(self) -> Dict[str, Any]:
        """Generates OpenAI-compatible function calling schema."""
        properties = {}
        required = []
        for p in self.parameters:
            prop_def: Dict[str, Any] = {
                "type": p.type,
                "description": p.description,
            }
            if p.enum:
                prop_def["enum"] = p.enum
            properties[p.name] = prop_def
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def validate_args(self, args: Dict[str, Any]) -> Optional[str]:
        """Validates provided arguments against the schema. Returns error string if invalid."""
        for p in self.parameters:
            if p.required and p.name not in args:
                return f"Missing required parameter: '{p.name}'"
            if p.name in args and p.enum and args[p.name] not in p.enum:
                return f"Invalid value for '{p.name}'. Expected one of: {p.enum}"
        return None

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Executes the tool logic with validated arguments."""
        raise NotImplementedError

    def verify(self, result: ToolResult) -> bool:
        """Verifies that the executed action took place in the real system."""
        return result.success
