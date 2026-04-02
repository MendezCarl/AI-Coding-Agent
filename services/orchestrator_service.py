from __future__ import annotations

from datetime import UTC, datetime
import threading
from services.tool_registry import MAX_WORKFLOW_STEPS, tool_registry
from tools.workflow_runs import (
    create_run,
    ensure_terminal_failed,
    get_run,
    log_run_event,
    log_step,
    update_run_status,
)


class WorkflowGuardError(RuntimeError):
    pass


class OrchestratorService:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}

    def execute_sync(self, steps: list[dict], session_id: str | None = None, metadata: dict | None = None) -> dict:
        self._validate_steps(steps)

        run_record = create_run(total_steps=len(steps), session_id=session_id, metadata=metadata)
        if run_record.get("status") != "ok":
            raise RuntimeError(run_record.get("error", "Failed to create workflow run"))

        run_id = run_record["run_id"]
        return self._execute_existing_run(run_id=run_id, steps=steps)

    def execute_async(self, steps: list[dict], session_id: str | None = None, metadata: dict | None = None) -> dict:
        self._validate_steps(steps)

        run_record = create_run(
            total_steps=len(steps),
            session_id=session_id,
            metadata=metadata,
            initial_status="queued",
        )
        if run_record.get("status") != "ok":
            raise RuntimeError(run_record.get("error", "Failed to create workflow run"))

        run_id = run_record["run_id"]
        thread = threading.Thread(
            target=self._run_async,
            args=(run_id, steps),
            name=f"workflow-{run_id}",
            daemon=True,
        )
        self._threads[run_id] = thread
        thread.start()

        run_state = get_run(run_id)
        if run_state.get("status") != "ok":
            raise RuntimeError(run_state.get("error", "Failed to load queued workflow run"))

        return {
            "status": "ok",
            "run": run_state["run"],
            "steps": run_state["steps"],
            "queued": True,
        }

    def _run_async(self, run_id: str, steps: list[dict]) -> None:
        try:
            self._execute_existing_run(run_id=run_id, steps=steps)
        except Exception as e:
            log_run_event(
                run_id=run_id,
                event_type="async_exception",
                message="Unhandled exception in async worker",
                metadata={"error": str(e)},
            )
            ensure_terminal_failed(
                run_id=run_id,
                reason="runtime_exception",
                message=str(e),
            )
        finally:
            self._threads.pop(run_id, None)

    def _execute_existing_run(self, run_id: str, steps: list[dict]) -> dict:
        update_run_status(run_id=run_id, status="running", completed_steps=0)

        completed_steps = 0
        last_error: str | None = None

        try:
            results: list[dict] = []
            for step_index, step in enumerate(steps, start=1):
                tool_name = step["tool"]
                args = dict(step.get("args") or {})
                label = step.get("label")
                started_at = self._now_iso()

                result = tool_registry.execute(tool_name=tool_name, args=args, for_workflow=True)
                step_status = "succeeded" if result.get("status") == "ok" else "failed"
                finished_at = self._now_iso()
                step_error = result.get("error") if step_status == "failed" else None

                log_step(
                    run_id=run_id,
                    step_index=step_index,
                    step_label=label,
                    tool_name=tool_name,
                    args=args,
                    status=step_status,
                    result=result,
                    started_at=started_at,
                    finished_at=finished_at,
                    error=step_error,
                )

                if step_status == "failed":
                    last_error = step_error or f"Step {step_index} failed"
                    log_run_event(
                        run_id=run_id,
                        event_type="step_failure",
                        message=last_error,
                        metadata={"step_index": step_index, "tool": tool_name},
                    )
                    update_run_status(
                        run_id=run_id,
                        status="failed",
                        completed_steps=completed_steps,
                        error=last_error,
                        failure_reason="step_failure",
                    )
                    break

                completed_steps += 1
                update_run_status(
                    run_id=run_id,
                    status="running",
                    completed_steps=completed_steps,
                    error=None,
                    failure_reason=None,
                )
                results.append(
                    {
                        "step_index": step_index,
                        "tool": tool_name,
                        "label": label,
                        "result": result,
                    }
                )
            else:
                update_run_status(
                    run_id=run_id,
                    status="succeeded",
                    completed_steps=completed_steps,
                    error=None,
                    failure_reason=None,
                )

            run_state = get_run(run_id)
            if run_state.get("status") != "ok":
                raise RuntimeError(run_state.get("error", "Failed to load workflow run"))

            return {
                "status": "ok",
                "run": run_state["run"],
                "steps": run_state["steps"],
                "events": run_state.get("events", []),
                "succeeded": last_error is None,
            }
        except Exception as e:
            log_run_event(
                run_id=run_id,
                event_type="runtime_exception",
                message="Unhandled exception during workflow execution",
                metadata={"error": str(e)},
            )
            update_run_status(
                run_id=run_id,
                status="failed",
                completed_steps=completed_steps,
                error=str(e),
                failure_reason="runtime_exception",
            )
            raise

    def get_run(self, run_id: str) -> dict:
        return get_run(run_id)

    def _validate_steps(self, steps: list[dict]) -> None:
        if not steps:
            raise WorkflowGuardError("Workflow must include at least one step")
        if len(steps) > MAX_WORKFLOW_STEPS:
            raise WorkflowGuardError(
                f"Workflow has {len(steps)} steps; max allowed is {MAX_WORKFLOW_STEPS}"
            )
        for index, step in enumerate(steps, start=1):
            tool_name = step.get("tool")
            allowed_tools = tool_registry.list_workflow_tools()
            if tool_name not in allowed_tools:
                raise WorkflowGuardError(
                    f"Step {index} uses unsupported tool '{tool_name}'. Allowed tools: {allowed_tools}"
                )
            args = step.get("args")
            if args is not None and not isinstance(args, dict):
                raise WorkflowGuardError(f"Step {index} args must be an object")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()


orchestrator_service = OrchestratorService()
