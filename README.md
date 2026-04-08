# AI Agent Server

A local AI coding agent built on [FastAPI](https://fastapi.tiangolo.com/) and [Ollama](https://ollama.com/). It exposes an HTTP API for natural language prompts and a full suite of file, git, shell, web, and vector-search tools — all sandboxed to the project directory.

---

## Features

- **`/ask`** — Send a prompt to a local LLM (Ollama). Automatically enriches the prompt with relevant context from the vector knowledge base before sending.
- **File tools** — Read, write, patch, and list files; grep search with regex support.
- **Git tools** — `git status` and `git diff` (staged or unstaged) over the repo.
- **Shell tool** — Run arbitrary commands inside the agent root with a configurable timeout and a blocklist for dangerous commands.
- **Diagnostics** — Syntax-check up to 500 Python files at once.
- **Web tools** — DuckDuckGo search and safe HTML fetching. Both validate URLs against an SSRF blocklist (no localhost, private IPs, or cloud metadata endpoints).
- **Vector knowledge base** — ChromaDB-backed semantic index (`all-MiniLM-L6-v2` embeddings). Supports creating indexes, upserting documents, topic-filtered queries, and topic deletion.
- **Staging / proposal workflow** — A SQLite-backed human-in-the-loop review queue. Documents (including web results) are staged as proposals with a TTL before being approved into the vector index.
- **Security sandbox** — Every file and shell operation is restricted to `AGENT_ROOT` (the working directory when the server starts). Path traversal attempts are rejected.

---

## Requirements

| Dependency | Notes |
|---|---|
| Python 3.10+ | |
| [Ollama](https://ollama.com/download) | Runs the LLM locally |
| `qwen2.5-coder:7b` model | Pulled via `ollama pull` |
| Python packages | Listed in `requirements.txt` |

---

## Installation

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd ai-agent

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Ollama (visit https://ollama.com/download for your OS)
# Then pull the model:
ollama pull qwen2.5-coder:7b
```

---

## Running the Server

Make sure Ollama is running, then start the agent:

```bash
uvicorn agent:app --reload
```

The server starts at `http://127.0.0.1:8000`.

- Interactive API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

> **Note:** The server must be started from the project root. `AGENT_ROOT` is captured from the working directory at startup — all file and shell operations are sandboxed to this path.

---

## API Overview

### `POST /ask`

Send a prompt to the LLM. Optionally queries the vector index for relevant context first.

```json
{
  "prompt": "How do I add a new tool endpoint?",
    "session_id": "optional-session-id",
        "session_context_turns": 8,
    "use_instructions": true,
        "include_legacy_instruction_docs": false,
  "use_retrieval": true,
  "index_name": "knowledge",
  "top_k": 5
}

When `use_instructions` is true, markdown files under `docs/instructions/` are loaded as prompt context.
Files with ALL-CAPS names (for example `docs/instructions/SECURITY_RULES.md`) are treated as hard truths and inserted before normal guidance.
Set `include_legacy_instruction_docs=true` only for compatibility with the previous docs-wide loading behavior.
```

---

### Session Tools

| Endpoint | Description |
|---|---|
| `POST /create_session` | Create a new session with TTL and metadata |
| `POST /get_session` | Get session state and optional message history |
| `POST /list_sessions` | List sessions with pagination |
| `POST /cleanup_expired_sessions` | Delete expired sessions and orphan messages |

When `session_id` is passed to `/ask`, recent session messages are replayed into prompt context and turns are persisted with explicit started/completed/failed lifecycle states.

---

### Workflow Tools

| Endpoint | Description |
|---|---|
| `POST /execute_workflow_sync` | Execute a linear workflow over an allowlisted set of tools |
| `POST /execute_workflow_async` | Queue a linear workflow for background execution and return a run record |
| `POST /get_workflow_run` | Fetch persisted workflow run status, step logs, and run events |

Current workflow constraints:
- Linear execution only
- Maximum 20 steps
- `run` tool timeout capped at 120 seconds inside workflows
- Async execution uses in-process background threads
- On server startup, incomplete queued/running workflow runs are marked failed
- Failed workflow runs include failure_reason (`restart_recovery`, `runtime_exception`, `step_failure`, `validation_failure`)

Example:

```json
{
    "steps": [
        {"tool": "list_dir", "args": {"path": "."}, "label": "inspect-root"},
        {"tool": "git_status", "args": {"path": "."}, "label": "repo-status"}
    ],
    "metadata": {"purpose": "quick inspection"}
}
```

---

### Fix Tools

| Endpoint | Description |
|---|---|
| `POST /analyze_failure` | Parse failure output, extract likely files/symbols, and return suggested next actions |
| `POST /assisted_fix` | Apply one approved exact-text patch and optionally rerun one verification command |

Current fix-flow constraints:
- No autonomous looping
- Explicit approval required before patch application
- At most one verification rerun per request
- Verification failure is reported but does not trigger automatic retries

Example analysis request:

```json
{
    "error_output": "NameError: name 'client' is not defined\napp.py:12",
    "path": "."
}
```

Example assisted fix request:

```json
{
    "path": "app.py",
    "old_text": "pritn('hello')",
    "new_text": "print('hello')",
    "approved": true,
    "verify_command": "python -m py_compile app.py"
}
```

---

### File Tools

| Endpoint | Description |
|---|---|
| `POST /read` | Read a file, optionally sliced to a line range |
| `POST /write` | Write a file (creates parents, optional backup) |
| `POST /apply_patch` | Replace exact text in a file (safe atomic write) |
| `POST /list_dir` | List directory contents |
| `POST /grep_search` | Search files by string or regex |
| `POST /diagnostics` | Python syntax-check a file or directory tree |

---

### Git Tools

| Endpoint | Description |
|---|---|
| `POST /git_status` | Short git status with branch info |
| `POST /git_diff` | Show unstaged or staged diff |

---

### Shell Tool

| Endpoint | Description |
|---|---|
| `POST /run` | Run a shell command inside the agent root |

```json
{ "command": "pytest tests/", "timeout": 60 }
```

Blocked prefixes include `rm -rf /`, `sudo rm`, `mkfs`, `shutdown`, and `reboot`.

---

### Web Tools

| Endpoint | Description |
|---|---|
| `POST /web_search` | DuckDuckGo search, returns ranked results |
| `POST /web_fetch` | Fetch a URL, returns cleaned text or markdown |
| `POST /stage_web_result` | Fetch a web result and stage it as a proposal |

---

### Vector Index Tools

| Endpoint | Description |
|---|---|
| `POST /create_index` | Create or reset a named index |
| `POST /upsert_documents` | Add or update documents in an index |
| `POST /query_index` | Semantic search with optional topic filter |
| `POST /delete_topic` | Remove all documents for a topic |

---

### Staging / Proposal Workflow

New knowledge goes through a staging queue before entering the vector index.

| Endpoint | Description |
|---|---|
| `POST /stage_document` | Stage a document as a pending proposal |
| `POST /list_proposals` | List proposals (filter by index, status) |
| `POST /get_proposal` | Get a single proposal by ID |
| `POST /approve_proposal` | Approve and upsert to the vector index |
| `POST /reject_proposal` | Reject with an optional reason |
| `POST /refresh_proposal` | Extend TTL or reset status to pending |
| `POST /cleanup_expired_proposals` | Mark expired pending proposals |

---

## Project Structure

```
agent.py                  # FastAPI app entry point
requirements.txt
models/
    requests.py           # Pydantic request/response models
routes/
    ask.py                # /ask endpoint (LLM + retrieval)
    tools.py              # All tool endpoints
tools/
    security.py           # AGENT_ROOT sandbox + path helpers
    read.py               # File read
    write.py              # File write
    apply_patch.py        # Exact-text file patching
    list_dir.py           # Directory listing
    grep_search.py        # Text/regex search
    diagnostics.py        # Python syntax checking
    run.py                # Shell command runner
    git_status.py         # git status
    git_diff.py           # git diff
    web_policy.py         # URL/IP validation (SSRF protection)
    web_search.py         # DuckDuckGo search
    safe_fetch.py         # Safe HTTP fetcher
    vector_chroma.py      # ChromaDB implementation
    vector_index.py       # Vector store facade
    vector_store_adapter.py  # Protocol + VectorDocument dataclass
    retrieval_policy.py   # Decides when web research is needed
    staging.py            # Proposal queue (SQLite)
knowledge/
    frameworks/           # (empty — add knowledge docs here)
    languages/
    style/
```

---

## Runtime Data

The server creates a `.agent_data/` directory inside the project root at runtime:

```
.agent_data/
    chroma/        # ChromaDB vector store
    proposals.db   # SQLite staging database
```

Add `.agent_data/` to your `.gitignore`.

---

## .gitignore (recommended)

```
.venv/
__pycache__/
*.pyc
*.pyo
*.bak
.agent_data/
```
