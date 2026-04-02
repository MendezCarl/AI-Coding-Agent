from fastapi import FastAPI

from routes.ask import router as ask_router
from routes.tools import router as tools_router

app = FastAPI(
    title="AI Agent Server",
    description="Local AI agent server with Ollama and tool endpoints",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "AI Agent Server is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask_router)
app.include_router(tools_router)