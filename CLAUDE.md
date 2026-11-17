# CLAUDE PROJECT INSTRUCTIONS

## Objective
Complete tasks accurately while minimizing unnecessary usage, context consumption and repeated work.

## Working Rules
1. Understand the task before modifying anything.
2. Prepare a short plan before execution.
3. Use the least expensive suitable model.
4. Never use a more powerful model without a technical reason.
5. Keep responses concise and actionable.
6. Read only the files relevant to the task.
7. Do not repeatedly inspect unchanged files.
8. Avoid unnecessary web searches and tool calls.
9. Never invent test results or claim unverified success.
10. Preserve existing project architecture and functionality.

## Context Management
- Work on one clearly defined task at a time.
- Use compact summaries when context becomes large.
- Create a handoff before starting a new chat.
- Preserve important decisions and unresolved issues.
- Keep project instructions concise.

## Execution
- Plan first.
- Inspect before modifying.
- Make the smallest necessary changes.
- Run relevant tests.
- Report PASS/FAIL with evidence.
- Stop when acceptance criteria are satisfied.

## Memory
Update `MEMORY.md` with stable, useful project preferences and decisions over time. Do not store secrets, API keys or temporary logs.

## Completion Report Format
Always format completion reports with:
- **Objective**
- **Files changed**
- **Changes made**
- **Tests executed**
- **Actual results**
- **Remaining issues**
- **Exact next action**
