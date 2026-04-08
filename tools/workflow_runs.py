from __future__ import annotations

from datetime import UTC, datetime
import json
import sqlite3
from uuid import uuid4

from tools.security import AGENT_ROOT

DB_PATH = AGENT_ROOT / ".agent_data" / "workflow_runs.db"
ALLOWED_RUN_STATUSES = {"pending", "queued", "running", "waiting_for_tool", "succeeded", "failed", "cancelled"}
ALLOWED_STEP_STATUSES = {"succeeded", "failed", "skipped"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
ALLOWED_FAILURE_REASONS = {
    "restart_recovery",
    "runtime_exception",
    "step_failure",
    "validation_failure",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            session_id TEXT,
            total_steps INTEGER NOT NULL,
            completed_steps INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            failure_reason TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            step_label TEXT,
            tool_name TEXT NOT NULL,
            args_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            error TEXT,
            FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_steps_run_id ON workflow_steps(run_id, step_index)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_run_events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_run_events_run_id ON workflow_run_events(run_id, created_at)"
    )

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
    if "failure_reason" not in cols:
        conn.execute("ALTER TABLE workflow_runs ADD COLUMN failure_reason TEXT")
    if "interactive_state" not in cols:
        conn.execute("ALTER TABLE workflow_runs ADD COLUMN interactive_state TEXT")

    conn.commit()
    return conn


def create_run(
    total_steps: int,
    session_id: str | None = None,
    metadata: dict | None = None,
    initial_status: str = "pending",
) -> dict:
    try:
        if initial_status not in ALLOWED_RUN_STATUSES:
            return {"status": "error", "error": f"Invalid run status: {initial_status}"}
        run_id = str(uuid4())
        now = _now_iso()
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs (
                    id, status, session_id, total_steps, completed_steps, created_at, updated_at, metadata, error, failure_reason
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, NULL, NULL)
                """,
                (run_id, initial_status, session_id, total_steps, now, now, json.dumps(metadata or {})),
            )
            conn.commit()
        return {"status": "ok", "run_id": run_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def update_run_status(
    run_id: str,
    status: str,
    completed_steps: int | None = None,
    error: str | None = None,
    failure_reason: str | None = None,
) -> dict:
    try:
        if status not in ALLOWED_RUN_STATUSES:
            return {"status": "error", "error": f"Invalid run status: {status}"}
        if failure_reason is not None and failure_reason not in ALLOWED_FAILURE_REASONS:
            return {"status": "error", "error": f"Invalid failure reason: {failure_reason}"}
        now = _now_iso()
        clauses = ["status = ?", "updated_at = ?", "error = ?", "failure_reason = ?"]
        params: list[object] = [status, now, error, failure_reason]
        if completed_steps is not None:
            clauses.append("completed_steps = ?")
            params.append(completed_steps)
        params.append(run_id)
        with _db() as conn:
            conn.execute(
                f"UPDATE workflow_runs SET {', '.join(clauses)} WHERE id = ?",
                params,
            )
            conn.commit()
        return {"status": "ok", "run_id": run_id}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def log_step(
    run_id: str,
    step_index: int,
    step_label: str | None,
    tool_name: str,
    args: dict,
    status: str,
    result: dict | None,
    started_at: str,
    finished_at: str,
    error: str | None = None,
) -> dict:
    try:
        if status not in ALLOWED_STEP_STATUSES:
            return {"status": "error", "error": f"Invalid step status: {status}"}
        step_id = str(uuid4())
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO workflow_steps (
                    id, run_id, step_index, step_label, tool_name, args_json, status,
                    result_json, started_at, finished_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    run_id,
                    step_index,
                    step_label,
                    tool_name,
                    json.dumps(args),
                    status,
                    json.dumps(result) if result is not None else None,
                    started_at,
                    finished_at,
                    error,
                ),
            )
            conn.commit()
        return {"status": "ok", "step_id": step_id}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def get_run(run_id: str) -> dict:
    try:
        with _db() as conn:
            run_row = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
            if not run_row:
                return {"status": "error", "error": "Workflow run not found", "run_id": run_id}
            step_rows = conn.execute(
                """
                SELECT * FROM workflow_steps
                WHERE run_id = ?
                ORDER BY step_index ASC
                """,
                (run_id,),
            ).fetchall()
            event_rows = conn.execute(
                """
                SELECT * FROM workflow_run_events
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        run = {
            "id": run_row["id"],
            "status": run_row["status"],
            "session_id": run_row["session_id"],
            "total_steps": run_row["total_steps"],
            "completed_steps": run_row["completed_steps"],
            "created_at": run_row["created_at"],
            "updated_at": run_row["updated_at"],
            "metadata": json.loads(run_row["metadata"]),
            "error": run_row["error"],
            "failure_reason": run_row["failure_reason"],
        }
        steps = []
        for row in step_rows:
            steps.append(
                {
                    "id": row["id"],
                    "step_index": row["step_index"],
                    "step_label": row["step_label"],
                    "tool_name": row["tool_name"],
                    "args": json.loads(row["args_json"]),
                    "status": row["status"],
                    "result": json.loads(row["result_json"]) if row["result_json"] else None,
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "error": row["error"],
                }
            )
        events = [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "message": row["message"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
            }
            for row in event_rows
        ]
        return {"status": "ok", "run": run, "steps": steps, "events": events}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def mark_incomplete_runs_failed(reason: str) -> dict:
    try:
        now = _now_iso()
        with _db() as conn:
            cursor = conn.execute(
                """
                UPDATE workflow_runs
                SET status = 'failed', updated_at = ?, error = ?, failure_reason = 'restart_recovery'
                WHERE status IN ('pending', 'queued', 'running')
                """,
                (now, reason),
            )
            conn.commit()
        return {"status": "ok", "updated_runs": cursor.rowcount}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def log_run_event(run_id: str, event_type: str, message: str, metadata: dict | None = None) -> dict:
    try:
        event_id = str(uuid4())
        now = _now_iso()
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO workflow_run_events (id, run_id, event_type, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, run_id, event_type, message, json.dumps(metadata or {}), now),
            )
            conn.commit()
        return {"status": "ok", "event_id": event_id}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def ensure_terminal_failed(run_id: str, reason: str, message: str) -> dict:
    try:
        if reason not in ALLOWED_FAILURE_REASONS:
            return {"status": "error", "error": f"Invalid failure reason: {reason}"}
        state = get_run(run_id)
        if state.get("status") != "ok":
            return state
        current = state["run"]["status"]
        if current in TERMINAL_RUN_STATUSES:
            return {"status": "ok", "run_id": run_id, "already_terminal": True}
        return update_run_status(
            run_id=run_id,
            status="failed",
            completed_steps=state["run"].get("completed_steps", 0),
            error=message,
            failure_reason=reason,
        )
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def save_interactive_state(run_id: str, state: dict) -> dict:
    """Persist the paused interactive execution state for a waiting_for_tool run."""
    try:
        now = _now_iso()
        with _db() as conn:
            conn.execute(
                "UPDATE workflow_runs SET interactive_state = ?, updated_at = ? WHERE id = ?",
                (json.dumps(state), now, run_id),
            )
            conn.commit()
        return {"status": "ok", "run_id": run_id}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}


def get_interactive_state(run_id: str) -> dict:
    """Retrieve the paused interactive execution state for a waiting_for_tool run."""
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT interactive_state FROM workflow_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            return {"status": "error", "error": "Workflow run not found", "run_id": run_id}
        raw = row["interactive_state"]
        if not raw:
            return {"status": "error", "error": "No interactive state saved for this run", "run_id": run_id}
        return {"status": "ok", "state": json.loads(raw)}
    except Exception as e:
        return {"status": "error", "error": str(e), "run_id": run_id}
