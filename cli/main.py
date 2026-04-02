from __future__ import annotations

import typer

from cli.client import ApiClient
from cli.commands import ask as ask_cmd
from cli.commands import fix as fix_cmd
from cli.commands import health as health_cmd
from cli.commands import session as session_cmd
from cli.commands import tools as tools_cmd
from cli.commands import workflow as workflow_cmd
from cli.config import load_config

app = typer.Typer(help="CLI for the local AI agent server")

_state = {
    "server_url": load_config().server_url,
    "timeout_seconds": load_config().timeout_seconds,
    "output_mode": "human",
    "session_id": None,
}


@app.callback()
def main(
    server_url: str = typer.Option(_state["server_url"], "--server-url", help="Agent server base URL"),
    timeout: float = typer.Option(_state["timeout_seconds"], "--timeout", min=1.0, help="HTTP timeout in seconds"),
    output: str = typer.Option("human", "--output", help="Output mode: human or json"),
    session_id: str | None = typer.Option(None, "--session-id", help="Default session id for commands"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Reserved flag for future interactive flows"),
) -> None:
    _state["server_url"] = server_url.rstrip("/")
    _state["timeout_seconds"] = timeout
    _state["output_mode"] = "json" if output.lower() == "json" else "human"
    _state["session_id"] = session_id
    _ = non_interactive


def _client_factory() -> ApiClient:
    return ApiClient(base_url=_state["server_url"], timeout_seconds=_state["timeout_seconds"])


def _output_mode() -> str:
    return _state["output_mode"]


def _session_id() -> str | None:
    return _state["session_id"]


health_cmd.register(app, _client_factory, _output_mode)
ask_cmd.register(app, _client_factory, _output_mode, _session_id)
session_cmd.register(app, _client_factory, _output_mode, _session_id)
workflow_cmd.register(app, _client_factory, _output_mode, _session_id)
tools_cmd.register(app, _client_factory, _output_mode)
fix_cmd.register(app, _client_factory, _output_mode)


if __name__ == "__main__":
    app()
