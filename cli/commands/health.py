from __future__ import annotations

import typer

from cli.client import ApiClient
from cli.output import print_result


def register(app: typer.Typer, client_factory, output_mode_getter) -> None:
    @app.command("health")
    def health() -> None:
        client: ApiClient = client_factory()
        result = client.get("/health")
        payload = result.payload
        if result.ok and "status" not in payload:
            payload = {"status": "ok", **payload}
        print_result(payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)
