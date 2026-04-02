from fastapi import APIRouter, HTTPException

from models.requests import AskRequest
from services.ask_service import ask_service

router = APIRouter()

@router.post("/ask")
async def ask(req: AskRequest):
    try:
        return await ask_service.ask(req)

    except Exception as e:
        # Preserve a stable HTTP 500 contract while service boundaries evolve.
        error = str(e)
        if "Ollama" in error or "http" in error.lower():
            raise HTTPException(status_code=500, detail=f"Ollama request failed: {error}")
        raise HTTPException(status_code=500, detail=error)
