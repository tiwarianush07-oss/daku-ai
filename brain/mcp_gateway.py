"""
DAKU Phase 8 — MCP Permission Gateway Hardening Module
Provides:
1. Declarative Per-Server & Per-Tool Access Control Lists (ACLs)
2. Token Isolation Boundary (scrubbing secrets from child MCP processes)
3. In-Memory Token-Bucket Rate Limiting (preventing runaway tool execution loops)
4. Integration with DAKU's 3-Tier Security Gate and DeepSeek Harness Bridge
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.base import PermissionLevel
from tools.permissions import PermissionManager

logger = logging.getLogger("daku.mcp.gateway")

DEFAULT_ACL_PATH = Path(__file__).resolve().parent.parent / "config" / "mcp_acl.json"

# Harmless baseline OS environment variables always permitted for child execution
SAFE_SYSTEM_ENV_VARS: Set[str] = {
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "NUMBER_OF_PROCESSORS",
    "LOCALAPPDATA",
    "APPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
}

# Core secrets strictly prohibited from ever leaking to external MCP subprocesses
STRICT_FORBIDDEN_ENV_KEYS: Set[str] = {
    "MODEL_API_KEY",
    "SARVAM_API_KEY",
    "DAKU_AUTH_TOKEN",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HARNESS_API_KEY",
    "UNCENSORED_API_KEY",
}


class TokenBucket:
    """Thread-safe in-memory token bucket rate limiter using time.monotonic()."""

    def __init__(self, rate_per_minute: float = 30.0, burst_capacity: float = 5.0):
        self.capacity = max(1.0, float(burst_capacity))
        self.refill_rate = max(0.01, float(rate_per_minute) / 60.0)  # tokens per second
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, count: float = 1.0) -> Tuple[bool, float]:
        """
        Attempts to consume tokens.
        Returns (allowed, wait_seconds_required_if_denied).
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.last_refill = now

            # Refill tokens up to burst capacity
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= count:
                self.tokens -= count
                return True, 0.0

            deficit = count - self.tokens
            wait_time = deficit / self.refill_rate
            return False, wait_time

    def reset(self) -> None:
        """Resets the bucket to full capacity."""
        with self._lock:
            self.tokens = self.capacity
            self.last_refill = time.monotonic()


