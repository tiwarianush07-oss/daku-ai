"""
DAKU Agent Backend Interface & Implementations
Phase 4: DeepSeek Harness + Uncensored R1 Backend + Direct Model Backend.

Provides:
- AgentBackend: Abstract interface for all agent backends with full lifecycle management.
- DeepSeekHarnessBackend: Modular agent orchestration client based on the official DeepSeek Harness
  architecture (zero local LLM inference, remote execution, session handling, tool routing).
- UncensoredR1Backend: Remote DeepSeek R1 Distill backend supporting FastAPI and OpenAI-compatible
  endpoints, automatic <think> reasoning tag stripping for voice TTS, and structured tool extraction.
- BackendFactory: Dynamic factory for selecting and configuring backends via AGENT_BACKEND.

Zero local large model inference. All heavy computation remains remote/cloud-side.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from brain.multipass import MultiPassReasoner
from config.settings import settings
from tools.base import ToolResult
from tools.planner import TaskPlanner
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.backend")

DAKU_SYSTEM_PROMPT = """You are DAKU, a lightweight personal voice AI assistant and task automation agent for Windows.
Rules:
1. Keep responses short, natural, helpful, voice-friendly, and action-oriented (1 to 2 sentences max).
2. Support English, Hindi, and Hinglish naturally.
3. When the user asks to perform an action (open an application, open browser, navigate URL, check page title, find files, check RAM/CPU, list files), use the available tools.
4. Never falsely claim that an action was executed if it was not. Always report the verified result.
5. Do not output markdown code blocks or long explanations unless specifically asked.
"""


def _mask_secret_value(val: str) -> str:
    """Masks secrets for secure logging."""
    if not val or len(val) < 6:
        return "********"
    return f"{val[:2]}********{val[-2:]}"


class AgentBackend:
    """Abstract interface for agent orchestration backends."""

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Process a user message and return the assistant response string."""
        raise NotImplementedError

    def initialize(self) -> bool:
        """Initialize backend connection and resources."""
        return True

    def shutdown(self) -> None:
        """Cleanly terminate backend session and release resources."""
        pass

    def is_healthy(self) -> bool:
        """Check backend health and connectivity."""
        return True

    def get_name(self) -> str:
        """Return backend identifier name."""
        return self.__class__.__name__


