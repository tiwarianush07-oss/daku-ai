"""
DAKU DeepSeek Harness Adapter & Plugin Bridge
Phase B: Cordis-powered "Everything is a Plugin" runtime integration.

Provides:
- HarnessPluginManifest: Representation of DAKU tools as Cordis/dsh plugins.
- HarnessSession: Multi-turn session state with an append-only event log.
- HarnessCommandResult: Settled tool result compatible with DeepSeek Harness command/run protocol.
- DeepSeekHarnessBridge: Full lifecycle adapter wiring DAKU's native OS tools and MCP servers
  into the DeepSeek Harness runtime with 3-tier security enforcement and <think> reasoning extraction.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from brain.mcp_gateway import MCPPermissionGateway
from brain.memory_store import MemoryStore, MemoryTier
from brain.multipass import MultiPassReasoner
from config.settings import settings
from tools.base import PermissionLevel, ToolResult
from tools.permissions import PermissionManager
from tools.planner import TaskPlanner
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.harness.bridge")

# Maximum events stored in memory per session to enforce <25 MB RAM ceiling
MAX_SESSION_EVENTS = 100


@dataclass
class HarnessPluginManifest:
    """Represents a DAKU tool capability exposed as a Cordis plugin for DeepSeek Harness."""

    plugin_id: str
    name: str
    version: str
    category: str
    description: str
    tool_names: List[str]
    permission_tier: str
    schemas: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "tool_names": self.tool_names,
            "permission_tier": self.permission_tier,
            "schemas": self.schemas,
        }


@dataclass
class HarnessCommandResult:
    """Settled command result conforming to the DeepSeek Harness CommandResult / Approval protocol."""

    kind: str  # "success" | "error"
    tool_name: str
    result_text: str
    voice_summary: str
    verified: bool = False
    permission_level: str = "SAFE"
    outcome: Optional[str] = None  # "allowed-once" | "rejected" | "cancelled"
    source_event_seq: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "kind": self.kind,
            "tool_name": self.tool_name,
            "text": self.result_text,
            "voice_summary": self.voice_summary,
            "verified": self.verified,
            "permission_level": self.permission_level,
        }
        if self.outcome:
            data["outcome"] = self.outcome
        if self.source_event_seq is not None:
            data["source_event_seq"] = self.source_event_seq
        return data


class HarnessSession:
    """
    Append-only multi-turn session state conforming to DeepSeek Harness event log design.
    Maintains bounded memory usage (< 2 MB) for the AMD Athlon 4 GB RAM profile.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id: str = session_id or f"dsh_session_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        self.created_at: float = time.time()
        self.event_log: List[Dict[str, Any]] = []
        self._seq_counter: int = 0
        self.last_think_trace: str = ""
        self.pass_count: int = 0
        self.active_plugins: Set[str] = set()
        self.metadata: Dict[str, Any] = {}

        # Log initial creation event
        self.record_event("session/created", {"session_id": self.session_id, "timestamp": self.created_at})

    def record_event(self, event_type: str, payload: Dict[str, Any]) -> int:
        """Appends a new immutable event to the log with monotonic sequence numbering."""
        seq = self._seq_counter
        self._seq_counter += 1

        event = {
            "seq": seq,
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }

        self.event_log.append(event)
        if len(self.event_log) > MAX_SESSION_EVENTS:
            # Preserve earliest session/created event and slide window for recent history
            first = self.event_log[0]
            self.event_log = [first] + self.event_log[-(MAX_SESSION_EVENTS - 1):]

        return seq

    def get_events(self, since_seq: int = 0) -> List[Dict[str, Any]]:
        """Returns all events recorded since the given sequence number."""
        return [e for e in self.event_log if e["seq"] >= since_seq]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "event_count": len(self.event_log),
            "seq_counter": self._seq_counter,
            "last_think_trace": self.last_think_trace,
            "pass_count": self.pass_count,
            "active_plugins": list(self.active_plugins),
        }


