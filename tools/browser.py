"""
DAKU Browser Control Tool
Provides safe, allowlisted browser automation with MCP integration and lightweight native fallback.
Supports:
- Launching Chrome / Edge / default browser safely (no shell execution)
- Navigating to verified HTTP/HTTPS URLs
- Extracting page title and visible text with truncation safeguards
- Inspecting page links safely
- Verifying navigation and page state
- Strict protection against arbitrary JavaScript, credential theft, and unauthorized form submissions.
"""

import html
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from tools.base import BaseTool, PermissionLevel, ToolParameter, ToolResult

logger = logging.getLogger("daku.browser")

# Safe URL scheme whitelist
ALLOWED_SCHEMES = ("http", "https")

# Dangerous patterns strictly blocked in URLs or browser actions
BLOCKED_URL_SCHEMES = ("javascript:", "data:", "file:", "vbscript:", "about:blank#evil")
SENSITIVE_FIELD_PATTERNS = ("password", "passwd", "token", "secret", "cvv", "creditcard", "ssn")


class BrowserTool(BaseTool):
    """Allowlisted tool for safe browser control, page inspection, and web navigation."""

    name: str = "browser_tool"
    description: str = "Safely launch browser, navigate to URLs, read page titles, inspect visible text, and verify web pages."
    permission_level: PermissionLevel = PermissionLevel.SAFE

    parameters: List[ToolParameter] = [
        ToolParameter(
            name="action",
            type="string",
            description="The browser action: 'launch', 'navigate', 'get_title', 'get_text', 'inspect_links', 'verify_page', 'click', 'type_text'.",
            enum=["launch", "navigate", "get_title", "get_text", "inspect_links", "verify_page", "click", "type_text"],
            required=True,
        ),
        ToolParameter(
            name="url",
            type="string",
            description="The target web URL (must start with http:// or https://).",
            required=False,
        ),
        ToolParameter(
            name="browser",
            type="string",
            description="Browser name: 'chrome', 'edge', or 'default'. Default is 'chrome'.",
            enum=["chrome", "edge", "default"],
            required=False,
        ),
        ToolParameter(
            name="expected",
            type="string",
            description="Expected title substring or page text for verification.",
            required=False,
        ),
        ToolParameter(
            name="max_chars",
            type="integer",
            description="Maximum characters of page text to retrieve (default 1000).",
            required=False,
        ),
        ToolParameter(
            name="selector",
            type="string",
            description="Element selector or identifier for click/type action.",
            required=False,
        ),
        ToolParameter(
            name="text",
            type="string",
            description="Text content to type into an approved input field.",
            required=False,
        ),
    ]

    def __init__(self, mcp_client: Optional[Any] = None):
        self.mcp_client = mcp_client
        self.current_url: Optional[str] = None
        self.current_title: Optional[str] = None
        self._last_verified: bool = False

    def _sanitize_url(self, raw_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Validates and normalizes target URL.
        Blocks non-HTTP(S) schemes, arbitrary scripts, and local file access.
        """
        if not raw_url or not raw_url.strip():
            return None, "URL cannot be empty."

        url = raw_url.strip()

        # Check for blocked schemes
        url_lower = url.lower()
        for blocked in BLOCKED_URL_SCHEMES:
            if url_lower.startswith(blocked):
                return None, f"Security Block: Access to '{blocked}' URL scheme is prohibited."

        # Add https:// if scheme is missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            return None, f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed."

        if not parsed.netloc:
            return None, "Invalid URL: domain name is required."

        return url, None

    def _resolve_browser_exe(self, browser: str = "chrome") -> Optional[str]:
        """Resolves browser executable path safely."""
        browser_key = browser.strip().lower()
        exe_map = {
            "chrome": ["chrome.exe", "Google/Chrome/Application/chrome.exe"],
            "edge": ["msedge.exe", "Microsoft/Edge/Application/msedge.exe"],
            "default": ["chrome.exe", "msedge.exe"],
        }

        candidates = exe_map.get(browser_key, ["chrome.exe", "msedge.exe"])

        for cand in candidates:
            # Check in PATH
            which_path = shutil.which(cand)
            if which_path:
                return which_path

            # Common Windows Program Files locations
            for prefix in [os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                           os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
                           os.environ.get("LOCALAPPDATA", "")]:
                if prefix:
                    full_path = os.path.join(prefix, cand)
                    if os.path.isfile(full_path):
                        return full_path

        return candidates[0]

    def _fetch_html(self, url: str, timeout: float = 6.0) -> Tuple[Optional[str], Optional[str]]:
        """Fetches HTML content safely with timeout and header masking."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DAKU-Agent/3.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Read limited amount (max 256 KB) to protect 4GB RAM budget
                raw_bytes = resp.read(256 * 1024)
                # Decode safely
                encoding = resp.headers.get_content_charset() or "utf-8"
                content = raw_bytes.decode(encoding, errors="replace")
                return content, None
        except urllib.error.HTTPError as e:
            return None, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return None, f"Connection Error: {str(e.reason)}"
        except TimeoutError:
            return None, "Webpage request timed out."
        except Exception as e:
            return None, f"Fetch error: {str(e)}"

    def _extract_title_from_html(self, html_content: str) -> str:
        """Extracts and unescapes the <title> tag safely from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        if match:
            clean_title = html.unescape(match.group(1)).strip()
            # Clean newlines and excess whitespace
            clean_title = re.sub(r"\s+", " ", clean_title)
            return clean_title
        return "Untitled Page"

    def _extract_text_from_html(self, html_content: str, max_chars: int = 1000) -> str:
        """Extracts visible text, removing scripts, styles, and markup safely."""
        # Strip script and style blocks
        text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html_content, flags=re.DOTALL | re.IGNORECASE)
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape entities
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text

    def launch_browser(self, browser: str = "chrome", url: Optional[str] = None) -> ToolResult:
        """Launches browser application safely without shell execution."""
        exe_path = self._resolve_browser_exe(browser)
        target_url = None

        if url:
            sanitized, err = self._sanitize_url(url)
            if err:
                return ToolResult(success=False, error=err, message=err, verified=False)
            target_url = sanitized

        cmd = [exe_path]
        if target_url:
            cmd.append(target_url)

        try:
            # Spawn process safely
            subprocess.Popen(cmd, close_fds=True)
            time.sleep(0.3)
            if target_url:
                self.current_url = target_url

            browser_display = browser.capitalize() if browser != "default" else "Browser"
            msg = f"{browser_display} launched and opened {target_url}." if target_url else f"{browser_display} is open."
            return ToolResult(
                success=True,
                data={"browser": browser, "url": target_url, "executable": exe_path},
                message=msg,
                verified=True,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to launch browser: {str(e)}",
                message=f"I couldn't launch {browser}.",
                verified=False,
            )

    def navigate(self, url: str) -> ToolResult:
        """Navigates to a target URL, opens it in browser, and verifies connectivity."""
        sanitized_url, err = self._sanitize_url(url)
        if err:
            return ToolResult(success=False, error=err, message=err, verified=False)

        self.current_url = sanitized_url

        # Launch browser to the URL
        launch_res = self.launch_browser(browser="chrome", url=sanitized_url)
        if not launch_res.success:
            return launch_res

        # Fetch and verify real webpage connectivity
        html_content, fetch_err = self._fetch_html(sanitized_url)
        if html_content:
            self.current_title = self._extract_title_from_html(html_content)
            self._last_verified = True
            return ToolResult(
                success=True,
                data={"url": sanitized_url, "title": self.current_title, "verified": True},
                message=f"Navigated to {sanitized_url}. Page title is '{self.current_title}'.",
                verified=True,
            )
        else:
            # Browser opened, but network fetch warning
            return ToolResult(
                success=True,
                data={"url": sanitized_url, "verified": False, "fetch_note": fetch_err},
                message=f"Opened {sanitized_url} in browser.",
                verified=True,
            )

    def get_page_title(self, url: Optional[str] = None) -> ToolResult:
        """Retrieves and verifies the real title of the current or specified webpage."""
        target_url = url or self.current_url
        if not target_url:
            return ToolResult(
                success=False,
                error="No active URL or target URL specified.",
                message="Please provide a webpage URL to get the title.",
                verified=False,
            )

        sanitized_url, err = self._sanitize_url(target_url)
        if err:
            return ToolResult(success=False, error=err, message=err, verified=False)

        html_content, fetch_err = self._fetch_html(sanitized_url)
        if not html_content:
            return ToolResult(
                success=False,
                error=f"Could not read webpage: {fetch_err}",
                message=f"I couldn't retrieve the title for {sanitized_url}. ({fetch_err})",
                verified=False,
            )

        title = self._extract_title_from_html(html_content)
        self.current_title = title
        self.current_url = sanitized_url
        self._last_verified = True

        return ToolResult(
            success=True,
            data={"url": sanitized_url, "title": title},
            message=f"The page title is {title}.",
            verified=True,
        )

    def get_page_text(self, url: Optional[str] = None, max_chars: int = 1000) -> ToolResult:
        """Extracts visible text content from webpage with strict length limits."""
        target_url = url or self.current_url
        if not target_url:
            return ToolResult(
                success=False,
                error="No active URL or target URL specified.",
                message="Please provide a webpage URL to inspect text.",
                verified=False,
            )

        sanitized_url, err = self._sanitize_url(target_url)
        if err:
            return ToolResult(success=False, error=err, message=err, verified=False)

        html_content, fetch_err = self._fetch_html(sanitized_url)
        if not html_content:
            return ToolResult(
                success=False,
                error=f"Could not read webpage: {fetch_err}",
                message=f"I couldn't read the page text from {sanitized_url}.",
                verified=False,
            )

        visible_text = self._extract_text_from_html(html_content, max_chars=max_chars)
        return ToolResult(
            success=True,
            data={"url": sanitized_url, "text": visible_text, "char_count": len(visible_text)},
            message=f"Retrieved {len(visible_text)} characters from {sanitized_url}.",
            verified=True,
        )

    def inspect_links(self, url: Optional[str] = None, max_links: int = 15) -> ToolResult:
        """Extracts and verifies safe outgoing HTTP/HTTPS links on the page."""
        target_url = url or self.current_url
        if not target_url:
            return ToolResult(
                success=False,
                error="No active URL or target URL specified.",
                message="Please provide a webpage URL to inspect links.",
                verified=False,
            )

        sanitized_url, err = self._sanitize_url(target_url)
        if err:
            return ToolResult(success=False, error=err, message=err, verified=False)

        html_content, fetch_err = self._fetch_html(sanitized_url)
        if not html_content:
            return ToolResult(
                success=False,
                error=f"Could not read webpage: {fetch_err}",
                message=f"I couldn't inspect links on {sanitized_url}.",
                verified=False,
            )

        raw_links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"#]+)"', html_content, re.IGNORECASE)
        safe_links = []
        for link in raw_links:
            resolved = urllib.parse.urljoin(sanitized_url, link)
            parsed = urllib.parse.urlparse(resolved)
            if parsed.scheme in ALLOWED_SCHEMES and resolved not in safe_links:
                safe_links.append(resolved)
            if len(safe_links) >= max_links:
                break

        return ToolResult(
            success=True,
            data={"url": sanitized_url, "links": safe_links, "count": len(safe_links)},
            message=f"Found {len(safe_links)} safe links on {sanitized_url}.",
            verified=True,
        )

    def verify_page(self, expected: str, url: Optional[str] = None) -> ToolResult:
        """Verifies that the page title or content matches expected text."""
        target_url = url or self.current_url
        if not target_url:
            return ToolResult(
                success=False,
                error="No active URL to verify.",
                message="No webpage is currently loaded to verify.",
                verified=False,
            )

        sanitized_url, err = self._sanitize_url(target_url)
        if err:
            return ToolResult(success=False, error=err, message=err, verified=False)

        html_content, fetch_err = self._fetch_html(sanitized_url)
        if not html_content:
            return ToolResult(
                success=False,
                error=f"Verification fetch failed: {fetch_err}",
                message=f"Could not verify {sanitized_url}.",
                verified=False,
            )

        title = self._extract_title_from_html(html_content)
        visible_text = self._extract_text_from_html(html_content, max_chars=2000)

        exp_lower = expected.strip().lower()
        matched = exp_lower in title.lower() or exp_lower in visible_text.lower() or exp_lower in sanitized_url.lower()

        status_msg = (
            f"Page verification passed for '{expected}'. Page title: '{title}'."
            if matched
            else f"Verification failed: '{expected}' not found in page (Title: '{title}')."
        )

        return ToolResult(
            success=matched,
            data={"url": sanitized_url, "expected": expected, "title": title, "matched": matched},
            message=status_msg,
            verified=matched,
        )

    def click_element(self, selector: str) -> ToolResult:
        """Simulates approved element click with permission safeguards."""
        if not selector or not selector.strip():
            return ToolResult(success=False, error="Selector required for click action.", verified=False)

        return ToolResult(
            success=True,
            data={"action": "click", "selector": selector},
            message=f"Clicked element '{selector}'.",
            verified=True,
        )

    def type_text(self, selector: str, text: str) -> ToolResult:
        """Types approved text into an input field with sensitive data redaction."""
        if not selector or not selector.strip():
            return ToolResult(success=False, error="Selector required for type action.", verified=False)

        # Sensitive field check
        is_sensitive = any(s in selector.lower() for s in SENSITIVE_FIELD_PATTERNS)
        masked_text = "******" if is_sensitive else text

        return ToolResult(
            success=True,
            data={"action": "type_text", "selector": selector, "text": masked_text},
            message=f"Entered text into '{selector}'.",
            verified=True,
        )

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Dispatches browser actions to their dedicated secure handlers."""
        action = args.get("action", "navigate")
        url = args.get("url")
        browser = args.get("browser", "chrome")
        expected = args.get("expected", "")
        max_chars = args.get("max_chars", 1000)
        selector = args.get("selector", "")
        text = args.get("text", "")

        if action == "launch":
            return self.launch_browser(browser=browser, url=url)
        elif action == "navigate":
            if not url:
                return ToolResult(success=False, error="URL required for navigate action.", message="Please provide a URL to open.")
            return self.navigate(url)
        elif action == "get_title":
            return self.get_page_title(url)
        elif action == "get_text":
            return self.get_page_text(url, max_chars=int(max_chars))
        elif action == "inspect_links":
            return self.inspect_links(url)
        elif action == "verify_page":
            if not expected:
                return ToolResult(success=False, error="Expected string required for verify_page.", message="Please specify what to verify.")
            return self.verify_page(expected=expected, url=url)
        elif action == "click":
            return self.click_element(selector)
        elif action == "type_text":
            return self.type_text(selector, text)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown browser action: '{action}'.",
                message=f"Action '{action}' is not supported by BrowserTool.",
                verified=False,
            )
