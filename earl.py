"""
earl — interactive AI coding agent (like Claude Code).

Run from any project directory:
  python earl.py              ← opens interactive REPL in $PWD
  python earl.py --write      ← open REPL with file edits enabled from the start

One-shot usage (for scripting):
  python earl.py run "add type hints to tools/read.py"
  python earl.py ask "how does the orchestrator work?"

REPL commands:
  <anything>       task / question — earl figures it out
  ?<text>          force a quick question (no tool loop, just /ask)
  !<text>          force a tool-executing task
  /write           toggle write mode on/off
  /session         show current session id
  exit | quit      leave

Configuration (in priority order):
  1. CLI flags
  2. Environment variables: AGENT_SERVER_URL, AGENT_API_KEY
  3. ~/.agent_config.toml  →  [agent]  server_url = "..."  api_key = "..."
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Make tool imports work regardless of which directory earl is invoked from.
_EARL_DIR = Path(__file__).resolve().parent
if str(_EARL_DIR) not in sys.path:
    sys.path.insert(0, str(_EARL_DIR))

import click
import httpx

# ---------------------------------------------------------------------------
# Local tool imports — reuse existing tool modules directly, no duplication
# ---------------------------------------------------------------------------
from tools.apply_patch import apply_patch
from tools.diagnostics import diagnostics
from tools.git_diff import git_diff
from tools.git_status import git_status
from tools.grep_search import grep_search
from tools.list_dir import list_dir
from tools.read import read_file
from tools.run import run_command
from tools.write import write_file

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path.home() / ".agent_config.toml"
_DEFAULT_SERVER = "http://localhost:8000"

_LOCAL_TOOL_ALLOWLIST = {
    "apply_patch", "diagnostics", "git_diff", "git_status",
    "grep_search", "list_dir", "read", "run", "write",
}

_QUESTION_PREFIXES = ("what", "how", "why", "when", "who", "where", "is ", "are ",
                      "does", "do ", "can ", "could", "should", "explain", "describe",
                      "tell me", "show me", "list ")


def _load_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if _CONFIG_PATH.exists():
        try:
            import toml  # type: ignore[import]
            raw = toml.load(_CONFIG_PATH)
            section = raw.get("agent", {})
            if "server_url" in section:
                cfg["server_url"] = str(section["server_url"])
            if "api_key" in section:
                cfg["api_key"] = str(section["api_key"])
        except Exception:
            pass
    return cfg


def _resolve(flag_value: str | None, env_key: str, config_key: str, default: str) -> str:
    if flag_value:
        return flag_value
    if env_key in os.environ:
        return os.environ[env_key]
    return _load_config().get(config_key, default)


def _headers(api_key: str) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


def _looks_like_question(text: str) -> bool:
    t = text.lower().strip()
    return t.endswith("?") or any(t.startswith(p) for p in _QUESTION_PREFIXES)


# ---------------------------------------------------------------------------
# Local tool dispatch
# ---------------------------------------------------------------------------

def _execute_local(tool_call: dict[str, Any], cwd: str) -> dict[str, Any]:
    tool = tool_call["tool"]
    args: dict[str, Any] = dict(tool_call.get("args") or {})

    if tool not in _LOCAL_TOOL_ALLOWLIST:
        return {"status": "error", "error": f"Tool '{tool}' is not in the client allowlist"}

    def _p(key: str) -> str:
        val = args.get(key, ".")
        return val if os.path.isabs(str(val)) else os.path.join(cwd, val)

    try:
        if tool == "read":
            return read_file(path=_p("path"), start_line=args.get("start_line"), end_line=args.get("end_line"))
        if tool == "write":
            return write_file(path=_p("path"), content=str(args["content"]),
                              make_backup=bool(args.get("make_backup", True)),
                              create_parents=bool(args.get("create_parents", True)))
        if tool == "apply_patch":
            return apply_patch(path=_p("path"), old_text=str(args["old_text"]),
                               new_text=str(args["new_text"]),
                               replace_all=bool(args.get("replace_all", False)),
                               create_backup=bool(args.get("create_backup", True)))
        if tool == "list_dir":
            return list_dir(path=_p("path"), include_hidden=bool(args.get("include_hidden", False)))
        if tool == "grep_search":
            return grep_search(query=str(args["query"]), path=_p("path"),
                               is_regex=bool(args.get("is_regex", False)),
                               case_sensitive=bool(args.get("case_sensitive", False)),
                               max_results=int(args.get("max_results", 200)),
                               include_hidden=bool(args.get("include_hidden", False)))
        if tool == "git_status":
            return git_status(path=_p("path"))
        if tool == "git_diff":
            return git_diff(path=_p("path"), staged=bool(args.get("staged", False)))
        if tool == "run":
            run_cwd = args.get("cwd")
            if run_cwd and not os.path.isabs(run_cwd):
                run_cwd = os.path.join(cwd, run_cwd)
            return run_command(command=str(args["command"]), cwd=run_cwd or cwd,
                               timeout=int(args.get("timeout", 30)))
        if tool == "diagnostics":
            return diagnostics(path=_p("path"), include_hidden=bool(args.get("include_hidden", False)))
    except KeyError as e:
        return {"status": "error", "error": f"Missing required arg for '{tool}': {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"Unhandled tool: {tool}"}


# ---------------------------------------------------------------------------
# Core execution helpers (shared by REPL and subcommands)
# ---------------------------------------------------------------------------

def _do_task(
    task: str,
    http: httpx.Client,
    server_url: str,
    key: str,
    work_dir: str,
    allow_write: bool,
    session_id: str | None,
    max_steps: int,
    use_retrieval: bool,
) -> bool:
    """Run a task through the full tool loop. Returns True on success."""
    payload: dict[str, Any] = {
        "task": task,
        "allow_write": allow_write,
        "max_steps": max_steps,
        "use_retrieval": use_retrieval,
    }
    if session_id:
        payload["session_id"] = session_id

    resp = http.post(f"{server_url}/task/start", json=payload, headers=_headers(key))
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    if data.get("status") != "ok":
        click.echo(click.style(f"  error: {data.get('error', data)}", fg="red"))
        return False

    run_id: str = data["run_id"]
    click.echo(click.style(f"  run {run_id[:8]}…", fg="bright_black"))

    while data.get("next") == "tool_call":
        tc = data["tool_call"]
        label = tc.get("label") or tc["tool"]
        step = tc.get("step_index", "?")
        click.echo(click.style(f"  [{step}] {label}  ({tc['tool']})", fg="cyan"))

        result = _execute_local(tc, work_dir)
        ok = result.get("status") == "ok"
        click.echo(click.style(f"       {'✓' if ok else '✗'} {'' if ok else result.get('error')}", fg="green" if ok else "red"))

        resp = http.post(f"{server_url}/task/{run_id}/tool_result",
                         json={"tool_name": tc["tool"], "result": result},
                         headers=_headers(key))
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            click.echo(click.style(f"  error: {data.get('error', data)}", fg="red"))
            return False

    if data.get("next") == "complete":
        click.echo(click.style("  done.", fg="green", bold=True))
        return True
    else:
        click.echo(click.style(f"  failed: {data.get('error')}", fg="red"))
        return False


def _do_ask(
    question: str,
    http: httpx.Client,
    server_url: str,
    key: str,
    session_id: str | None,
    use_retrieval: bool,
) -> None:
    payload: dict[str, Any] = {"prompt": question, "use_retrieval": use_retrieval}
    if session_id:
        payload["session_id"] = session_id
    resp = http.post(f"{server_url}/ask", json=payload, headers=_headers(key))
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        click.echo(click.style(f"  error: {data.get('error', data)}", fg="red"))
        return
    click.echo(data.get("response", ""))


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

def _repl(server_url: str, key: str, work_dir: str, allow_write: bool) -> None:
    import tools.security as _sec
    _sec.AGENT_ROOT = Path(work_dir)

    session_id = str(uuid.uuid4())
    write_on = allow_write

    click.echo(click.style("Earl", bold=True, fg="cyan") +
               click.style(f"  cwd: {work_dir}", fg="bright_black"))
    click.echo(click.style(f"  server: {server_url}", fg="bright_black"))
    click.echo(click.style(f"  write: {'on' if write_on else 'off'}  "
                           f"session: {session_id[:8]}…  "
                           "(type exit to quit, /write to toggle edits)", fg="bright_black"))
    click.echo()

    with httpx.Client(timeout=120) as http:
        # Verify server is reachable before entering the loop
        try:
            http.get(f"{server_url}/health", headers=_headers(key)).raise_for_status()
        except Exception as e:
            click.echo(click.style(f"Cannot reach server at {server_url}: {e}", fg="red"))
            return

        while True:
            try:
                mode_indicator = click.style("W", fg="yellow") if write_on else click.style("R", fg="bright_black")
                raw = input(click.style("earl", fg="cyan", bold=True) +
                            f"[{mode_indicator}]" +
                            click.style("> ", fg="cyan", bold=True))
            except (EOFError, KeyboardInterrupt):
                click.echo()
                click.echo(click.style("bye.", fg="bright_black"))
                break

            text = raw.strip()
            if not text:
                continue

            # REPL commands
            low = text.lower()
            if low in ("exit", "quit"):
                click.echo(click.style("bye.", fg="bright_black"))
                break
            if low == "/write":
                write_on = not write_on
                click.echo(click.style(f"  write mode {'on' if write_on else 'off'}", fg="yellow"))
                continue
            if low == "/session":
                click.echo(click.style(f"  session: {session_id}", fg="bright_black"))
                continue

            # Force-ask prefix
            if text.startswith("?"):
                question = text[1:].strip()
                try:
                    _do_ask(question, http, server_url, key, session_id, use_retrieval=True)
                except Exception as e:
                    click.echo(click.style(f"  error: {e}", fg="red"))
                continue

            # Force-task prefix
            if text.startswith("!"):
                task = text[1:].strip()
                try:
                    _do_task(task, http, server_url, key, work_dir,
                             allow_write=write_on, session_id=session_id,
                             max_steps=12, use_retrieval=True)
                except Exception as e:
                    click.echo(click.style(f"  error: {e}", fg="red"))
                continue

            # Auto-route: questions go to /ask, everything else runs the tool loop
            if _looks_like_question(text):
                try:
                    _do_ask(text, http, server_url, key, session_id, use_retrieval=True)
                except Exception as e:
                    click.echo(click.style(f"  error: {e}", fg="red"))
            else:
                try:
                    _do_task(text, http, server_url, key, work_dir,
                             allow_write=write_on, session_id=session_id,
                             max_steps=12, use_retrieval=True)
                except httpx.HTTPStatusError as e:
                    click.echo(click.style(f"  HTTP {e.response.status_code}: {e.response.text}", fg="red"))
                except httpx.RequestError as e:
                    click.echo(click.style(f"  connection error: {e}", fg="red"))
                except Exception as e:
                    click.echo(click.style(f"  error: {e}", fg="red"))

            click.echo()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--server", default=None, envvar="AGENT_SERVER_URL", help="Remote server URL.")
@click.option("--api-key", default=None, envvar="AGENT_API_KEY", help="API key.")
@click.option("--write", "allow_write", is_flag=True, default=False, help="Enable file edits from the start.")
@click.option("--cwd", default=None, help="Working directory (default: $PWD).")
@click.pass_context
def cli(ctx: click.Context, server: str | None, api_key: str | None, allow_write: bool, cwd: str | None) -> None:
    """Earl — AI coding agent. Run without a subcommand to open the interactive REPL."""
    ctx.ensure_object(dict)
    ctx.obj["server_url"] = _resolve(server, "AGENT_SERVER_URL", "server_url", _DEFAULT_SERVER).rstrip("/")
    ctx.obj["api_key"] = _resolve(api_key, "AGENT_API_KEY", "api_key", "")
    ctx.obj["work_dir"] = os.path.abspath(cwd or os.getcwd())
    ctx.obj["allow_write"] = allow_write

    if ctx.invoked_subcommand is None:
        # No subcommand → open REPL
        _repl(
            server_url=ctx.obj["server_url"],
            key=ctx.obj["api_key"],
            work_dir=ctx.obj["work_dir"],
            allow_write=ctx.obj["allow_write"],
        )


@cli.command()
@click.argument("task")
@click.option("--server", default=None, help="Remote server URL.")
@click.option("--api-key", default=None, help="API key.")
@click.option("--allow-write", is_flag=True, default=False, help="Allow file edits.")
@click.option("--session", default=None, help="Session ID.")
@click.option("--max-steps", default=12, show_default=True)
@click.option("--cwd", default=None)
@click.option("--no-retrieval", is_flag=True, default=False)
def run(task: str, server: str | None, api_key: str | None, allow_write: bool,
        session: str | None, max_steps: int, cwd: str | None, no_retrieval: bool) -> None:
    """Run a single task (non-interactive)."""
    server_url = _resolve(server, "AGENT_SERVER_URL", "server_url", _DEFAULT_SERVER).rstrip("/")
    key = _resolve(api_key, "AGENT_API_KEY", "api_key", "")
    work_dir = os.path.abspath(cwd or os.getcwd())

    import tools.security as _sec
    _sec.AGENT_ROOT = Path(work_dir)

    click.echo(click.style(f"task: {task}", bold=True))
    click.echo(click.style(f"server: {server_url}  cwd: {work_dir}", fg="bright_black"))
    try:
        with httpx.Client(timeout=120) as http:
            ok = _do_task(task, http, server_url, key, work_dir,
                          allow_write=allow_write, session_id=session,
                          max_steps=max_steps, use_retrieval=not no_retrieval)
        if not ok:
            sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(click.style(f"HTTP {e.response.status_code}: {e.response.text}", fg="red"))
        sys.exit(1)
    except httpx.RequestError as e:
        click.echo(click.style(f"Connection error: {e}", fg="red"))
        sys.exit(1)


@cli.command()
@click.argument("question")
@click.option("--server", default=None)
@click.option("--api-key", default=None)
@click.option("--session", default=None)
@click.option("--no-retrieval", is_flag=True, default=False)
def ask(question: str, server: str | None, api_key: str | None,
        session: str | None, no_retrieval: bool) -> None:
    """Ask a question (no file editing)."""
    server_url = _resolve(server, "AGENT_SERVER_URL", "server_url", _DEFAULT_SERVER).rstrip("/")
    key = _resolve(api_key, "AGENT_API_KEY", "api_key", "")
    try:
        with httpx.Client(timeout=120) as http:
            _do_ask(question, http, server_url, key, session, use_retrieval=not no_retrieval)
    except httpx.HTTPStatusError as e:
        click.echo(click.style(f"HTTP {e.response.status_code}: {e.response.text}", fg="red"))
        sys.exit(1)
    except httpx.RequestError as e:
        click.echo(click.style(f"Connection error: {e}", fg="red"))
        sys.exit(1)


if __name__ == "__main__":
    cli()