class DeepSeekHarnessBackend(AgentBackend):
    """
    DeepSeek Harness Agent Orchestration Backend.
    Operates as AGENT ORCHESTRATION over remote Cloud APIs.
    Does NOT run local model inference — 100% cloud-first for low-spec hardware.

    Features:
    - Session handling & lightweight memory (< 10 MB RAM)
    - Tool interaction via DAKU's ToolRegistry (native tools, browser automation, MCP tools)
    - Response normalization & clean voice synthesis output
    - Graceful error, timeout, and failure recovery
    - Clean shutdown handler
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 15.0,
        tool_registry: Optional[ToolRegistry] = None,
        reasoner: Optional[MultiPassReasoner] = None,
        bridge: Optional[Any] = None,
    ):
        self.endpoint = (endpoint or getattr(settings, "DEEPSEEK_HARNESS_URL", None) or settings.HARNESS_ENDPOINT or settings.MODEL_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else (settings.HARNESS_API_KEY or settings.MODEL_API_KEY)
        self.model_name = model_name or settings.HARNESS_MODEL_NAME or settings.MODEL_NAME
        self.timeout = timeout
        self.tool_registry = tool_registry or ToolRegistry()
        self.planner = TaskPlanner(tool_registry=self.tool_registry)
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)
        from brain.deepseek_harness_bridge import DeepSeekHarnessBridge
        self.bridge = bridge or DeepSeekHarnessBridge(
            tool_registry=self.tool_registry,
            permission_manager=self.tool_registry.permission_manager,
            reasoner=self.reasoner,
            planner=self.planner,
        )
        self.session_id = f"dsh_session_{int(time.time() * 1000)}"
        self.session = self.bridge.create_session(self.session_id)
        self.last_think_trace: str = ""
        self._is_active = True
        logger.info(f"Initialized DeepSeekHarnessBackend [Session: {self.session_id}, Model: {self.model_name}]")

    def initialize(self) -> bool:
        self._is_active = True
        return True

    def shutdown(self) -> None:
        """Clean shutdown of session state."""
        self._is_active = False
        if hasattr(self, "session") and self.session:
            self.session.record_event("session/shutdown", {"timestamp": time.time()})
        logger.info(f"DeepSeekHarnessBackend session {self.session_id} shut down cleanly.")

    def is_healthy(self) -> bool:
        return self._is_active

    def get_name(self) -> str:
        return "DeepSeekHarnessBackend"

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides real-time telemetry snapshot for Solar Swarm HUD and diagnostics."""
        return {
            "backend": "DeepSeekHarnessBackend",
            "session_id": self.session_id,
            "harness_status": "ACTIVE" if self._is_active else "STOPPED",
            "endpoint": self.endpoint,
            "model": self.model_name,
            "event_count": len(self.session.event_log) if self.session else 0,
            "pass_count": self.session.pass_count if self.session else 0,
            "last_think_trace": self.last_think_trace,
            "active_plugins": list(self.session.active_plugins) if self.session else [],
            "plugin_count": len(self.bridge.get_plugin_manifests()),
            "plugins": [p.to_dict() for p in self.bridge.get_plugin_manifests()],
        }

    def get_last_think_trace(self) -> str:
        return self.last_think_trace

    def get_session(self) -> Optional[Any]:
        return getattr(self, "session", None)

    def _execute_offline_intent(self, user_message: str) -> Optional[str]:
        """Offline fallback intent parsing when API key is missing or network is unavailable."""
        msg = user_message.strip().lower().rstrip(".!?,")

        # Multi-Step or Browser query
        has_browser = any(w in msg for w in ("chrome", "browser", "edge", ".com", ".org", ".in", "google", "website"))
        has_compound = any(w in msg for w in (" and ", " aur ", " then ", "tell me", "title", "heading"))
        if (has_browser and (has_compound or "google" in msg or "." in msg)) or (" and " in msg or " aur " in msg):
            plan = self.planner.create_plan(user_message)
            if plan.steps:
                res = self.planner.execute_plan(plan)
                return res.get("message")

        # Application launch
        open_match = re.search(r"(?:open|launch|start|kholo)\s+([a-zA-Z0-9\s\.\:\-_/]+)", msg)
        if open_match:
            app = open_match.group(1).replace("app", "").strip()
            if app in ("notepad", "calc", "paint", "explorer", "cmd", "edge", "chrome", "code", "taskmgr"):
                res = self.tool_registry.execute_tool("application_tool", {"action": "launch", "app_name": app})
                return res.to_voice_summary()
            elif "." in app or app in ("google", "youtube", "github"):
                url = app if app.startswith("http") else f"https://www.{app}.com" if "." not in app else app
                res = self.tool_registry.execute_tool("browser_tool", {"action": "navigate", "url": url})
                return res.to_voice_summary()

        # Hardware queries
        if any(w in msg for w in ("ram", "memory")):
            return self.tool_registry.execute_tool("system_tool", {"query": "ram"}).to_voice_summary()
        if any(w in msg for w in ("cpu", "processor")):
            return self.tool_registry.execute_tool("system_tool", {"query": "cpu"}).to_voice_summary()
        if any(w in msg for w in ("disk", "storage")):
            return self.tool_registry.execute_tool("system_tool", {"query": "disk"}).to_voice_summary()
        if any(w in msg for w in ("time", "date", "clock")):
            return self.tool_registry.execute_tool("system_tool", {"query": "time"}).to_voice_summary()
        if any(w in msg for w in ("windows version", "os version")):
            return self.tool_registry.execute_tool("system_tool", {"query": "windows_ver"}).to_voice_summary()
        if "find" in msg or "search" in msg:
            pat = "*.pdf" if "pdf" in msg else "*.txt" if "txt" in msg else "*"
            return self.tool_registry.execute_tool("file_tool", {"action": "search_files", "pattern": pat}).to_voice_summary()

        return None

    def _normalize_response(self, text: str) -> str:
        """Normalizes agent response for clean Windows SAPI voice synthesis."""
        clean = text.strip()
        clean = re.sub(r"[#*`_~]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _extract_tool_request(self, choice: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Extracts tool calls from choice structure or text content."""
        if "tool_calls" in choice and choice["tool_calls"]:
            tc = choice["tool_calls"][0]
            func = tc.get("function", {})
            func_name = func.get("name", "")
            try:
                func_args = json.loads(func.get("arguments", "{}"))
            except Exception:
                func_args = {}
            return func_name, func_args

        # Check content for tool call markers (e.g. <tool_call>...</tool_call>)
        content = choice.get("message", {}).get("content", "") or choice.get("content", "")
        if "<tool_call>" in content and "</tool_call>" in content:
            match = re.search(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
            if match:
                try:
                    payload = json.loads(match.group(1).strip())
                    name = payload.get("name") or payload.get("tool")
                    args = payload.get("arguments") or payload.get("args") or {}
                    return name, args
                except Exception:
                    pass

        return None

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Processes message through DeepSeek Harness orchestration."""
        if not self._is_active:
            return "DeepSeek Harness backend is shut down."

        if not user_message or not user_message.strip():
            return "I didn't catch that. Please try again."

        if self.session:
            self.session.record_event("turn/start", {"user_message": user_message})

        # Check multi-step task planner first
        plan = self.planner.create_plan(user_message)
        if len(plan.steps) > 1:
            exec_res = self.planner.execute_plan(plan)
            if exec_res.get("success"):
                msg = exec_res.get("message", "Task completed.")
                if self.session:
                    self.session.record_event("turn/multi_step_completed", {"plan_steps": len(plan.steps)})
                return msg

        # Offline fallback if API key is not configured
        if not self.api_key or not self.api_key.strip() or self.api_key == "your_api_key_here":
            offline_reply = self._execute_offline_intent(user_message)
            if offline_reply:
                if self.session:
                    self.session.record_event("turn/offline_intent", {"reply": offline_reply})
                return offline_reply
            msg_lower = user_message.lower()
            if any(w in msg_lower for w in ("hello", "hi", "hey")):
                return "Hello. I'm DAKU. How can I help?"
            elif "who are you" in msg_lower:
                return "I am DAKU, powered by the DeepSeek Harness orchestration agent."
            return "DAKU is running in offline demo mode. Configure an AI provider to enable cloud intelligence."

        # Build OpenAI/Harness-compatible payload
        messages = [{"role": "system", "content": DAKU_SYSTEM_PROMPT}]
        if conversation_history:
            for turn in conversation_history[-6:]:
                messages.append(turn)
        messages.append({"role": "user", "content": user_message})

        tools_payload = self.bridge.get_tool_schemas()

        endpoint = self.endpoint
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "DAKU-DeepSeek-Harness/4.0",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.4,
            "stream": False,
        }
        if tools_payload:
            payload["tools"] = tools_payload

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return f"DeepSeek Harness received status code {resp.status}."
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]["message"]

                # Extract and dispatch tool call through DeepSeek Harness Bridge
                tool_req = self._extract_tool_request(choice)
                if tool_req:
                    func_name, func_args = tool_req
                    cmd_res = self.bridge.dispatch_tool_call(func_name, func_args, session_id=self.session_id)
                    if self.session:
                        self.session.record_event("turn/end", {"tool": func_name, "verified": cmd_res.verified})
                    return cmd_res.voice_summary

                raw_reply = choice.get("content", "").strip()
                # Check for reasoning_content in choice/message (DeepSeek R1 / V3)
                reasoning_content = choice.get("reasoning_content", "") or choice.get("message", {}).get("reasoning_content", "")
                if reasoning_content and not ("<think>" in raw_reply):
                    raw_reply = f"<think>{reasoning_content}</think>\n{raw_reply}"

                clean_reply, think_trace = self.bridge.extract_and_route_reasoning(raw_reply, session_id=self.session_id)
                self.last_think_trace = think_trace
                if self.session:
                    self.session.record_event("turn/end", {"result": clean_reply, "has_reasoning": bool(think_trace)})
                return self._normalize_response(clean_reply) or "I processed your request."

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "Authentication failed for DeepSeek Harness. Please check your API key in .env."
            elif e.code == 429:
                return "DeepSeek Harness rate limit reached. Please try again in a few moments."
            elif e.code >= 500:
                return "The DeepSeek Harness cloud service is currently experiencing server issues."
            return f"DeepSeek Harness API request returned error code {e.code}."
        except urllib.error.URLError:
            local = self._execute_offline_intent(user_message)
            if local:
                return local
            return "Unable to connect to DeepSeek Harness cloud service. Running in offline fallback mode."
        except TimeoutError:
            return "The DeepSeek Harness agent service timed out. Please try again."
        except Exception as e:
            local = self._execute_offline_intent(user_message)
            if local:
                return local
            return f"DeepSeek Harness encountered an unexpected error: {str(e)}"


class UncensoredR1Backend(AgentBackend):
    """
    Uncensored Remote DeepSeek R1 Distill Backend.
    Represents the remote deployment of DeepSeek R1 Distill (e.g. via analytiq-hub/deepseek-uncensored).
    Operates as a 100% REMOTE MODEL BACKEND — NEVER downloads weights to the local 4 GB laptop.

    Features:
    - Strips internal <think>...</think> reasoning traces from voice output (preserves clean speech)
    - Supports both /v1/inference (FastAPI Cloud Run) and /v1/chat/completions (OpenAI/LiteLLM) endpoints
    - Parses structured tool requests from reasoning or JSON blocks
    - Enforces computer safety: Model output NEVER executes OS commands directly;
      routes strictly via Tool Registry -> Permission Manager -> Executor -> Verifier.
    - Zero censorship of legitimate planning, conversation, or analysis.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 15.0,
        tool_registry: Optional[ToolRegistry] = None,
        reasoner: Optional[MultiPassReasoner] = None,
    ):
        self.base_url = (base_url or settings.UNCENSORED_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else (settings.UNCENSORED_API_KEY or settings.MODEL_API_KEY)
        self.model_name = model_name or settings.UNCENSORED_MODEL_NAME
        self.timeout = timeout
        self.tool_registry = tool_registry or ToolRegistry()
        self.planner = TaskPlanner(tool_registry=self.tool_registry)
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)
        self._is_active = True
        logger.info(f"Initialized UncensoredR1Backend [BaseURL: {self.base_url}, Model: {self.model_name}]")

    def initialize(self) -> bool:
        self._is_active = True
        return True

    def shutdown(self) -> None:
        self._is_active = False
        logger.info("UncensoredR1Backend shut down cleanly.")

    def is_healthy(self) -> bool:
        return self._is_active

    def get_name(self) -> str:
        return "UncensoredR1Backend"

    def _strip_think_tags(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Strips internal reasoning traces between <think> and </think> tags.
        Returns (clean_user_facing_response, extracted_reasoning_trace).
        Ensures internal reasoning is NEVER read aloud over Windows TTS.
        """
        reasoning = None
        match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        if match:
            reasoning = match.group(1).strip()
            clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        else:
            clean_text = text.strip()

        # Clean residual tags if broken
        clean_text = clean_text.replace("<think>", "").replace("</think>", "").strip()
        return clean_text, reasoning

    def _extract_tool_request(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Extracts structured tool calls from reasoning output or markdown JSON blocks.
        Model can request an action, but DAKU decides whether it is executed.
        """
        # 1. Look for ```json { "tool": ..., "args": ... } ``` or similar
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block)
                tool = data.get("tool") or data.get("tool_name") or data.get("action")
                args = data.get("args") or data.get("arguments") or data.get("parameters") or data
                if tool and self.tool_registry.get_tool(tool):
                    return tool, args
                elif "action" in data and self.tool_registry.get_tool("browser_tool"):
                    if data["action"] in ("navigate", "get_title", "get_text"):
                        return "browser_tool", data
            except Exception:
                pass

        # 2. Look for <action tool="...">...</action>
        action_match = re.search(r'<action\s+tool=["\'](.*?)["\']>(.*?)</action>', text, re.DOTALL)
        if action_match:
            tool_name = action_match.group(1)
            try:
                args = json.loads(action_match.group(2).strip())
                if self.tool_registry.get_tool(tool_name):
                    return tool_name, args
            except Exception:
                pass

        return None

    def _execute_offline_intent(self, user_message: str) -> Optional[str]:
        """Offline fallback intent handler."""
        msg = user_message.strip().lower().rstrip(".!?,")
        has_browser = any(w in msg for w in ("chrome", "browser", "edge", ".com", ".org", "google", "website"))
        has_compound = any(w in msg for w in (" and ", " aur ", " then ", "title", "heading"))
        if (has_browser and (has_compound or "google" in msg or "." in msg)) or (" and " in msg or " aur " in msg):
            plan = self.planner.create_plan(user_message)
            if plan.steps:
                res = self.planner.execute_plan(plan)
                return res.get("message")

        open_match = re.search(r"(?:open|launch|start|kholo)\s+([a-zA-Z0-9\s\.\:\-_/]+)", msg)
        if open_match:
            app = open_match.group(1).replace("app", "").strip()
            if app in ("notepad", "calc", "paint", "explorer", "cmd", "edge", "chrome", "code", "taskmgr"):
                return self.tool_registry.execute_tool("application_tool", {"action": "launch", "app_name": app}).to_voice_summary()
            elif "." in app or app in ("google", "youtube", "github"):
                url = app if app.startswith("http") else f"https://www.{app}.com" if "." not in app else app
                return self.tool_registry.execute_tool("browser_tool", {"action": "navigate", "url": url}).to_voice_summary()

        if any(w in msg for w in ("ram", "memory")):
            return self.tool_registry.execute_tool("system_tool", {"query": "ram"}).to_voice_summary()
        if any(w in msg for w in ("cpu", "processor")):
            return self.tool_registry.execute_tool("system_tool", {"query": "cpu"}).to_voice_summary()
        if any(w in msg for w in ("disk", "storage")):
            return self.tool_registry.execute_tool("system_tool", {"query": "disk"}).to_voice_summary()
        if any(w in msg for w in ("time", "date")):
            return self.tool_registry.execute_tool("system_tool", {"query": "time"}).to_voice_summary()

        return None

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Processes message through remote Uncensored R1 backend with voice tag stripping."""
        if not self._is_active:
            return "Uncensored R1 backend is shut down."

        if not user_message or not user_message.strip():
            return "I didn't catch that. Please try again."

        # Check multi-step task planner first
        plan = self.planner.create_plan(user_message)
        if len(plan.steps) > 1:
            exec_res = self.planner.execute_plan(plan)
            if exec_res.get("success"):
                return exec_res.get("message", "Task completed.")

        # Offline fallback if API key is not configured
        if not self.api_key or not self.api_key.strip() or self.api_key == "your_api_key_here":
            offline_reply = self._execute_offline_intent(user_message)
            if offline_reply:
                return offline_reply
            msg_lower = user_message.lower()
            if any(w in msg_lower for w in ("hello", "hi", "hey")):
                return "Hello. I'm DAKU. How can I help?"
            elif "who are you" in msg_lower:
                return "I am DAKU, powered by the Uncensored DeepSeek R1 backend."
            return "DAKU is running in offline demo mode. Configure an AI provider to enable cloud intelligence."

        # Determine endpoint URL
        is_fastapi_inference = self.base_url.endswith("/v1/inference")
        endpoint = self.base_url
        if not is_fastapi_inference and not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DAKU-Uncensored-R1/4.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if is_fastapi_inference:
            payload = {
                "prompt": f"{DAKU_SYSTEM_PROMPT}\nUser: {user_message}\nAssistant:",
                "max_tokens": 200,
            }
        else:
            messages = [{"role": "system", "content": DAKU_SYSTEM_PROMPT}]
            if conversation_history:
                for turn in conversation_history[-6:]:
                    messages.append(turn)
            messages.append({"role": "user", "content": user_message})

            tools_payload = [
                {"type": "function", "function": schema}
                for schema in self.tool_registry.get_schemas()
            ]

            payload = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.6,
                "stream": False,
            }
            if tools_payload:
                payload["tools"] = tools_payload

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return f"Uncensored R1 backend received status code {resp.status}."
                body = json.loads(resp.read().decode("utf-8"))

                # Parse choice from OpenAI/LiteLLM or direct content
                raw_text = ""
                if "choices" in body and body["choices"]:
                    choice = body["choices"][0].get("message", {})
                    if "tool_calls" in choice and choice["tool_calls"]:
                        tc = choice["tool_calls"][0].get("function", {})
                        t_name = tc.get("name", "")
                        try:
                            t_args = json.loads(tc.get("arguments", "{}"))
                        except Exception:
                            t_args = {}
                        res = self.tool_registry.execute_tool(t_name, t_args)
                        if not (res.success and res.verified):
                            reasoning_res = self.reasoner.reason_and_execute(
                                user_query=user_message,
                                initial_action=(t_name, t_args),
                            )
                            return reasoning_res.to_voice_summary()
                        return res.to_voice_summary()
                    raw_text = choice.get("content", "")
                elif "content" in body:
                    raw_text = str(body["content"])
                elif "response" in body:
                    raw_text = str(body["response"])
                else:
                    raw_text = json.dumps(body)

                # Check if model requested a tool via text reasoning
                tool_req = self._extract_tool_request(raw_text)
                if tool_req:
                    func_name, func_args = tool_req
                    res = self.tool_registry.execute_tool(func_name, func_args)
                    if not (res.success and res.verified):
                        reasoning_res = self.reasoner.reason_and_execute(
                            user_query=user_message,
                            initial_action=(func_name, func_args),
                        )
                        return reasoning_res.to_voice_summary()
                    return res.to_voice_summary()

                # Strip <think> reasoning tags for clean spoken output
                clean_output, _ = self._strip_think_tags(raw_text)
                clean_output = re.sub(r"[#*`_~]", "", clean_output)
                clean_output = re.sub(r"\s+", " ", clean_output).strip()
                return clean_output or "I processed your request."

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "Authentication failed for Uncensored R1 backend. Please check your API key in .env."
            elif e.code == 429:
                return "Uncensored R1 backend rate limit reached. Please try again in a few moments."
            elif e.code >= 500:
                return "The Uncensored R1 cloud service is currently experiencing server issues."
            return f"Uncensored R1 API request returned error code {e.code}."
        except urllib.error.URLError:
            local = self._execute_offline_intent(user_message)
            if local:
                return local
            return "Unable to connect to Uncensored R1 backend. Running in offline fallback mode."
        except TimeoutError:
            return "The Uncensored R1 service timed out. Please try again."
        except Exception as e:
            local = self._execute_offline_intent(user_message)
            if local:
                return local
            return f"Uncensored R1 encountered an unexpected error: {str(e)}"


class SarvamLLMBackend(AgentBackend):
    """
    Sarvam AI LLM Agent Backend.
    Uses official Sarvam OpenAI-compatible Chat Completions endpoint (https://api.sarvam.ai/v1/chat/completions).
    Models: sarvam-105b-conversations (conversational) or sarvam-105b (agentic reasoning).
    Supports tool calling, multi-pass reasoning, and graceful offline fallback.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 15.0,
        tool_registry: Optional[ToolRegistry] = None,
        reasoner: Optional[MultiPassReasoner] = None,
    ):
        self.endpoint = (endpoint or os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai")).rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            if not self.endpoint.endswith("/v1"):
                self.endpoint = f"{self.endpoint}/v1/chat/completions"
            else:
                self.endpoint = f"{self.endpoint}/chat/completions"

        self.api_key = (api_key or os.getenv("SARVAM_API_KEY", "")).strip()
        self.model_name = (model_name or os.getenv("SARVAM_LLM_MODEL", "sarvam-105b-conversations")).strip()
        self.timeout = timeout
        self.tool_registry = tool_registry or ToolRegistry()
        self.planner = TaskPlanner(tool_registry=self.tool_registry)
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)

    def is_healthy(self) -> bool:
        return bool(self.api_key and self.api_key != "your_sarvam_api_key_here")

    def _execute_offline_intent(self, user_message: str) -> Optional[str]:
        from brain.router import DirectModelRouter
        router = DirectModelRouter(tool_registry=self.tool_registry)
        return router._execute_offline_intent(user_message)

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not user_message or not user_message.strip():
            return "I didn't catch that. Please try again."

        # Offline fallback if API key is not configured
        if not self.is_healthy():
            offline = self._execute_offline_intent(user_message)
            if offline:
                return offline
            return "DAKU is running with Sarvam in offline demo mode. Set SARVAM_API_KEY in .env."

        # Check multi-step planner
        plan = self.planner.create_plan(user_message)
        if len(plan.steps) > 1:
            exec_res = self.planner.execute_plan(plan)
            if exec_res.get("success"):
                return exec_res.get("message", "Task completed.")

        messages = [{"role": "system", "content": DAKU_SYSTEM_PROMPT}]
        if conversation_history:
            for turn in conversation_history[-6:]:
                messages.append(turn)
        messages.append({"role": "user", "content": user_message})

        tools_payload = []
        for schema in self.tool_registry.get_schemas():
            tools_payload.append({"type": "function", "function": schema})

        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "DAKU-Sarvam-Agent/5.0",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 200,
        }
        if tools_payload:
            payload["tools"] = tools_payload

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return f"Sarvam LLM returned status {resp.status}."
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]["message"]

                # Handle tool calls
                if "tool_calls" in choice and choice["tool_calls"]:
                    tool_call = choice["tool_calls"][0]
                    func = tool_call.get("function", {})
                    func_name = func.get("name", "")
                    try:
                        func_args = json.loads(func.get("arguments", "{}"))
                    except Exception:
                        func_args = {}

                    tool_exec_result = self.tool_registry.execute_tool(func_name, func_args)
                    if not (tool_exec_result.success and tool_exec_result.verified):
                        reasoning_res = self.reasoner.reason_and_execute(
                            user_query=user_message,
                            initial_action=(func_name, func_args),
                        )
                        return reasoning_res.to_voice_summary()
                    return tool_exec_result.to_voice_summary()

                reply = choice.get("content", "").strip()
                # Strip think tags if model generates reasoning tokens
                clean_reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
                return clean_reply or "I processed your request."

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "Authentication failed for Sarvam AI. Please check your SARVAM_API_KEY in .env."
            elif e.code == 429:
                return "Sarvam AI rate limit reached. Please try again in a few moments."
            elif e.code >= 500:
                return "The Sarvam AI cloud service is currently experiencing issues."
            return f"Sarvam API request returned error code {e.code}."
        except urllib.error.URLError:
            offline = self._execute_offline_intent(user_message)
            if offline:
                return offline
            return "Unable to connect to Sarvam AI. Running in offline fallback mode."
        except TimeoutError:
            return "The Sarvam AI service timed out. Please try again."
        except Exception as e:
            offline = self._execute_offline_intent(user_message)
            if offline:
                return offline
            return f"Sarvam encountered an error: {str(e)}"