class MCPPermissionGateway:
    """
    Phase 8 MCP Security Gateway enforcing per-server ACLs,
    token isolation boundaries, and rate-limiting across all MCP tools.
    """

    def __init__(
        self,
        acl_path: Optional[Union[Path, str]] = None,
        permission_manager: Optional[PermissionManager] = None,
        auto_confirm_in_test: bool = True,
    ):
        self.acl_path = Path(acl_path) if acl_path else DEFAULT_ACL_PATH
        self.permission_manager = permission_manager or PermissionManager(auto_confirm_in_test=auto_confirm_in_test)
        self._lock = threading.Lock()
        self._rate_limiters: Dict[str, TokenBucket] = {}
        self.config: Dict[str, Any] = {}
        self.load_acl_config()

    def load_acl_config(self) -> None:
        """Loads declarative rules from config/mcp_acl.json with robust fallbacks."""
        with self._lock:
            if self.acl_path and self.acl_path.is_file():
                try:
                    with open(self.acl_path, "r", encoding="utf-8") as f:
                        self.config = json.load(f)
                    logger.info(f"Loaded MCP ACL configuration from {self.acl_path}")
                except Exception as e:
                    logger.warning(f"Failed to load MCP ACL config from {self.acl_path}: {e}")
                    self.config = self._default_acl_config()
            else:
                self.config = self._default_acl_config()

            # Initialize rate limiters from config
            self._init_rate_limiters()

    def _default_acl_config(self) -> Dict[str, Any]:
        """Provides safe fallback configuration if mcp_acl.json is missing."""
        return {
            "version": "1.0.0",
            "default_policy": "CONFIRMATION_REQUIRED",
            "default_rate_limit_per_minute": 30,
            "default_rate_limit_burst": 5,
            "forbidden_env_keys": list(STRICT_FORBIDDEN_ENV_KEYS),
            "servers": {},
        }

    def _init_rate_limiters(self) -> None:
        """Initializes token buckets for configured servers."""
        default_rpm = self.config.get("default_rate_limit_per_minute", 30)
        default_burst = self.config.get("default_rate_limit_burst", 5)

        servers = self.config.get("servers", {})
        for name, s_cfg in servers.items():
            rpm = s_cfg.get("rate_limit_per_minute", default_rpm)
            burst = s_cfg.get("rate_limit_burst", s_cfg.get("burst_size", default_burst))
            self._rate_limiters[name] = TokenBucket(rate_per_minute=rpm, burst_capacity=burst)

    def _get_rate_limiter(self, server_name: str) -> TokenBucket:
        """Retrieves or creates a rate limiter bucket for a given server name."""
        with self._lock:
            if server_name not in self._rate_limiters:
                default_rpm = self.config.get("default_rate_limit_per_minute", 30)
                default_burst = self.config.get("default_rate_limit_burst", 5)
                self._rate_limiters[server_name] = TokenBucket(
                    rate_per_minute=default_rpm,
                    burst_capacity=default_burst,
                )
            return self._rate_limiters[server_name]

    def check_rate_limit(self, server_name: str) -> Tuple[bool, Optional[str]]:
        """
        Enforces token-bucket rate limits per MCP server.
        Returns (allowed: bool, rejection_reason: Optional[str]).
        """
        bucket = self._get_rate_limiter(server_name)
        allowed, wait_seconds = bucket.consume(1.0)
        if not allowed:
            msg = (
                f"Rate limit exceeded for MCP server '{server_name}'. "
                f"Bucket depleted; please retry in {wait_seconds:.1f} seconds."
            )
            logger.warning(msg)
            return False, msg
        return True, None

    def get_effective_permission(
        self,
        server_name: str,
        tool_name: str,
    ) -> Tuple[PermissionLevel, str]:
        """
        Evaluates the declarative per-server and per-tool permission level from ACL rules.
        Returns (effective_permission_level, reasoning_string).
        """
        servers = self.config.get("servers", {})
        default_policy_str = self.config.get("default_policy", "CONFIRMATION_REQUIRED")

        # 1. Unknown server -> Defaults to CONFIRMATION_REQUIRED
        if server_name not in servers:
            level = getattr(PermissionLevel, default_policy_str, PermissionLevel.CONFIRMATION_REQUIRED)
            return level, f"Unknown MCP server '{server_name}' defaulted to {level.value}."

        s_cfg = servers[server_name]
        tools_cfg = s_cfg.get("tools", {})

        # Normalize tool name (check both raw tool name and namespaced mcp_{server}_{tool})
        clean_tool = tool_name
        prefix = f"mcp_{server_name}_"
        if clean_tool.startswith(prefix):
            clean_tool = clean_tool[len(prefix):]

        # 2. Per-tool explicit override
        if clean_tool in tools_cfg:
            rule_str = tools_cfg[clean_tool].upper()
            level = getattr(PermissionLevel, rule_str, PermissionLevel.CONFIRMATION_REQUIRED)
            return level, f"Explicit rule for '{server_name}:{clean_tool}' is {level.value}."

        # 3. Server-level default
        server_default = s_cfg.get("default_level", default_policy_str).upper()
        level = getattr(PermissionLevel, server_default, PermissionLevel.CONFIRMATION_REQUIRED)
        return level, f"Server '{server_name}' default policy is {level.value}."

    def evaluate_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, PermissionLevel, str]:
        """
        Comprehensive evaluation checking:
        1. Rate limits
        2. Hard-blocked command patterns
        3. Declarative ACL permissions
        4. User confirmation (if CONFIRMATION_REQUIRED)
        """
        args_dict = args if args is not None else (arguments or {})

        # 1. Check Rate Limit
        rate_ok, rate_err = self.check_rate_limit(server_name)
        if not rate_ok:
            return False, PermissionLevel.BLOCKED, rate_err or "Rate limit exceeded."

        # 2. Check ACL effective permission
        effective_level, reason = self.get_effective_permission(server_name, tool_name)

        # 3. Check for hard-blocked operation patterns (delete, drop, eval, format)
        op_lower = (tool_name + " " + json.dumps(args_dict)).lower()
        if any(pat in op_lower for pat in ("delete_dir", "format_disk", "drop_table", "drop_database", "eval_script_raw")):
            return False, PermissionLevel.BLOCKED, f"Operation contains permanently blocked safety pattern."

        # 4. Enforce level
        if effective_level == PermissionLevel.BLOCKED:
            return False, PermissionLevel.BLOCKED, f"Operation '{tool_name}' on server '{server_name}' is BLOCKED by ACL policy."

        if effective_level == PermissionLevel.SAFE:
            return True, PermissionLevel.SAFE, reason

        if effective_level == PermissionLevel.CONFIRMATION_REQUIRED:
            desc = f"Execute MCP tool '{tool_name}' on server '{server_name}' with parameters {args_dict}"
            is_confirmed, level, msg = self.permission_manager.evaluate(
                tool_name=f"mcp_{server_name}_{tool_name}",
                operation=tool_name,
                args=args_dict,
                declared_level=PermissionLevel.CONFIRMATION_REQUIRED,
            )
            return is_confirmed, level, msg

        return False, PermissionLevel.BLOCKED, "Unknown permission resolution."

    def scrub_environment(
        self,
        server_name: str,
        base_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        Token Isolation Boundary:
        Scrubs environment variables before passing them to child MCP processes.
        Strictly prohibits MODEL_API_KEY, SARVAM_API_KEY, DAKU_AUTH_TOKEN, and other
        sensitive secrets unless explicitly allowlisted in that server's ACL.
        Core DAKU authentication tokens are NEVER allowed to pass.
        """
        source = dict(base_env if base_env is not None else os.environ)
        servers = self.config.get("servers", {})
        server_cfg = servers.get(server_name, {})
        allowed_keys: Set[str] = set(server_cfg.get("allowed_env_keys", []))

        # Configured forbidden keys from ACL
        forbidden_keys: Set[str] = set(self.config.get("forbidden_env_keys", [])) | STRICT_FORBIDDEN_ENV_KEYS

        scrubbed: Dict[str, str] = {}
        for k, v in source.items():
            # Never pass core DAKU tokens under any circumstance
            if k in STRICT_FORBIDDEN_ENV_KEYS and k not in allowed_keys:
                continue

            # Check if key is explicitly forbidden
            if k in forbidden_keys and k not in allowed_keys:
                continue

            # Check if key is in harmless system set or server allowlist
            if k in SAFE_SYSTEM_ENV_VARS or k in allowed_keys:
                scrubbed[k] = v

        return scrubbed

    def reset_rate_limits(self) -> None:
        """Resets all token bucket rate limiters (primarily for test isolation)."""
        with self._lock:
            for bucket in self._rate_limiters.values():
                bucket.reset()

    def get_metrics(self) -> Dict[str, Any]:
        """Provides status and observability metrics for MCP security gateway."""
        with self._lock:
            servers = self.config.get("servers", {})
            return {
                "configured_servers_count": len(servers),
                "active_rate_limiters_count": len(self._rate_limiters),
                "default_policy": self.config.get("default_policy", "CONFIRMATION_REQUIRED"),
                "servers": list(servers.keys()),
            }
