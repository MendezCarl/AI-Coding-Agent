from __future__ import annotations

import typer

from cli.client import ApiClient
from cli.output import print_result


def register(app: typer.Typer, client_factory, output_mode_getter, session_id_getter) -> None:
    session_app = typer.Typer(help="Session management commands")

    @session_app.command("create")
    def create(
        ttl_hours: int = typer.Option(168, "--ttl-hours", min=1, max=720),
        metadata_json: str = typer.Option("{}", "--metadata-json", help="Session metadata as JSON object"),
    ) -> None:
        try:
            import json

            metadata = json.loads(metadata_json)
            if not isinstance(metadata, dict):
                raise ValueError("metadata_json must decode to an object")
        except Exception as e:
            print_result({"status": "error", "error": f"Invalid metadata_json: {e}"}, output_mode_getter())
            raise typer.Exit(code=1)

        client: ApiClient = client_factory()
        result = client.post("/create_session", {"ttl_hours": ttl_hours, "metadata": metadata})
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @session_app.command("get")
    def get(
        session_id: str | None = typer.Option(None, "--session-id", help="Session id to retrieve"),
        include_messages: bool = typer.Option(True, "--include-messages/--no-messages"),
        include_turns: bool = typer.Option(True, "--include-turns/--no-turns"),
        limit: int = typer.Option(200, "--limit", min=1, max=2000),
        offset: int = typer.Option(0, "--offset", min=0),
    ) -> None:
        resolved = session_id or session_id_getter()
        if not resolved:
            print_result({"status": "error", "error": "session_id is required"}, output_mode_getter())
            raise typer.Exit(code=1)

        payload = {
            "session_id": resolved,
            "include_messages": include_messages,
            "include_turns": include_turns,
            "limit": limit,
            "offset": offset,
        }
        client: ApiClient = client_factory()
        result = client.post("/get_session", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @session_app.command("list")
    def list_sessions(
        limit: int = typer.Option(50, "--limit", min=1, max=500),
        offset: int = typer.Option(0, "--offset", min=0),
        include_expired: bool = typer.Option(False, "--include-expired"),
    ) -> None:
        payload = {
            "limit": limit,
            "offset": offset,
            "include_expired": include_expired,
        }
        client: ApiClient = client_factory()
        result = client.post("/list_sessions", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @session_app.command("cleanup")
    def cleanup() -> None:
        client: ApiClient = client_factory()
        result = client.post("/cleanup_expired_sessions", {})
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    app.add_typer(session_app, name="session")
