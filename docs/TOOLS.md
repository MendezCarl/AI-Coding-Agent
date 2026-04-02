# Tool Catalog and Contracts

## Principles

- Keep each tool focused and deterministic.
- Restrict filesystem and command execution to AGENT_ROOT.
- Return structured status objects for predictable callers.

## Core Tool Areas

1. File tools
- read.py: read file with optional line bounds.
- write.py: atomic write with optional backup.
- apply_patch.py: exact-text replacement patching.
- list_dir.py: directory listing with hidden-file control.
- grep_search.py: plain or regex search with limits.

2. Execution and diagnostics
- run.py: command execution with timeout and safety blocklist.
- diagnostics.py: Python syntax checks.

3. Git tools
- git_status.py: concise repository status.
- git_diff.py: staged/unstaged diff output.

4. Web and retrieval
- web_search.py: web search with domain filters.
- safe_fetch.py: guarded fetching with SSRF policy checks.
- vector_index.py, vector_chroma.py: semantic storage/query.

5. Staging
- staging.py: proposal queue with TTL, states, and approval flow.

## Guardrail Expectations

- All tool inputs are validated via request models.
- Return shape should include status and error message on failure.
- Side-effecting tools should include clear traceable metadata.