class BackendFactory:
    """
    Factory for instantiating the configured AgentBackend:
    - 'direct' -> DirectModelBackend (DirectModelRouter)
    - 'harness' -> DeepSeekHarnessBackend
    - 'uncensored' -> UncensoredR1Backend
    - 'sarvam' -> SarvamLLMBackend (optional conversational adapter)
    """

    @staticmethod
    def create_backend(
        backend_type: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
        **kwargs: Any,
    ) -> AgentBackend:
        b_type = (backend_type or settings.AGENT_BACKEND or "direct").strip().lower()
        reg = tool_registry or ToolRegistry()

        if b_type in ("sarvam", "sarvam_llm", "sarvam-llm", "sarvam-105b", "sarvam-conversations"):
            return SarvamLLMBackend(tool_registry=reg, **kwargs)
        elif b_type in ("harness", "deepseek_harness", "deepseek-harness"):
            return DeepSeekHarnessBackend(tool_registry=reg, **kwargs)
        elif b_type in ("uncensored", "uncensored_r1", "uncensored-r1", "r1"):
            return UncensoredR1Backend(tool_registry=reg, **kwargs)
        elif b_type in ("direct", "direct_model", "direct-model"):
            from brain.router import DirectModelRouter
            return DirectModelRouter(tool_registry=reg, **kwargs)
        else:
            logger.warning(f"Unknown AGENT_BACKEND '{b_type}'. Defaulting to DirectModelBackend.")
            from brain.router import DirectModelRouter
            return DirectModelRouter(tool_registry=reg, **kwargs)

