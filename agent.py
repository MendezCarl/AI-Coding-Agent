import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from routes.ask import router as ask_router
from routes.tools import router as tools_router
from tools.workflow_runs import mark_incomplete_runs_failed

app = FastAPI(
    title="AI Agent Server",
    description="Local AI agent server with Ollama and tool endpoints",
    version="0.1.0",
)

_OPEN_PATHS = {"/", "/health"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.url.path in _OPEN_PATHS:
        return await call_next(request)
    api_key = os.environ.get("AGENT_API_KEY")
    if api_key:
        provided = request.headers.get("X-API-Key", "")
        if provided != api_key:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "error": "Unauthorized"},
            )
    return await call_next(request)


@app.on_event("startup")
async def recover_incomplete_workflow_runs() -> None:
    mark_incomplete_runs_failed("Server restarted before workflow completion")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "AI Agent Server is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask_router)
app.include_router(tools_router)