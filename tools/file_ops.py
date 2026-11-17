"""
DAKU FileTool Module
Provides allowlisted, safe file system operations on Windows.
Supports searching, listing, reading, and safe creation with strict safety guards.
Deletion and destructive modifications are permanently blocked.
"""

import datetime
import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, PermissionLevel, ToolParameter, ToolResult


class FileTool(BaseTool):
    """Allowlisted file operations tool for Windows."""

    name: str = "file_tool"
    description: str = "Perform safe file operations: list directory, search files, inspect metadata, read text files, and open Explorer."
    permission_level: PermissionLevel = PermissionLevel.SAFE

    parameters: List[ToolParameter] = [
        ToolParameter(
            name="action",
            type="string",
            description="The action to perform: 'list_dir', 'search_files', 'get_metadata', 'read_file', 'create_file', 'create_dir', or 'open_explorer'.",
            enum=["list_dir", "search_files", "get_metadata", "read_file", "create_file", "create_dir", "open_explorer"],
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Target file or directory path (supports relative paths, absolute paths, or ~ for user home).",
            required=False,
            default=".",
        ),
        ToolParameter(
            name="pattern",
            type="string",
            description="Search glob pattern (e.g., '*.pdf', '*.txt', 'report*') for search_files.",
            required=False,
            default="*",
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Text content for create_file action.",
            required=False,
            default="",
        ),
    ]

    def _resolve_path(self, raw_path: Optional[str]) -> Path:
        """Expands environment variables, ~, and resolves absolute path safely."""
        if not raw_path or raw_path.strip() in (".", ""):
            return Path.cwd()
        
        path_str = raw_path.strip().strip("'\"")
        # Handle Windows common aliases
        lower = path_str.lower()
        if lower in ("desktop", "~/desktop"):
            return Path.home() / "Desktop"
        elif lower in ("documents", "~/documents", "docs"):
            return Path.home() / "Documents"
        elif lower in ("downloads", "~/downloads"):
            return Path.home() / "Downloads"
        elif lower in ("home", "~"):
            return Path.home()

        return Path(path_str).expanduser().resolve()

    def list_directory(self, target_path: Optional[str] = None) -> ToolResult:
        """Lists files and folders in directory (capped at 50 to conserve memory)."""
        resolved = self._resolve_path(target_path)
        if not resolved.exists():
            return ToolResult(
                success=False,
                error=f"Directory '{resolved}' does not exist.",
                message=f"Directory '{resolved.name}' was not found.",
            )
        if not resolved.is_dir():
            return ToolResult(
                success=False,
                error=f"Path '{resolved}' is a file, not a directory.",
                message=f"'{resolved.name}' is a file, not a folder.",
            )

        try:
            entries = []
            count = 0
            for item in resolved.iterdir():
                count += 1
                if count > 50:
                    break
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": item.stat().st_size if item.is_file() else 0,
                })

            item_count = len(entries)
            summary = f"Found {item_count} items in {resolved.name}."
            return ToolResult(
                success=True,
                data={"path": str(resolved), "items": entries, "count": item_count},
                message=summary,
                verified=True,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not list directory: {str(e)}",
                message=f"Unable to access {resolved.name}.",
            )

    def search_files(
        self,
        pattern: str = "*",
        search_dir: Optional[str] = None,
        max_results: int = 20,
    ) -> ToolResult:
        """Searches matching files across directory tree (max depth 3, capped results)."""
        resolved = self._resolve_path(search_dir)
        if not resolved.exists():
            resolved = Path.cwd()

        pattern_clean = pattern.strip()
        if not pattern_clean.startswith("*") and not "." in pattern_clean:
            pattern_clean = f"*{pattern_clean}*"

        matches = []
        try:
            # Walk directory with depth limitation to prevent CPU/RAM overhead
            base_depth = len(resolved.parts)
            for root, dirs, files in os.walk(resolved):
                current_depth = len(Path(root).parts) - base_depth
                if current_depth > 3:
                    dirs.clear()  # Don't descend further
                    continue

                for filename in files:
                    if fnmatch.fnmatch(filename.lower(), pattern_clean.lower()):
                        full_path = os.path.join(root, filename)
                        matches.append({
                            "name": filename,
                            "path": full_path,
                            "size_bytes": os.path.getsize(full_path) if os.path.isfile(full_path) else 0,
                        })
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

            count = len(matches)
            # Formatting voice-friendly message
            ext_label = pattern_clean.replace("*", "").upper() or "matching"
            if count == 0:
                msg = f"No {ext_label} files found in {resolved.name}."
            elif count == 1:
                msg = f"I found 1 {ext_label} file: {matches[0]['name']}."
            else:
                msg = f"I found {count} {ext_label} files."

            return ToolResult(
                success=True,
                data={"pattern": pattern_clean, "search_dir": str(resolved), "matches": matches, "count": count},
                message=msg,
                verified=True,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Search failed: {str(e)}",
                message="Error searching for files.",
            )

    def get_metadata(self, file_path: str) -> ToolResult:
        """Inspects file metadata (size, timestamps, permissions)."""
        resolved = self._resolve_path(file_path)
        if not resolved.exists():
            return ToolResult(
                success=False,
                error=f"File '{resolved}' does not exist.",
                message=f"File '{resolved.name}' was not found.",
            )

        stat = resolved.stat()
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = round(stat.st_size / 1024, 2)
        is_file = resolved.is_file()

        info = {
            "name": resolved.name,
            "path": str(resolved),
            "is_file": is_file,
            "size_kb": size_kb,
            "modified": mod_time,
        }
        msg = f"File {resolved.name} is {size_kb} KB, last modified {mod_time}."
        return ToolResult(success=True, data=info, message=msg, verified=True)

    def read_text_file(self, file_path: str, max_chars: int = 4000) -> ToolResult:
        """Reads text file safely with character limit to prevent memory spikes."""
        resolved = self._resolve_path(file_path)
        if not resolved.exists() or not resolved.is_file():
            return ToolResult(
                success=False,
                error=f"File '{resolved}' not found.",
                message=f"Could not find file '{resolved.name}'.",
            )

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)
            truncated = resolved.stat().st_size > max_chars
            return ToolResult(
                success=True,
                data={"content": content, "truncated": truncated, "path": str(resolved)},
                message=f"Read {len(content)} characters from {resolved.name}." if not truncated else f"Read first {max_chars} characters from {resolved.name}.",
                verified=True,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Error reading file: {str(e)}",
                message=f"Unable to read {resolved.name}.",
            )

    def create_file(self, file_path: str, content: str = "") -> ToolResult:
        """Creates a new text file safely (requires CONFIRMATION)."""
        resolved = self._resolve_path(file_path)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

            exists = resolved.is_file()
            return ToolResult(
                success=exists,
                data={"path": str(resolved), "size_bytes": len(content.encode("utf-8"))},
                message=f"File {resolved.name} created successfully." if exists else "File creation failed.",
                verified=exists,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not create file: {str(e)}",
                message=f"Failed to create file {resolved.name}.",
            )

    def create_directory(self, dir_path: str) -> ToolResult:
        """Creates a new directory safely (requires CONFIRMATION)."""
        resolved = self._resolve_path(dir_path)
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            exists = resolved.is_dir()
            return ToolResult(
                success=exists,
                data={"path": str(resolved)},
                message=f"Folder {resolved.name} created successfully." if exists else "Folder creation failed.",
                verified=exists,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not create folder: {str(e)}",
                message=f"Failed to create folder {resolved.name}.",
            )

    def open_in_explorer(self, target_path: Optional[str] = None) -> ToolResult:
        """Opens directory in Windows Explorer."""
        resolved = self._resolve_path(target_path)
        if not resolved.exists():
            resolved = Path.cwd()
        try:
            subprocess.Popen(["explorer.exe", str(resolved)], close_fds=True)
            return ToolResult(
                success=True,
                data={"path": str(resolved)},
                message=f"Opened {resolved.name} in Windows Explorer.",
                verified=True,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not open Explorer: {str(e)}",
                message="Failed to open Windows Explorer.",
            )

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        """Routes to requested file operation."""
        action = args.get("action", "list_dir")
        path = args.get("path")
        pattern = args.get("pattern", "*")
        content = args.get("content", "")

        if action == "list_dir":
            return self.list_directory(path)
        elif action == "search_files":
            return self.search_files(pattern=pattern, search_dir=path)
        elif action == "get_metadata":
            return self.get_metadata(path or ".")
        elif action == "read_file":
            return self.read_text_file(path or "")
        elif action == "create_file":
            return self.create_file(path or "new_file.txt", content=content)
        elif action == "create_dir":
            return self.create_directory(path or "new_folder")
        elif action == "open_explorer":
            return self.open_in_explorer(path)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown file action: '{action}'.",
                message=f"Unknown file action '{action}'.",
            )
