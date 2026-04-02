from __future__ import annotations

import json

from rich.console import Console

console = Console()


def print_result(payload: dict, output_mode: str = "human") -> None:
    if output_mode == "json":
        console.print(json.dumps(payload, indent=2, ensure_ascii=True))
        return

    handled: set[str] = set()
    status = payload.get("status")
    if status is not None:
        handled.add("status")
    if status == "ok":
        console.print("[green]ok[/green]")
    elif status is not None:
        console.print(f"[red]{status}[/red]")

    if "response" in payload:
        handled.add("response")
        console.print(payload["response"])

    if "error" in payload:
        handled.add("error")
        console.print(f"[red]error:[/red] {payload['error']}")

    run = payload.get("run")
    if isinstance(run, dict):
        handled.add("run")
        run_id = run.get("id", "<unknown>")
        run_status = run.get("status", "unknown")
        completed = run.get("completed_steps")
        total = run.get("total_steps")
        failure_reason = run.get("failure_reason")
        progress = ""
        if completed is not None and total is not None:
            progress = f" ({completed}/{total})"
        if failure_reason:
            console.print(f"run {run_id}: {run_status}{progress}, reason={failure_reason}")
        else:
            console.print(f"run {run_id}: {run_status}{progress}")

    remaining = {k: v for k, v in payload.items() if k not in handled}
    if remaining:
        console.print(json.dumps(remaining, indent=2, ensure_ascii=True))
