from __future__ import annotations

import typer

from cli.client import ApiClient
from cli.output import print_result


def register(app: typer.Typer, client_factory, output_mode_getter, session_id_getter) -> None:
    @app.command("ask")
    def ask(
        prompt: str = typer.Argument(..., help="Prompt to send to the local coding agent"),
        session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
        session_context_turns: int = typer.Option(8, "--session-context-turns", min=0, max=20),
        use_instructions: bool = typer.Option(True, "--use-instructions/--no-instructions"),
        include_legacy_instruction_docs: bool = typer.Option(False, "--legacy-instruction-docs"),
        use_retrieval: bool = typer.Option(True, "--use-retrieval/--no-retrieval"),
        index_name: str = typer.Option("knowledge", "--index-name"),
        top_k: int = typer.Option(5, "--top-k", min=1, max=20),
    ) -> None:
        resolved_session = session_id or session_id_getter()
        payload = {
            "prompt": prompt,
            "session_id": resolved_session,
            "session_context_turns": session_context_turns,
            "use_instructions": use_instructions,
            "include_legacy_instruction_docs": include_legacy_instruction_docs,
            "use_retrieval": use_retrieval,
            "index_name": index_name,
            "top_k": top_k,
        }

        client: ApiClient = client_factory()
        result = client.post("/ask", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)
