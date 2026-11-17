# Project Memory: DAKU

## System & Environment Preferences
- **Operating System**: Windows 10/11 (AMD64)
- **Hardware Profile**: AMD Athlon Silver 3050U with Radeon Graphics, ~3.44 GB Total RAM (Constrained memory profile).
- **Python Execution**: Use `py` (Python 3.13.9) or virtualenv path (`.\.venv-adk\Scripts\python.exe`). Note that raw `python` invokes a Microsoft Store alias on this system.
- **Node.js**: v22.23.2, npm 10.9.8.

## Architecture & Operational Constraints
- **Zero Local LLM Inference**: 100% cloud/remote-first design (<15 MB working set memory, <1% idle CPU). Never run heavy local models.
- **Core Loop**: Strict 5-stage lifecycle state machine (`PLANNING` -> `AWAITING_CONFIRMATION` -> `EXECUTING` -> `VERIFYING` -> `COMPLETED`) with max 10 steps and max 2 retries per step.
- **Safety & Permissions**: Model output never executes OS commands directly; actions route via 3-tier Permission Manager (`SAFE`, `CONFIRMATION_REQUIRED`, `BLOCKED`).
- **Tooling**: 4 native tools (`application_tool`, `browser_tool`, `file_tool`, `system_tool`) plus dynamically registered MCP servers.

## Code & Testing Protocols
- **Test Command**: `py -m unittest discover tests`
- **System Diagnostics**: `py doctor.py`
- **Graph Updates**: Run `graphify update .` after code modifications to maintain the knowledge graph.
- **Secrets Policy**: Never commit, log, or record API keys, tokens, or credentials in memory or repository files.
