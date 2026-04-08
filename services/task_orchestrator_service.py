from __future__ import annotations

import json
from typing import Any

import httpx

from models.requests import OrchestrateTaskRequest
from services.instruction_service import instruction_service
from services.orchestrator_service import orchestrator_service
from services.tool_registry import tool_registry
from tools.retrieval_policy import should_use_research
from tools.sessions import begin_turn, complete_turn, fail_turn, get_recent_messages
from tools.vector_index import query_index

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
PLANNER_MODEL = "qwen2.5-coder:7b"

MUTATING_TOOLS = {"write", "apply_patch"}


def _balanced_json_slice(text: str) -> str | None:
    """
    Extract the first top-level JSON array/object substring from free-form model text.

    Ollama models sometimes wrap JSON in prose or code fences; this keeps parsing resilient
    without being too permissive.
    """

    if not text:
        return None

    start_candidates: list[tuple[int, str]] = []
    for token in ("[", "{"):
        idx = text.find(token)
        if idx != -1:
            start_candidates.append((idx, token))
    if not start_candidates:
        return None

    start, opening = min(start_candidates, key=lambda item: item[0])
    closing = "]" if opening == "[" else "}"

    in_string = False
    escape = False
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _tool_specs(allowed_tools: list[str]) -> list[dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {
        "list_dir": {
            "description": "List files/directories under a path.",
            "args": {
                "path": {"type": "string", "required": False, "default": "."},
                "include_hidden": {"type": "boolean", "required": False, "default": False},
            },
        },
        "grep_search": {
            "description": "Search repository text for a query.",
            "args": {
                "query": {"type": "string", "required": True},
                "path": {"type": "string", "required": False, "default": "."},
                "is_regex": {"type": "boolean", "required": False, "default": False},
                "case_sensitive": {"type": "boolean", "required": False, "default": False},
                "max_results": {"type": "number", "required": False, "default": 200},
                "include_hidden": {"type": "boolean", "required": False, "default": False},
            },
        },
        "read": {
            "description": "Read a file (optionally by line range).",
            "args": {
                "path": {"type": "string", "required": True},
                "start_line": {"type": "number", "required": False},
                "end_line": {"type": "number", "required": False},
            },
        },
        "diagnostics": {
            "description": "Python diagnostics: syntax-check up to 500 Python files under a path.",
            "args": {
                "path": {"type": "string", "required": False, "default": "."},
                "include_hidden": {"type": "boolean", "required": False, "default": False},
            },
        },
        "git_status": {
            "description": "Run `git status` in the repository.",
            "args": {
                "path": {"type": "string", "required": False, "default": "."},
            },
        },
        "git_diff": {
            "description": "Run `git diff` in the repository.",
            "args": {
                "path": {"type": "string", "required": False, "default": "."},
                "staged": {"type": "boolean", "required": False, "default": False},
            },
        },
        "run": {
            "description": "Run a shell command within the agent root (dangerous prefixes are blocked).",
            "args": {
                "command": {"type": "string", "required": True},
                "cwd": {"type": "string", "required": False},
                "timeout": {"type": "number", "required": False, "default": 30},
            },
        },
        "query_index": {
            "description": "Semantic search the vector knowledge index.",
            "args": {
                "query": {"type": "string", "required": True},
                "index_name": {"type": "string", "required": False, "default": "knowledge"},
                "top_k": {"type": "number", "required": False, "default": 5},
                "topic": {"type": "string", "required": False},
            },
        },
        "write": {
            "description": "Write a file (overwrites content).",
            "args": {
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "make_backup": {"type": "boolean", "required": False, "default": True},
                "create_parents": {"type": "boolean", "required": False, "default": True},
            },
        },
        "apply_patch": {
            "description": "Apply an exact-text patch in a file.",
            "args": {
                "path": {"type": "string", "required": True},
                "old_text": {"type": "string", "required": True},
                "new_text": {"type": "string", "required": True},
                "replace_all": {"type": "boolean", "required": False, "default": False},
                "create_backup": {"type": "boolean", "required": False, "default": True},
            },
        },
    }

    output: list[dict[str, Any]] = []
    for name in allowed_tools:
        if name in specs:
            output.append({"name": name, **specs[name]})
        else:
            output.append({"name": name, "description": "Tool available.", "args": {}})
    return output


def _parse_steps(raw_model_text: str) -> list[dict[str, Any]]:
    snippet = _balanced_json_slice(raw_model_text)
    if not snippet:
        raise ValueError("Planner did not return JSON")

    data = json.loads(snippet)
    if isinstance(data, dict) and isinstance(data.get("steps"), list):
        data = data["steps"]

    if not isinstance(data, list) or not data:
        raise ValueError("Planner JSON must be a non-empty array of steps")

    steps: list[dict[str, Any]] = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Step {idx} must be an object")
        tool = item.get("tool")
        if not tool:
            raise ValueError(f"Step {idx} missing 'tool'")
        args = item.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError(f"Step {idx} args must be an object")
        label = item.get("label")
        if label is not None and not isinstance(label, str):
            raise ValueError(f"Step {idx} label must be a string")
        steps.append({"tool": str(tool), "args": args, "label": label})
    return steps


class TaskOrchestratorService:
    async def orchestrate(self, req: OrchestrateTaskRequest) -> dict[str, Any]:
        stage = "prepare"
        turn_id: str | None = None
        recent_messages: list[dict] = []

        allowed_tools = tool_registry.list_workflow_tools()
        if not req.allow_write:
            allowed_tools = [name for name in allowed_tools if name not in MUTATING_TOOLS]

        try:
            if req.session_id:
                history = get_recent_messages(
                    session_id=req.session_id,
                    limit=8,
                )
                if history.get("status") != "ok":
                    error = history.get("error", "Failed to load session history")
                    raise RuntimeError(f"Session error: {error}")
                recent_messages = history.get("messages", [])

                turn_start = begin_turn(
                    session_id=req.session_id,
                    user_content=req.task,
                    metadata={
                        "kind": "orchestrate_task",
                        "allow_write": req.allow_write,
                        "plan_only": req.plan_only,
                        "run_async": req.run_async,
                        "max_steps": req.max_steps,
                        "use_retrieval": req.use_retrieval,
                        "use_instructions": req.use_instructions,
                    },
                )
                if turn_start.get("status") != "ok":
                    error = turn_start.get("error", "Failed to begin session turn")
                    raise RuntimeError(f"Session error: {error}")
                turn_id = turn_start["turn_id"]

            retrieval = None
            context_blob = ""
            if req.use_retrieval:
                retrieval = query_index(
                    query=req.task,
                    index_name=req.index_name,
                    top_k=req.top_k,
                )
                if retrieval.get("status") == "ok" and retrieval.get("hits"):
                    context_lines = []
                    for idx, hit in enumerate(retrieval["hits"], start=1):
                        source = hit.get("metadata", {}).get("source_url") or "local"
                        context_lines.append(f"[{idx}] source={source}\n{hit.get('content', '')}")
                    context_blob = "\n\n".join(context_lines)

            instruction_bundle = {
                "hard_truths": [],
                "guidance": [],
                "cache_hit": False,
                "excluded_files": [],
                "source_policy": "instructions-only",
                "instructions_dir": "docs/instructions",
                "legacy_docs_enabled": False,
            }
            if req.use_instructions:
                instruction_bundle = instruction_service.load(
                    include_legacy_docs=req.include_legacy_instruction_docs
                )

            tool_schema = _tool_specs(allowed_tools)

            prompt_sections: list[str] = []
            prompt_sections.append(
                "You are a tool orchestrator for a local coding agent.\n"
                "You create a short linear workflow of tool calls that helps accomplish the user's task.\n\n"
                "CRITICAL OUTPUT RULES:\n"
                "- Output ONLY valid JSON.\n"
                "- Output MUST be a JSON array of step objects.\n"
                "- Each step: {\"tool\": string, \"args\": object, \"label\": string|null}.\n"
                "- Do not wrap JSON in markdown fences.\n\n"
                "PLANNING RULES:\n"
                f"- Use ONLY these tools: {allowed_tools}.\n"
                f"- Use at most {req.max_steps} steps.\n"
                "- Prefer repo inspection first (list_dir, grep_search, read, git_status, git_diff) before running commands.\n"
                "- Keep run commands short, deterministic, and non-destructive.\n"
                "- If you cannot fully complete the task, return best-effort inspection steps.\n"
            )

            if not req.allow_write:
                prompt_sections.append(
                    "SAFETY:\n"
                    "- Do NOT use write/apply_patch. Your workflow must be read-only.\n"
                )

            prompt_sections.append(
                "AVAILABLE TOOLS (name, description, args):\n" + json.dumps(tool_schema, indent=2)
            )

            hard_truths = instruction_bundle.get("hard_truths", [])
            if hard_truths:
                hard_truth_lines = []
                for item in hard_truths:
                    hard_truth_lines.append(f"source={item['path']}\n{item['content']}")
                prompt_sections.append(
                    "NON-NEGOTIABLE HARD TRUTHS FROM DOCS:\n" + "\n\n".join(hard_truth_lines)
                )

            guidance = instruction_bundle.get("guidance", [])
            if guidance:
                guidance_lines = []
                for item in guidance:
                    guidance_lines.append(f"source={item['path']}\n{item['content']}")
                prompt_sections.append("ADDITIONAL DOCS GUIDANCE:\n" + "\n\n".join(guidance_lines))

            if recent_messages:
                history_lines = []
                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    history_lines.append(f"{role}: {content}")
                prompt_sections.append("RECENT SESSION CONTEXT:\n" + "\n".join(history_lines))

            if context_blob:
                prompt_sections.append(
                    "RETRIEVED REPOSITORY CONTEXT (use when relevant):\n" + context_blob
                )

            prompt_sections.append("USER TASK:\n" + req.task)
            prompt_for_model = "\n\n".join(prompt_sections)

            stage = "planner_model_call"
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": PLANNER_MODEL,
                        "prompt": prompt_for_model,
                        "stream": False,
                    },
                )
            response.raise_for_status()
            data = response.json()
            raw = data.get("response")
            if not raw or not isinstance(raw, str):
                raise RuntimeError(f"Unexpected planner response: {data}")

            stage = "parse_plan"
            steps = _parse_steps(raw)

            if len(steps) > req.max_steps:
                steps = steps[: req.max_steps]

            for idx, step in enumerate(steps, start=1):
                tool = step.get("tool")
                if tool not in allowed_tools:
                    raise ValueError(
                        f"Step {idx} uses unsupported tool '{tool}'. Allowed tools: {allowed_tools}"
                    )
                if not req.allow_write and tool in MUTATING_TOOLS:
                    raise ValueError(f"Step {idx} uses disallowed mutating tool '{tool}'")

            if req.plan_only:
                hits = retrieval.get("hits", []) if isinstance(retrieval, dict) else []
                payload: dict[str, Any] = {
                    "status": "ok",
                    "plan_only": True,
                    "steps": steps,
                    "planner": {"model": PLANNER_MODEL},
                    "retrieval": {
                        "enabled": req.use_retrieval,
                        "index_name": req.index_name,
                        "hits": len(hits),
                        "needs_research": should_use_research(hits),
                    },
                }

                if req.session_id and turn_id:
                    stage = "response_persist"
                    complete_turn(
                        session_id=req.session_id,
                        turn_id=turn_id,
                        assistant_content=json.dumps(payload, indent=2),
                        metadata={"planned_steps": len(steps)},
                    )
                return payload

            stage = "execute_workflow"
            metadata = dict(req.metadata or {})
            metadata.setdefault("task", req.task)
            metadata.setdefault("planner_model", PLANNER_MODEL)
            metadata.setdefault("allow_write", req.allow_write)
            metadata.setdefault("generated_steps", len(steps))

            if req.run_async:
                result = orchestrator_service.execute_async(
                    steps=steps,
                    session_id=req.session_id,
                    metadata=metadata,
                )
            else:
                result = orchestrator_service.execute_sync(
                    steps=steps,
                    session_id=req.session_id,
                    metadata=metadata,
                )

            output: dict[str, Any] = {
                "status": "ok",
                "plan_only": False,
                "steps": steps,
                "execution": result,
            }

            if req.session_id and turn_id:
                stage = "response_persist"
                complete_turn(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    assistant_content=json.dumps(output, indent=2),
                    metadata={
                        "planned_steps": len(steps),
                        "run_id": (result.get("run") or {}).get("id"),
                        "queued": bool(result.get("queued")),
                    },
                )

            return output
        except Exception as e:
            if req.session_id and turn_id:
                fail_turn(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    error=str(e),
                    error_stage=stage,
                )
            raise


task_orchestrator_service = TaskOrchestratorService()

