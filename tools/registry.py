"""
DAKU Tool Registry & Tool Router Module
Provides central registration, schema generation, argument validation,
permission enforcement, and execution verification for all native and MCP tools.
Implements the ToolRouter decision order:
1. Approved native DAKU tool
2. Approved existing MCP tool
3. Safe fallback
4. Refusal if no safe capability exists
Guarantees the AI can NEVER execute arbitrary shell commands.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from tools.application import ApplicationTool
from tools.base import BaseTool, PermissionLevel, ToolResult
from tools.browser import BrowserTool
from tools.file_ops import FileTool
from tools.mcp_client import DynamicMCPTool, MCPManager
from tools.permissions import PermissionManager
from tools.system import SystemTool

logger = logging.getLogger("daku.tools")


class ToolRouter:
    """
    Routes actions to the highest priority, safest available tool:
    Priority 1: Approved native DAKU tool
    Priority 2: Approved existing MCP tool
    Priority 3: Safe fallback
    Priority 4: Refuse / Block
    """

    def __init__(self, registry: "ToolRegistry"):
        self.registry = registry

    def route_action(self, intent: str, args: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Determines the optimal tool name and arguments for a requested intent.
        """
        intent_lower = intent.lower()

        # Priority 1: Native browser / navigation
        if any(w in intent_lower for w in ("browser", "navigate", "url", "webpage", "page_title", "page_text")):
            if self.registry.get_tool("browser_tool"):
                return "browser_tool", args

        # Priority 1: Native application launch/inspect
        if any(w in intent_lower for w in ("launch_app", "open_app", "is_running", "detect_apps")):
            if self.registry.get_tool("application_tool"):
                return "application_tool", args

        # Priority 1: Native file operations
        if any(w in intent_lower for w in ("search_files", "read_file", "list_dir", "create_file")):
            if self.registry.get_tool("file_tool"):
                return "file_tool", args

        # Priority 1: Native system hardware query
        if any(w in intent_lower for w in ("ram", "cpu", "disk", "time", "windows_ver")):
            if self.registry.get_tool("system_tool"):
                return "system_tool", args

        # Priority 2: Check matching MCP tool
        for tool_name in self.registry.list_tool_names():
            if tool_name.startswith("mcp_") and intent_lower in tool_name.lower():
                return tool_name, args

        # Priority 3: Fallback if tool name matches directly
        if self.registry.get_tool(intent):
            return intent, args

        return None, None


class ToolRegistry:
    """
    Central tool registry and execution dispatcher for DAKU.
    """

    def __init__(
        self,
        permission_manager: Optional[PermissionManager] = None,
        mcp_manager: Optional[MCPManager] = None,
        auto_register_defaults: bool = True,
    ):
        self.permission_manager = permission_manager or PermissionManager()
        self.mcp_manager = mcp_manager or MCPManager()
        self._tools: Dict[str, BaseTool] = {}
        self.router = ToolRouter(self)

        if auto_register_defaults:
            self.register_default_tools()

    def register(self, tool: BaseTool) -> None:
        """Registers a tool in the registry."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def list_tool_names(self) -> List[str]:
        """Returns list of registered tool names."""
        return list(self._tools.keys())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Exports OpenAI-compatible function calling schemas for all registered tools."""
        return [tool.get_schema() for tool in self._tools.values()]

    def register_default_tools(self) -> None:
        """Registers native Windows system tools, browser tools, and discovered MCP tools."""
        # 1. Native safe system tools
        self.register(ApplicationTool())
        self.register(BrowserTool())
        self.register(FileTool())
        self.register(SystemTool())

        # 2. Register MCP tools (safe / classified)
        if self.mcp_manager:
            for mcp_tool in self.mcp_manager.create_mcp_tools():
                self.register(mcp_tool)

    def execute_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        """
        Validates, checks permissions, executes, and verifies a tool call.
        Strictly follows the execution contract:
        Tool Name + Args -> Permission Check -> Validator -> Executor -> Verification.
        """
        args_dict = args or {}
        tool = self.get_tool(tool_name)

        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is not registered.",
                message=f"Tool '{tool_name}' is not available.",
                verified=False,
            )

        # 1. Argument validation
        validation_error = tool.validate_args(args_dict)
        if validation_error:
            return ToolResult(
                success=False,
                error=f"Validation failed: {validation_error}",
                message=f"Invalid arguments for {tool_name}: {validation_error}",
                verified=False,
            )

        # 2. Permission check
        operation = args_dict.get("action") or args_dict.get("query") or "execute"
        declared_level = tool.permission_level

        # Context-sensitive elevation for file creation or browser form submissions
        if tool_name == "file_tool" and operation in ("create_file", "create_dir"):
            declared_level = PermissionLevel.CONFIRMATION_REQUIRED
        elif tool_name == "browser_tool" and operation in ("type_text", "click") and args_dict.get("sensitive", False):
            declared_level = PermissionLevel.CONFIRMATION_REQUIRED

        is_allowed, effective_level, reason = self.permission_manager.evaluate(
            tool_name=tool_name,
            operation=str(operation),
            args=args_dict,
            declared_level=declared_level,
        )

        if not is_allowed:
            return ToolResult(
                success=False,
                error=reason,
                message=reason,
                verified=False,
            )

        # 3. Execution
        try:
            result = tool.execute(args_dict)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
                message=f"Error running {tool_name}.",
                verified=False,
            )

        # 4. Verification
        try:
            is_verified = tool.verify(result)
            result.verified = is_verified
        except Exception:
            result.verified = False

        return result
