from __future__ import annotations

from datetime import UTC, datetime
import threading
from services.tool_registry import MAX_WORKFLOW_STEPS, tool_registry
from tools.workflow_runs import (
    create_run,
    ensure_terminal_failed,
    get_interactive_state,
    get_run,
    log_run_event,
    log_step,
    save_interactive_state,
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

    def start_interactive(
        self,
        steps: list[dict],
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Begin interactive execution: run server-side steps immediately, pause on first local tool.

        Returns either:
          {"status": "ok", "run_id": ..., "next": "tool_call", "tool_call": {tool, args, label, step_index}}
          {"status": "ok", "run_id": ..., "next": "complete", "run": ..., "steps": ...}
          {"status": "ok", "run_id": ..., "next": "failed",   "error": ...}
        """
        self._validate_steps(steps)
        run_record = create_run(total_steps=len(steps), session_id=session_id, metadata=metadata)
        if run_record.get("status") != "ok":
            raise RuntimeError(run_record.get("error", "Failed to create workflow run"))
        run_id = run_record["run_id"]
        update_run_status(run_id=run_id, status="running", completed_steps=0)
        return self._advance(run_id=run_id, remaining_steps=steps, completed_steps=0, log_index_start=1)

    def resume_interactive(self, run_id: str, tool_name: str, result: dict) -> dict:
        """Inject the client's local tool result and continue execution until the next pause or completion."""
        run_state = get_run(run_id)
        if run_state.get("status") != "ok":
            return {"status": "error", "error": run_state.get("error", "Run not found")}

        current_status = run_state["run"]["status"]
        if current_status != "waiting_for_tool":
            return {
                "status": "error",
                "error": f"Run is not waiting for a tool result (current status: {current_status})",
            }

        istate_resp = get_interactive_state(run_id)
        if istate_resp.get("status") != "ok":
            return {"status": "error", "error": istate_resp.get("error", "No interactive state")}

        istate = istate_resp["state"]
        awaited_tool = istate["awaited_tool"]
        if tool_name != awaited_tool:
            return {
                "status": "error",
                "error": f"Unexpected tool result: expected '{awaited_tool}', got '{tool_name}'",
            }

        remaining_steps: list[dict] = istate["remaining_steps"]
        completed_steps: int = istate["completed_steps"]
        step_index: int = istate["step_index"]
        started_at: str = istate["awaited_started_at"]
        current_step = remaining_steps[0]

        finished_at = self._now_iso()
        step_status = "succeeded" if result.get("status") == "ok" else "failed"
        log_step(
            run_id=run_id,
            step_index=step_index,
            step_label=current_step.get("label"),
            tool_name=tool_name,
            args=current_step.get("args", {}),
            status=step_status,
            result=result,
            started_at=started_at,
            finished_at=finished_at,
            error=result.get("error") if step_status == "failed" else None,
        )

        if step_status == "failed":
            error_msg = result.get("error") or f"Step {step_index} ({tool_name}) failed"
            log_run_event(run_id, "step_failure", error_msg, {"step_index": step_index, "tool": tool_name})
            update_run_status(
                run_id=run_id,
                status="failed",
                completed_steps=completed_steps,
                error=error_msg,
                failure_reason="step_failure",
            )
            return {"status": "ok", "run_id": run_id, "next": "failed", "error": error_msg}

        completed_steps += 1
        update_run_status(run_id=run_id, status="running", completed_steps=completed_steps)
        return self._advance(
            run_id=run_id,
            remaining_steps=remaining_steps[1:],
            completed_steps=completed_steps,
            log_index_start=step_index + 1,
        )

    def _advance(
        self,
        run_id: str,
        remaining_steps: list[dict],
        completed_steps: int,
        log_index_start: int,
    ) -> dict:
        """Execute server-side steps until a local tool is reached or all steps complete."""
        for i, step in enumerate(remaining_steps):
            step_index = log_index_start + i
            tool_name = step["tool"]
            args = dict(step.get("args") or {})
            label = step.get("label")
            started_at = self._now_iso()

            spec = tool_registry.get_spec(tool_name)
            if spec and spec.local:
                # Pause — client must execute this tool and call resume_interactive
                istate = {
                    "remaining_steps": remaining_steps[i:],
                    "completed_steps": completed_steps,
                    "step_index": step_index,
                    "awaited_tool": tool_name,
                    "awaited_args": args,
                    "awaited_started_at": started_at,
                }
                save_interactive_state(run_id, istate)
                update_run_status(run_id=run_id, status="waiting_for_tool", completed_steps=completed_steps)
                return {
                    "status": "ok",
                    "run_id": run_id,
                    "next": "tool_call",
                    "tool_call": {
                        "tool": tool_name,
                        "args": args,
                        "label": label,
                        "step_index": step_index,
                    },
                }

            # Execute on server immediately
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
                error_msg = step_error or f"Step {step_index} ({tool_name}) failed"
                log_run_event(run_id, "step_failure", error_msg, {"step_index": step_index, "tool": tool_name})
                update_run_status(
                    run_id=run_id,
                    status="failed",
                    completed_steps=completed_steps,
                    error=error_msg,
                    failure_reason="step_failure",
                )
                return {"status": "ok", "run_id": run_id, "next": "failed", "error": error_msg}

            completed_steps += 1
            update_run_status(run_id=run_id, status="running", completed_steps=completed_steps)

        # All steps complete
        update_run_status(run_id=run_id, status="succeeded", completed_steps=completed_steps)
        run_state = get_run(run_id)
        return {
            "status": "ok",
            "run_id": run_id,
            "next": "complete",
            "run": run_state.get("run", {}),
            "steps": run_state.get("steps", []),
        }
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