class DeepSeekHarnessBridge:
    """
    Bridge connecting DAKU's native tools, 3-tier permissions, and reasoning engines
    to the DeepSeek Harness (dsh) Cordis plugin architecture.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        reasoner: Optional[MultiPassReasoner] = None,
        planner: Optional[TaskPlanner] = None,
        mcp_gateway: Optional[MCPPermissionGateway] = None,
        memory_store: Optional[MemoryStore] = None,
    ):
        self.permission_manager = permission_manager or PermissionManager()
        self.tool_registry = tool_registry or ToolRegistry(permission_manager=self.permission_manager)
        self.planner = planner or TaskPlanner(tool_registry=self.tool_registry)
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)
        self.mcp_gateway = mcp_gateway or MCPPermissionGateway()
        self.memory_store = memory_store or MemoryStore()
        self._sessions: Dict[str, HarnessSession] = {}

    def create_session(self, session_id: Optional[str] = None) -> HarnessSession:
        """Creates or registers a new DeepSeek Harness session."""
        session = HarnessSession(session_id=session_id)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[HarnessSession]:
        """Retrieves an existing session by ID."""
        return self._sessions.get(session_id)

    def get_plugin_manifests(self) -> List[HarnessPluginManifest]:
        """
        Maps DAKU's native OS tools and discovered MCP tools into Cordis plugin manifests.
        """
        schemas_by_name = {s["name"]: s for s in self.tool_registry.get_schemas()}
        manifests: List[HarnessPluginManifest] = []

        # 1. Desktop Application Plugin (application_tool)
        if "application_tool" in schemas_by_name:
            manifests.append(
                HarnessPluginManifest(
                    plugin_id="daku.plugin.application",
                    name="Desktop Application Manager",
                    version="1.0.0",
                    category="desktop-control",
                    description="Launch, list, detect, and verify Windows desktop applications.",
                    tool_names=["application_tool"],
                    permission_tier="CONFIRMATION_REQUIRED",
                    schemas=[schemas_by_name["application_tool"]],
                )
            )

        # 2. Browser Automation Plugin (browser_tool)
        if "browser_tool" in schemas_by_name:
            manifests.append(
                HarnessPluginManifest(
                    plugin_id="daku.plugin.browser",
                    name="Browser Automation & Scraping",
                    version="1.0.0",
                    category="web-automation",
                    description="Navigate URLs, extract DOM text/titles, search web, and inspect pages.",
                    tool_names=["browser_tool"],
                    permission_tier="SAFE",
                    schemas=[schemas_by_name["browser_tool"]],
                )
            )

        # 3. Filesystem Plugin (file_tool)
        if "file_tool" in schemas_by_name:
            manifests.append(
                HarnessPluginManifest(
                    plugin_id="daku.plugin.filesystem",
                    name="Secure Filesystem Tool",
                    version="1.0.0",
                    category="storage",
                    description="Safe file listing, search, metadata inspection, read, and creation.",
                    tool_names=["file_tool"],
                    permission_tier="CONFIRMATION_REQUIRED",
                    schemas=[schemas_by_name["file_tool"]],
                )
            )

        # 4. System Telemetry Plugin (system_tool)
        if "system_tool" in schemas_by_name:
            manifests.append(
                HarnessPluginManifest(
                    plugin_id="daku.plugin.system",
                    name="System Diagnostics & Telemetry",
                    version="1.0.0",
                    category="telemetry",
                    description="Query RAM usage, CPU load, disk storage, time, and Windows version.",
                    tool_names=["system_tool"],
                    permission_tier="SAFE",
                    schemas=[schemas_by_name["system_tool"]],
                )
            )

        # 5. Dynamic MCP Tools
        native_names = {"application_tool", "browser_tool", "file_tool", "system_tool"}
        mcp_tools = [name for name in self.tool_registry.list_tool_names() if name not in native_names]
        if mcp_tools:
            mcp_schemas = [schemas_by_name[name] for name in mcp_tools if name in schemas_by_name]
            manifests.append(
                HarnessPluginManifest(
                    plugin_id="daku.plugin.mcp",
                    name="Model Context Protocol (MCP) Extensions",
                    version="1.0.0",
                    category="mcp-extension",
                    description="Discovered tools from connected MCP servers.",
                    tool_names=mcp_tools,
                    permission_tier="SAFE",
                    schemas=mcp_schemas,
                )
            )

        return manifests

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Returns standard function calling tool schemas for all registered plugins."""
        return [
            {"type": "function", "function": schema}
            for schema in self.tool_registry.get_schemas()
        ]

    def _resolve_plugin_id(self, tool_name: str) -> str:
        """Helper to resolve a tool name to its parent Cordis plugin ID."""
        mapping = {
            "application_tool": "daku.plugin.application",
            "browser_tool": "daku.plugin.browser",
            "file_tool": "daku.plugin.filesystem",
            "system_tool": "daku.plugin.system",
        }
        return mapping.get(tool_name, f"daku.plugin.mcp.{tool_name}")

    def dispatch_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> HarnessCommandResult:
        """
        Dispatches a DeepSeek Harness tool call through DAKU's 3-Tier Security Gate,
        executing with verification and recording session event telemetry.
        """
        session = self.get_session(session_id) if session_id else None
        plugin_id = self._resolve_plugin_id(tool_name)
        if session:
            session.active_plugins.add(plugin_id)

        # 0. MCP Permission Gateway Evaluation (Phase 8)
        if tool_name.startswith("mcp_"):
            tool = self.tool_registry.get_tool(tool_name)
            if hasattr(tool, "server_name") and hasattr(tool, "raw_tool_name"):
                server_name = getattr(tool, "server_name")
                raw_tool = getattr(tool, "raw_tool_name")
            else:
                remainder = tool_name[4:]  # strip 'mcp_'
                server_name = "unknown"
                raw_tool = remainder
                for s in self.mcp_gateway.config.get("servers", {}).keys():
                    if remainder == s or remainder.startswith(f"{s}_"):
                        server_name = s
                        raw_tool = remainder[len(s) + 1:] if len(remainder) > len(s) else remainder
                        break
                if server_name == "unknown":
                    parts = remainder.split("_", 1)
                    server_name = parts[0]
                    raw_tool = parts[1] if len(parts) > 1 else parts[0]

            mcp_allowed, mcp_level, mcp_reason = self.mcp_gateway.evaluate_mcp_tool(
                server_name=server_name,
                tool_name=raw_tool,
                arguments=arguments,
            )
            if not mcp_allowed:
                try:
                    self.memory_store.store_entry(
                        user_id="system",
                        tier=MemoryTier.SECURITY_AUDIT_LOG,
                        key=f"audit_{tool_name}_{int(time.time()*1000)}",
                        content=f"MCP Gate Blocked: {mcp_reason}",
                        metadata={"tool": tool_name, "server": server_name, "level": mcp_level.value, "args": arguments},
                    )
                except Exception:
                    pass
                seq = None
                if session:
                    seq = session.record_event(
                        "tool/mcp_blocked",
                        {"tool": tool_name, "server": server_name, "reason": mcp_reason},
                    )
                return HarnessCommandResult(
                    kind="error",
                    tool_name=tool_name,
                    result_text=mcp_reason,
                    voice_summary="I cannot execute that MCP tool because it is blocked or rate limited by the security gateway.",
                    verified=False,
                    permission_level=mcp_level.value,
                    outcome="rejected",
                    source_event_seq=seq,
                )

        # 1. Determine operation and declared permission level
        tool = self.tool_registry.get_tool(tool_name)
        operation = str(arguments.get("action") or arguments.get("query") or "execute")
        declared_level = tool.permission_level if tool else PermissionLevel.SAFE
        if tool_name == "file_tool" and operation in ("create_file", "create_dir"):
            declared_level = PermissionLevel.CONFIRMATION_REQUIRED
        elif tool_name == "browser_tool" and operation in ("type_text", "click") and arguments.get("sensitive", False):
            declared_level = PermissionLevel.CONFIRMATION_REQUIRED

        # 2. Evaluate permission through PermissionManager
        is_allowed, effective_level, perm_reason = self.permission_manager.evaluate(
            tool_name=tool_name,
            operation=operation,
            args=arguments,
            declared_level=declared_level,
        )

        if session:
            session.record_event(
                "tool/dispatch_received",
                {"tool": tool_name, "plugin": plugin_id, "arguments": arguments, "permission": effective_level.value},
            )

        # 3. Blocked Tier: Immediate refusal
        if not is_allowed and effective_level == PermissionLevel.BLOCKED:
            try:
                self.memory_store.store_entry(
                    user_id="system",
                    tier=MemoryTier.SECURITY_AUDIT_LOG,
                    key=f"audit_{tool_name}_{int(time.time()*1000)}",
                    content=f"Security Policy Blocked: {perm_reason}",
                    metadata={"tool": tool_name, "plugin": plugin_id, "args": arguments, "level": effective_level.value},
                )
            except Exception:
                pass
            seq = None
            if session:
                seq = session.record_event(
                    "tool/blocked",
                    {"tool": tool_name, "reason": perm_reason},
                )
            return HarnessCommandResult(
                kind="error",
                tool_name=tool_name,
                result_text=perm_reason,
                voice_summary="I cannot execute that action because it is blocked by security policy.",
                verified=False,
                permission_level=effective_level.value,
                outcome="rejected",
                source_event_seq=seq,
            )

        # 4. Confirmation Required Tier: Denied by user
        if not is_allowed and effective_level == PermissionLevel.CONFIRMATION_REQUIRED:
            seq = None
            if session:
                seq = session.record_event(
                    "approval/rejected",
                    {"tool": tool_name, "outcome": "rejected", "reason": perm_reason},
                )
            return HarnessCommandResult(
                kind="error",
                tool_name=tool_name,
                result_text=perm_reason,
                voice_summary="Action cancelled.",
                verified=False,
                permission_level=effective_level.value,
                outcome="rejected",
                source_event_seq=seq,
            )

        # 5. Confirmed or Pre-approved Tier
        if effective_level == PermissionLevel.CONFIRMATION_REQUIRED and session:
            session.record_event("approval/granted", {"tool": tool_name, "outcome": "allowed-once"})

        if session:
            session.record_event("tool/executing", {"tool": tool_name, "arguments": arguments})

        tool_result = self.tool_registry.execute_tool(tool_name, arguments)

        # Post-Execution Verification: Trigger reflection if action failed verification
        if not (tool_result.success and tool_result.verified):
            if session:
                session.record_event(
                    "tool/verification_failed",
                    {"tool": tool_name, "error": tool_result.error, "message": tool_result.message},
                )
            reasoning_res = self.reasoner.reason_and_execute(
                user_query=f"Execute {tool_name}",
                initial_action=(tool_name, arguments),
            )
            seq = None
            if session:
                session.pass_count += reasoning_res.passes_used
                seq = session.record_event(
                    "tool/reflection_settled",
                    {
                        "passes_used": reasoning_res.passes_used,
                        "verified": reasoning_res.verified,
                        "summary": reasoning_res.to_voice_summary(),
                    },
                )
            return HarnessCommandResult(
                kind="success" if reasoning_res.verified else "error",
                tool_name=tool_name,
                result_text=reasoning_res.final_answer or reasoning_res.to_voice_summary(),
                voice_summary=reasoning_res.to_voice_summary(),
                verified=reasoning_res.verified,
                permission_level=effective_level.value,
                outcome="allowed-once" if effective_level == PermissionLevel.CONFIRMATION_REQUIRED else None,
                source_event_seq=seq,
            )

        seq = None
        if session:
            seq = session.record_event(
                "tool/executed",
                {"tool": tool_name, "success": tool_result.success, "verified": tool_result.verified},
            )

        return HarnessCommandResult(
            kind="success" if tool_result.success else "error",
            tool_name=tool_name,
            result_text=tool_result.message or tool_result.raw_output or tool_result.error or "Action executed.",
            voice_summary=tool_result.to_voice_summary(),
            verified=tool_result.verified,
            permission_level=effective_level.value,
            outcome="allowed-once" if effective_level == PermissionLevel.CONFIRMATION_REQUIRED else None,
            source_event_seq=seq,
        )

    def extract_and_route_reasoning(
        self,
        raw_content: str,
        session_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Extracts <think>...</think> reasoning traces, storing them in the session telemetry
        while stripping them from the synthesized voice response.
        """
        think_traces: List[str] = []

        def _think_sub(match: re.Match) -> str:
            think_traces.append(match.group(1).strip())
            return ""

        clean_text = re.sub(r"<think>(.*?)</think>", _think_sub, raw_content, flags=re.DOTALL)
        # Catch open unclosed <think> tags if model truncated
        if "<think>" in clean_text:
            parts = clean_text.split("<think>", 1)
            clean_text = parts[0]
            think_traces.append(parts[1].replace("</think>", "").strip())

        full_think_trace = "\n\n".join(t for t in think_traces if t)

        session = self.get_session(session_id) if session_id else None
        if session and full_think_trace:
            session.last_think_trace = full_think_trace
            session.record_event(
                "reasoning/trace_extracted",
                {"length": len(full_think_trace), "preview": full_think_trace[:120]},
            )

        # Normalize clean text for voice TTS
        clean_text = re.sub(r"[#*`_~]", "", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        return clean_text, full_think_trace

    def get_telemetry_snapshot(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Provides an inspectable telemetry snapshot for the Solar Swarm HUD."""
        session = self.get_session(session_id) if session_id else None
        plugins = self.get_plugin_manifests()

        return {
            "harness_bridge_version": "1.0.0",
            "active_session": session.to_dict() if session else None,
            "registered_plugins_count": len(plugins),
            "plugins": [p.to_dict() for p in plugins],
        }
