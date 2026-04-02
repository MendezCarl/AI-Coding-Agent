from __future__ import annotations

import typer

from cli.client import ApiClient
from cli.output import print_result


def register(app: typer.Typer, client_factory, output_mode_getter) -> None:
    fix_app = typer.Typer(help="Failure analysis and assisted fix commands")

    @fix_app.command("analyze-failure")
    def analyze_failure(
        error_output: str = typer.Option(..., "--error-output", help="Raw traceback or failure output"),
        path: str | None = typer.Option(None, "--path", help="Optional scope path"),
        include_hidden: bool = typer.Option(False, "--include-hidden"),
        max_search_results: int = typer.Option(20, "--max-search-results", min=1, max=50),
    ) -> None:
        payload = {
            "error_output": error_output,
            "path": path,
            "include_hidden": include_hidden,
            "max_search_results": max_search_results,
        }
        client: ApiClient = client_factory()
        result = client.post("/analyze_failure", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @fix_app.command("assisted-fix")
    def assisted_fix(
        path: str = typer.Option(..., "--path", help="File path"),
        old_text: str = typer.Option(..., "--old-text", help="Exact text to replace"),
        new_text: str = typer.Option(..., "--new-text", help="Replacement text"),
        approve: bool = typer.Option(False, "--approve", help="Required to apply patch"),
        create_backup: bool = typer.Option(True, "--create-backup/--no-backup"),
        verify_command: str | None = typer.Option(None, "--verify-command", help="Optional verification command"),
        verify_cwd: str | None = typer.Option(None, "--verify-cwd", help="Optional verification working directory"),
        verify_timeout: int = typer.Option(60, "--verify-timeout", min=1, max=120),
    ) -> None:
        if not approve:
            print_result(
                {
                    "status": "error",
                    "error": "assisted-fix requires --approve to proceed",
                },
                output_mode_getter(),
            )
            raise typer.Exit(code=1)

        payload = {
            "path": path,
            "old_text": old_text,
            "new_text": new_text,
            "approved": True,
            "create_backup": create_backup,
            "verify_command": verify_command,
            "verify_cwd": verify_cwd,
            "verify_timeout": verify_timeout,
        }
        client: ApiClient = client_factory()
        result = client.post("/assisted_fix", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    app.add_typer(fix_app, name="fix")
