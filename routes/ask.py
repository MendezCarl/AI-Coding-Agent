from fastapi import APIRouter, HTTPException
import httpx

from models.requests import AskRequest
from tools.retrieval_policy import should_use_research
from tools.vector_index import query_index

router = APIRouter()

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5-coder:7b"


@router.post("/ask")
async def ask(req: AskRequest):
    try:
        retrieval = None
        prompt_for_model = req.prompt

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
                    context_lines.append(f"[{idx}] source={source}\n{hit.get('content', '')}")

                context_blob = "\n\n".join(context_lines)
                prompt_for_model = (
                    "Use the context below when relevant. If context conflicts with task intent, follow the user request.\n\n"
                    f"Context:\n{context_blob}\n\n"
                    f"User request:\n{req.prompt}"
                )

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
            raise HTTPException(status_code=500, detail=f"Unexpected Ollama response: {data}")

        hits = retrieval.get("hits", []) if isinstance(retrieval, dict) else []
        return {
            "response": data["response"],
            "retrieval": {
                "enabled": req.use_retrieval,
                "index_name": req.index_name,
                "hits": len(hits),
                "needs_research": should_use_research(hits),
            },
        }

    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Ollama request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
