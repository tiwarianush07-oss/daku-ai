"""
DAKU Brain & Model Router Module
Phase 3: Multi-Step Task Automation with TaskPlanner, Browser Tool, MCP & ToolRouter.
Integrates ToolRegistry, 3-tier permission checks, Task State Machine, real system execution,
and voice-friendly response synthesis.
"""

import json
import logging
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from brain.backend import AgentBackend
from brain.multipass import MultiPassReasoner
from config.settings import settings
from tools.base import ToolResult
from tools.planner import TaskPlanner, TaskState
from tools.registry import ToolRegistry

logger = logging.getLogger("daku.brain")


DAKU_SYSTEM_PROMPT = """You are DAKU, a lightweight personal voice AI assistant and task automation agent for Windows.
Rules:
1. Keep responses short, natural, helpful, voice-friendly, and action-oriented (1 to 2 sentences max).
2. Support English, Hindi, and Hinglish naturally.
3. When the user asks to perform an action (open an application, open browser, navigate URL, check page title, find files, check RAM/CPU, list files), use the available tools.
4. Never falsely claim that an action was executed if it was not. Always report the verified result.
5. Do not output markdown code blocks or long explanations unless specifically asked.
"""


class DirectModelRouter(AgentBackend):
    """
    Direct Cloud Model Router implementing OpenAI-compatible Chat Completions API with Tool Calling and TaskPlanner.
    Supports DeepSeek, OpenAI, Groq, Qwen, and safe offline deterministic intent execution.
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
        self.base_url = (base_url or settings.MODEL_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.MODEL_API_KEY
        self.model_name = model_name or settings.MODEL_NAME
        self.timeout = timeout
        self.tool_registry = tool_registry or ToolRegistry()
        self.planner = TaskPlanner(tool_registry=self.tool_registry)
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)

    def _execute_offline_intent(self, user_message: str) -> Optional[str]:
        """
        Parses user intent locally for offline demo, multi-step tasks, and test execution.
        Routes to TaskPlanner / ToolRegistry to execute real multi-step tasks and query real hardware.
        """
        msg = user_message.strip().lower().rstrip(".!?,")

        # 1. Multi-Step / Browser Task Detection (e.g., "open Chrome and open bhartiyarishtey.com", "open Chrome, go to bhartiyarishtey.com and tell me the page title")
        has_browser_or_url = any(w in msg for w in ("chrome", "browser", "edge", ".com", ".org", ".in", ".net", "http", "google", "website", "webpage"))
        has_compound = any(w in msg for w in (" and ", " aur ", " then ", "tell me", "title", "page title", "heading"))
        
        if (has_browser_or_url and (has_compound or "google" in msg or ".com" in msg or ".in" in msg or ".org" in msg)) or (" and " in msg or " aur " in msg):
            plan = self.planner.create_plan(user_message)
            if plan.steps:
                exec_res = self.planner.execute_plan(plan)
                return exec_res.get("message")

        # 2. Single Application Launch Intent ("open notepad", "launch calc", "notepad kholo", "open chrome", etc.)
        open_match = re.search(r"(?:open|launch|start|chalu karo|kholo)\s+([a-zA-Z0-9\s\.\:\-_/]+)", msg)
        kholo_match = re.search(r"([a-zA-Z0-9\s\.\:\-_/]+)\s+(?:kholo|chalu karo|open karo)", msg)
        app_candidate = None

        if open_match:
            app_candidate = open_match.group(1).strip()
        elif kholo_match:
            app_candidate = kholo_match.group(1).strip()

        if app_candidate:
            # Clean candidate
            app_name = app_candidate.replace("app", "").replace("application", "").strip().rstrip(".!?,")

            # Filter known desktop apps first
            if app_name in ("notepad", "calc", "calculator", "paint", "mspaint", "explorer", "cmd", "powershell", "edge", "chrome", "code", "taskmgr", "task manager"):
                res = self.tool_registry.execute_tool("application_tool", {"action": "launch", "app_name": app_name})
                return res.to_voice_summary()

            # Check if app candidate is a website domain (e.g., "open google.com", "open bhartiyarishtey.com", "open google")
            if "." in app_name or app_name in ("google", "youtube", "github", "bing"):
                url = app_name if app_name.startswith("http") else f"https://www.{app_name}.com" if "." not in app_name else app_name
                res = self.tool_registry.execute_tool("browser_tool", {"action": "navigate", "url": url})
                return res.to_voice_summary()

        # 3. Check if App is Running ("is notepad running", "check notepad")
        running_match = re.search(r"is\s+([a-zA-Z0-9\s]+)\s+running", msg)
        if running_match:
            app_name = running_match.group(1).strip()
            res = self.tool_registry.execute_tool("application_tool", {"action": "is_running", "app_name": app_name})
            return res.to_voice_summary()

        # 4. File Search Intent ("find my pdf files", "search for pdf", "pdf dhundo")
        if "find" in msg or "search" in msg or "dhundo" in msg:
            pattern = "*.pdf" if "pdf" in msg else "*.txt" if "txt" in msg or "text" in msg else "*"
            match = re.search(r"(?:find|search for|search|dhundo)\s+(?:my\s+)?([a-zA-Z0-9_\-\.\*]+)", msg)
            if match and "." in match.group(1):
                pattern = match.group(1)
            elif "pdf" in msg:
                pattern = "*.pdf"
            elif "txt" in msg or "text" in msg:
                pattern = "*.txt"

            res = self.tool_registry.execute_tool("file_tool", {"action": "search_files", "pattern": pattern})
            return res.to_voice_summary()

        # 5. System Info: RAM / Memory
        if any(w in msg for w in ("ram", "memory")):
            res = self.tool_registry.execute_tool("system_tool", {"query": "ram"})
            return res.to_voice_summary()

        # 6. System Info: CPU / Processor
        if any(w in msg for w in ("cpu", "processor")):
            res = self.tool_registry.execute_tool("system_tool", {"query": "cpu"})
            return res.to_voice_summary()

        # 7. System Info: Disk / Storage
        if any(w in msg for w in ("disk", "storage", "hard drive", "space")):
            res = self.tool_registry.execute_tool("system_tool", {"query": "disk"})
            return res.to_voice_summary()

        # 8. System Info: Time / Date
        if any(w in msg for w in ("time", "date", "clock", "samay", "kya time")):
            res = self.tool_registry.execute_tool("system_tool", {"query": "time"})
            return res.to_voice_summary()

        # 9. System Info: Windows / OS
        if any(w in msg for w in ("windows version", "os version", "operating system")):
            res = self.tool_registry.execute_tool("system_tool", {"query": "windows_ver"})
            return res.to_voice_summary()

        # 10. File Listing Intent ("list files", "directory content")
        if "list files" in msg or "list directory" in msg or "files dikhao" in msg:
            res = self.tool_registry.execute_tool("file_tool", {"action": "list_dir"})
            return res.to_voice_summary()

        # 11. File Reading Intent ("read file <name>", "view file <name>")
        read_match = re.search(r"(?:read|view|open file|padho)\s+([a-zA-Z0-9_\-\./\\]+)", msg)
        if read_match:
            filename = read_match.group(1).strip()
            res = self.tool_registry.execute_tool("file_tool", {"action": "read_file", "path": filename})
            return res.to_voice_summary()

        return None

    def _generate_mock_response(self, user_message: str) -> str:
        """
        Deterministic mock and tool execution for Phase 1/1.5/2/3 tests and offline mode.
        """
        tool_result = self._execute_offline_intent(user_message)
        if tool_result:
            return tool_result

        msg = user_message.strip().lower()
        if "hello daku" in msg or "hi daku" in msg or "hey daku" in msg or msg in ("hello", "hi"):
            return "Hello. I'm DAKU. How can I help?"
        elif "kaise ho" in msg or "how are you" in msg:
            return "Main badhiya hoon! Aap bataiye, main aapki kya madad kar sakta hoon?"
        elif "who are you" in msg or "tum kaun ho" in msg:
            return "I am DAKU, your personal Windows voice assistant and task automation agent."
        else:
            return "DAKU is running in offline demo mode. Configure an AI provider to enable cloud intelligence."

    def process_message(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Process user query via Cloud LLM with tool calling or graceful offline fallback.
        """
        if not user_message or not user_message.strip():
            return "I didn't catch that. Please try again."

        # Offline fallback or mock tool execution if API key is not configured
        if not self.api_key or not self.api_key.strip() or self.api_key == "your_api_key_here":
            return self._generate_mock_response(user_message)

        # First check multi-step planner
        plan = self.planner.create_plan(user_message)
        if len(plan.steps) > 1:
            exec_res = self.planner.execute_plan(plan)
            if exec_res.get("success"):
                return exec_res.get("message", "Task completed.")

        # Prepare messages payload
        messages = [{"role": "system", "content": DAKU_SYSTEM_PROMPT}]
        if conversation_history:
            for turn in conversation_history[-6:]:  # Keep short window for low memory & token efficiency
                messages.append(turn)
        messages.append({"role": "user", "content": user_message})

        # Format OpenAI-compatible tools parameter
        tools_payload = []
        for schema in self.tool_registry.get_schemas():
            tools_payload.append({
                "type": "function",
                "function": schema,
            })

        # Ensure correct endpoint URL
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "DAKU-Voice-Agent/3.0",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.5,
            "stream": False,
        }
        if tools_payload:
            payload["tools"] = tools_payload

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return f"Error: Received status code {resp.status} from model provider."
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]["message"]

                # Handle tool calls returned by the model
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
                return reply or "I processed your request."

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "Authentication failed. Please check your MODEL_API_KEY in .env."
            elif e.code == 429:
                return "Model rate limit reached. Please try again in a few moments."
            elif e.code >= 500:
                return "The cloud AI provider is currently experiencing server issues."
            return f"API request returned error code {e.code}."
        except urllib.error.URLError:
            # Network disconnection: fallback to local intent execution
            local_fallback = self._execute_offline_intent(user_message)
            if local_fallback:
                return local_fallback
            return "Unable to connect to the AI cloud service. Running in offline fallback mode."
        except TimeoutError:
            return "The AI service timed out. Please try again."
        except Exception as e:
            # On unexpected API payload format or error, attempt offline intent parsing
            local_fallback = self._execute_offline_intent(user_message)
            if local_fallback:
                return local_fallback
            return f"An unexpected error occurred: {str(e)}"


# Backward and forward compatibility alias
DirectModelBackend = DirectModelRouter


class Brain:
    """Core reasoning brain of DAKU with integrated ToolRegistry, TaskPlanner, and AgentBackend."""

    def __init__(
        self,
        backend: Optional[AgentBackend] = None,
        tool_registry: Optional[ToolRegistry] = None,
        reasoner: Optional[MultiPassReasoner] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.reasoner = reasoner or MultiPassReasoner(tool_registry=self.tool_registry)
        if backend is not None:
            self.backend = backend
        else:
            from brain.backend import BackendFactory
            self.backend = BackendFactory.create_backend(settings.AGENT_BACKEND, tool_registry=self.tool_registry)
        self.history: List[Dict[str, str]] = []

    def think(self, user_text: str) -> str:
        """Takes transcribed text, consults backend/planner, executes tools, and returns spoken response."""
        response = self.backend.process_message(user_text, self.history)
        # Store clean interaction history (limit to last 6 turns)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > 12:
            self.history = self.history[-12:]
        return response
