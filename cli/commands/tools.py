from __future__ import annotations

import json

import typer

from cli.client import ApiClient
from cli.output import print_result


def register(app: typer.Typer, client_factory, output_mode_getter) -> None:
    tools_app = typer.Typer(help="Core tool endpoint commands")

    @tools_app.command("run")
    def run(
        command: str = typer.Option(..., "--command", help="Shell command to execute"),
        cwd: str | None = typer.Option(None, "--cwd", help="Optional working directory"),
        timeout: int = typer.Option(30, "--timeout", min=1),
    ) -> None:
        payload = {"command": command, "cwd": cwd, "timeout": timeout}
        client: ApiClient = client_factory()
        result = client.post("/run", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("read")
    def read(
        path: str = typer.Option(..., "--path", help="File path"),
        start_line: int | None = typer.Option(None, "--start-line", min=1),
        end_line: int | None = typer.Option(None, "--end-line", min=1),
    ) -> None:
        payload = {"path": path, "start_line": start_line, "end_line": end_line}
        client: ApiClient = client_factory()
        result = client.post("/read", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("write")
    def write(
        path: str = typer.Option(..., "--path", help="File path"),
        content: str = typer.Option(..., "--content", help="File content"),
        make_backup: bool = typer.Option(True, "--make-backup/--no-backup"),
        create_parents: bool = typer.Option(True, "--create-parents/--no-create-parents"),
    ) -> None:
        payload = {
            "path": path,
            "content": content,
            "make_backup": make_backup,
            "create_parents": create_parents,
        }
        client: ApiClient = client_factory()
        result = client.post("/write", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("list-dir")
    def list_dir(
        path: str = typer.Option(".", "--path", help="Directory path"),
        include_hidden: bool = typer.Option(False, "--include-hidden"),
    ) -> None:
        payload = {"path": path, "include_hidden": include_hidden}
        client: ApiClient = client_factory()
        result = client.post("/list_dir", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("grep-search")
    def grep_search(
        query: str = typer.Option(..., "--query", help="Search query"),
        path: str = typer.Option(".", "--path", help="Search root path"),
        is_regex: bool = typer.Option(False, "--regex"),
        case_sensitive: bool = typer.Option(False, "--case-sensitive"),
        max_results: int = typer.Option(200, "--max-results", min=1, max=2000),
        include_hidden: bool = typer.Option(False, "--include-hidden"),
    ) -> None:
        payload = {
            "query": query,
            "path": path,
            "is_regex": is_regex,
            "case_sensitive": case_sensitive,
            "max_results": max_results,
            "include_hidden": include_hidden,
        }
        client: ApiClient = client_factory()
        result = client.post("/grep_search", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("diagnostics")
    def diagnostics(
        path: str = typer.Option(".", "--path", help="File or directory path"),
        include_hidden: bool = typer.Option(False, "--include-hidden"),
    ) -> None:
        payload = {"path": path, "include_hidden": include_hidden}
        client: ApiClient = client_factory()
        result = client.post("/diagnostics", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("git-status")
    def git_status(path: str = typer.Option(".", "--path", help="Repository path")) -> None:
        payload = {"path": path}
        client: ApiClient = client_factory()
        result = client.post("/git_status", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("git-diff")
    def git_diff(
        path: str = typer.Option(".", "--path", help="Repository path"),
        staged: bool = typer.Option(False, "--staged"),
    ) -> None:
        payload = {"path": path, "staged": staged}
        client: ApiClient = client_factory()
        result = client.post("/git_diff", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("apply-patch")
    def apply_patch(
        path: str = typer.Option(..., "--path", help="File path"),
        old_text: str = typer.Option(..., "--old-text", help="Exact text to replace"),
        new_text: str = typer.Option(..., "--new-text", help="Replacement text"),
        replace_all: bool = typer.Option(False, "--replace-all"),
        create_backup: bool = typer.Option(True, "--create-backup/--no-backup"),
    ) -> None:
        payload = {
            "path": path,
            "old_text": old_text,
            "new_text": new_text,
            "replace_all": replace_all,
            "create_backup": create_backup,
        }
        client: ApiClient = client_factory()
        result = client.post("/apply_patch", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @tools_app.command("query-index")
    def query_index(
        query: str = typer.Option(..., "--query", help="Semantic query"),
        index_name: str = typer.Option("knowledge", "--index-name"),
        top_k: int = typer.Option(5, "--top-k", min=1, max=20),
        topic: str | None = typer.Option(None, "--topic"),
    ) -> None:
        payload = {
            "index_name": index_name,
            "query": query,
            "top_k": top_k,
            "topic": topic,
        }
        client: ApiClient = client_factory()
        result = client.post("/query_index", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    app.add_typer(tools_app, name="tools")
