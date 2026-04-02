from __future__ import annotations

import httpx

from models.requests import AskRequest
from services.instruction_service import instruction_service
from tools.retrieval_policy import should_use_research
from tools.sessions import begin_turn, complete_turn, fail_turn, get_recent_messages
from tools.vector_index import query_index

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5-coder:7b"


class AskService:
    async def ask(self, req: AskRequest) -> dict:
        stage = "prepare"
        turn_id: str | None = None
        recent_messages: list[dict] = []

        try:
            if req.session_id:
                history = get_recent_messages(
                    session_id=req.session_id,
                    limit=req.session_context_turns,
                )
                if history.get("status") != "ok":
                    error = history.get("error", "Failed to load session history")
                    raise RuntimeError(f"Session error: {error}")
                recent_messages = history.get("messages", [])

                turn_start = begin_turn(
                    session_id=req.session_id,
                    user_content=req.prompt,
                    metadata={
                        "use_retrieval": req.use_retrieval,
                        "use_instructions": req.use_instructions,
                        "session_context_turns": req.session_context_turns,
                    },
                )
                if turn_start.get("status") != "ok":
                    error = turn_start.get("error", "Failed to begin session turn")
                    raise RuntimeError(f"Session error: {error}")
                turn_id = turn_start["turn_id"]

            retrieval = None
            context_blob = ""

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

            if req.use_retrieval:
                retrieval = query_index(
                    query=req.prompt,
                    index_name=req.index_name,
                    top_k=req.top_k,
                )

                if retrieval.get("status") == "ok" and retrieval.get("hits"):
                    context_lines = []
                    for idx, hit in enumerate(retrieval["hits"], start=1):
                        source = hit.get("metadata", {}).get("source_url") or "local"
                        context_lines.append(f"[{idx}] source={source}\\n{hit.get('content', '')}")
                    context_blob = "\\n\\n".join(context_lines)

            prompt_sections: list[str] = []

            hard_truths = instruction_bundle.get("hard_truths", [])
            if hard_truths:
                hard_truth_lines = []
                for item in hard_truths:
                    hard_truth_lines.append(f"source={item['path']}\\n{item['content']}")
                prompt_sections.append(
                    "NON-NEGOTIABLE HARD TRUTHS FROM DOCS:\\n"
                    + "\\n\\n".join(hard_truth_lines)
                )

            guidance = instruction_bundle.get("guidance", [])
            if guidance:
                guidance_lines = []
                for item in guidance:
                    guidance_lines.append(f"source={item['path']}\\n{item['content']}")
                prompt_sections.append(
                    "ADDITIONAL DOCS GUIDANCE:\\n"
                    + "\\n\\n".join(guidance_lines)
                )

            if recent_messages:
                history_lines = []
                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    history_lines.append(f"{role}: {content}")
                prompt_sections.append(
                    "RECENT SESSION CONTEXT:\\n"
                    + "\\n".join(history_lines)
                )

            if context_blob:
                prompt_sections.append(
                    "RETRIEVED REPOSITORY CONTEXT (use when relevant):\\n"
                    f"{context_blob}"
                )

            prompt_sections.append(f"USER REQUEST:\\n{req.prompt}")
            prompt_for_model = "\\n\\n".join(prompt_sections)

            stage = "model_call"
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": MODEL,
                        "prompt": prompt_for_model,
                        "stream": False,
                    },
                )

            response.raise_for_status()
            data = response.json()

            if "response" not in data:
                raise RuntimeError(f"Unexpected Ollama response: {data}")

            hits = retrieval.get("hits", []) if isinstance(retrieval, dict) else []
            result = {
                "response": data["response"],
                "retrieval": {
                    "enabled": req.use_retrieval,
                    "index_name": req.index_name,
                    "hits": len(hits),
                    "needs_research": should_use_research(hits),
                },
                "instructions": {
                    "enabled": req.use_instructions,
                    "hard_truth_sources": [item["path"] for item in hard_truths],
                    "guidance_sources": [item["path"] for item in guidance],
                    "cache_hit": instruction_bundle.get("cache_hit", False),
                    "excluded_files": instruction_bundle.get("excluded_files", []),
                    "source_policy": instruction_bundle.get("source_policy", "instructions-only"),
                    "instructions_dir": instruction_bundle.get("instructions_dir", "docs/instructions"),
                    "legacy_docs_enabled": instruction_bundle.get("legacy_docs_enabled", False),
                },
            }

            if req.session_id and turn_id:
                stage = "response_persist"
                turn_complete = complete_turn(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    assistant_content=data["response"],
                    metadata={
                        "retrieval_hits": len(hits),
                        "instruction_hard_truth_sources": [item["path"] for item in hard_truths],
                        "instruction_guidance_sources": [item["path"] for item in guidance],
                    },
                )
                if turn_complete.get("status") != "ok":
                    error = turn_complete.get("error", "Failed to complete session turn")
                    raise RuntimeError(f"Session error: {error}")
                result["session"] = {
                    "id": req.session_id,
                    "turn_id": turn_id,
                    "replayed_messages": len(recent_messages),
                }

            return result
        except Exception as e:
            if req.session_id and turn_id:
                fail_turn(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    error=str(e),
                    error_stage=stage,
                )
            raise


ask_service = AskService()
