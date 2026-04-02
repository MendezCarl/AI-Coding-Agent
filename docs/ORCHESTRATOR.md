# Orchestrator Specification

## Delivery Sequence

High-risk areas are implemented one-by-one:
1. Sessions
2. Hard-truth instructions
3. Sync orchestrator
4. Async orchestrator
5. Iterative fixing

## Sync Mode (First)

- Execute ordered linear steps.
- Stop on first unrecoverable failure.
- Persist per-step logs by run_id.
- Implemented endpoint: POST /execute_workflow_sync.
- Implemented run lookup: POST /get_workflow_run.

State machine:
PENDING -> RUNNING -> SUCCEEDED | FAILED

Current sync allowlist:
- apply_patch
- diagnostics
- git_diff
- git_status
- grep_search
- list_dir
- query_index
- read
- run
- write

Shared registry note:
- Orchestrator and core tool routes now resolve tool execution through a central tool registry.
- This prevents route/orchestrator drift for core tool argument handling and guardrails.

Current guardrails:
- Max 20 steps per workflow.
- Linear execution only.
- Max 120-second timeout for orchestrated run-command steps.
- Unsupported tools are rejected before execution.

## Async Mode (Second)

- Start run and return run_id.
- Persist run state and step logs.
- Provide polling endpoint for status.
- Implemented endpoint: POST /execute_workflow_async.
- Polling endpoint: POST /get_workflow_run.
- Execution model: in-process background thread per workflow run.
- Restart recovery: any run still in pending, queued, or running state at startup is marked failed with a restart-recovery error.
- Async exceptions are persisted as workflow run events.
- Failed runs include structured failure_reason values.

State machine:
QUEUED -> RUNNING -> SUCCEEDED | FAILED

Failure reason enum:
- restart_recovery
- runtime_exception
- step_failure
- validation_failure

## Safety Controls

- Max step count.
- Per-step timeout caps.
- Tool allowlist for orchestrated runs.

## Iterative Fixing Gate (Implemented as Conservative MVP)

- POST /analyze_failure inspects failure output and returns suggested next actions.
- POST /assisted_fix applies one approved exact-text patch and can rerun one verification command.
- No autonomous retry loop is enabled.
- Verification failure stops the flow and is returned to the caller for review.
