from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import find_dotenv, load_dotenv

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass
class CliConfig:
    server_url: str = DEFAULT_SERVER_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    output_mode: str = "human"


def load_config() -> CliConfig:
    # Resolve .env from the current working directory (for laptop CLI repos).
    load_dotenv(dotenv_path=find_dotenv(filename=".env", usecwd=True), override=False)

    server_url = os.getenv("AI_AGENT_SERVER_URL", DEFAULT_SERVER_URL).strip() or DEFAULT_SERVER_URL
    timeout_raw = os.getenv("AI_AGENT_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)).strip()

    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    return CliConfig(
        server_url=server_url,
        timeout_seconds=timeout_seconds,
        output_mode="human",
    )
