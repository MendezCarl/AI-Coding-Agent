from __future__ import annotations

import json
import time

import typer
from rich.console import Console

from cli.client import ApiClient
from cli.output import print_result

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
console = Console()


def _parse_steps(steps_json: str) -> list[dict]:
    data = json.loads(steps_json)
    if not isinstance(data, list):
        raise ValueError("steps_json must decode to an array")
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"step {idx} must be an object")
        if "tool" not in item:
            raise ValueError(f"step {idx} must include 'tool'")
    return data


def _parse_metadata(metadata_json: str) -> dict:
    data = json.loads(metadata_json)
    if not isinstance(data, dict):
        raise ValueError("metadata_json must decode to an object")
    return data


def register(app: typer.Typer, client_factory, output_mode_getter, session_id_getter) -> None:
    workflow_app = typer.Typer(help="Workflow execution commands")

    @workflow_app.command("sync")
    def sync(
        steps_json: str = typer.Option(..., "--steps-json", help="Workflow steps as JSON array"),
        metadata_json: str = typer.Option("{}", "--metadata-json", help="Workflow metadata JSON object"),
        session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
    ) -> None:
        try:
            steps = _parse_steps(steps_json)
            metadata = _parse_metadata(metadata_json)
        except Exception as e:
            print_result({"status": "error", "error": f"Invalid workflow payload: {e}"}, output_mode_getter())
            raise typer.Exit(code=1)

        payload = {
            "steps": steps,
            "session_id": session_id or session_id_getter(),
            "metadata": metadata,
        }

        client: ApiClient = client_factory()
        result = client.post("/execute_workflow_sync", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @workflow_app.command("async")
    def async_run(
        steps_json: str = typer.Option(..., "--steps-json", help="Workflow steps as JSON array"),
        metadata_json: str = typer.Option("{}", "--metadata-json", help="Workflow metadata JSON object"),
        session_id: str | None = typer.Option(None, "--session-id", help="Optional session id"),
    ) -> None:
        try:
            steps = _parse_steps(steps_json)
            metadata = _parse_metadata(metadata_json)
        except Exception as e:
            print_result({"status": "error", "error": f"Invalid workflow payload: {e}"}, output_mode_getter())
            raise typer.Exit(code=1)

        payload = {
            "steps": steps,
            "session_id": session_id or session_id_getter(),
            "metadata": metadata,
        }

        client: ApiClient = client_factory()
        result = client.post("/execute_workflow_async", payload)
        print_result(result.payload, output_mode_getter())
        if not result.ok:
            raise typer.Exit(code=1)

    @workflow_app.command("get")
    def get(
        run_id: str = typer.Option(..., "--run-id", help="Workflow run id"),
        watch: bool = typer.Option(False, "--watch", help="Poll until terminal status"),
        poll_interval: float = typer.Option(1.0, "--poll-interval", min=0.2, help="Polling interval in seconds"),
        max_polls: int = typer.Option(120, "--max-polls", min=1, help="Maximum poll attempts in watch mode"),
        show_progress: bool = typer.Option(True, "--progress/--no-progress", help="Show watch progress updates"),
        show_events: bool = typer.Option(True, "--events/--no-events", help="Show new run events while watching"),
    ) -> None:
        client: ApiClient = client_factory()
        output_mode = output_mode_getter()
        human_watch = output_mode == "human"

        def fetch_once() -> tuple[bool, dict]:
            result = client.post("/get_workflow_run", {"run_id": run_id})
            return result.ok, result.payload

        if not watch:
            ok, payload = fetch_once()
            print_result(payload, output_mode_getter())
            if not ok:
                raise typer.Exit(code=1)
            return

        attempts = 0
        last_payload: dict | None = None
        last_status: str | None = None
        last_completed: int | None = None
        seen_event_ids: set[str] = set()
        start_time = time.monotonic()
        while attempts < max_polls:
            attempts += 1
            ok, payload = fetch_once()
            last_payload = payload
            run = payload.get("run", {})
            status = run.get("status")
            if not ok:
                print_result(payload, output_mode_getter())
                raise typer.Exit(code=1)

            if human_watch and show_progress:
                completed = run.get("completed_steps")
                total = run.get("total_steps")
                if attempts == 1 or status != last_status or completed != last_completed:
                    elapsed = time.monotonic() - start_time
                    progress = ""
                    if completed is not None and total is not None:
                        progress = f" ({completed}/{total})"
                    console.print(
                        f"[cyan]watch[/cyan] attempt={attempts} status={status}{progress} elapsed={elapsed:.1f}s"
                    )
                last_completed = completed
                last_status = status

            if human_watch and show_events:
                events = payload.get("events") or []
                if isinstance(events, list):
                    for event in events:
                        if not isinstance(event, dict):
                            continue
                        event_id = event.get("id")
                        if event_id and event_id in seen_event_ids:
                            continue
                        if event_id:
                            seen_event_ids.add(event_id)
                        event_type = event.get("event_type", "event")
                        message = event.get("message", "")
                        console.print(f"[magenta]event:{event_type}[/magenta] {message}")

            if status in TERMINAL_STATUSES:
                print_result(payload, output_mode)
                return
            time.sleep(poll_interval)

        timeout_payload = {
            "status": "error",
            "error": "Watch polling timed out before terminal workflow status",
            "attempts": attempts,
            "last_status": (last_payload or {}).get("run", {}).get("status"),
            "run_id": run_id,
            "elapsed_seconds": round(time.monotonic() - start_time, 3),
        }
        print_result(timeout_payload, output_mode)
        raise typer.Exit(code=1)

    app.add_typer(workflow_app, name="workflow")
