# Runbook

## Local Startup

1. Activate virtual environment.
2. Ensure Ollama is running and model is available.
3. Start server with ./start_server.sh.
4. Check health endpoint.

## Basic Validation

- GET /health returns status ok.
- POST /ask returns response and retrieval metadata.
- Tool endpoints return status-based payloads.

CLI smoke checks:
- `./install_earl.sh` (optional, installs `earl` into `~/.local/bin`)
- `./earl --help`
- `./earl health`
- `./earl ask "Return only ok" --output json`
- `./earl session create`
- `./earl workflow sync --steps-json '[{"tool":"list_dir","args":{"path":"."}}]'`
- `./earl workflow async --steps-json '[{"tool":"list_dir","args":{"path":"."}}]'`
- `./earl workflow get --run-id <RUN_ID> --watch --progress --events`
- `./earl tools list-dir --path .`
- `./earl fix analyze-failure --error-output "NameError: name 'x' is not defined\napp.py:3"`

Milestone 4 watch-mode options:
- `--progress/--no-progress`: show per-poll status/progress/elapsed updates in human mode.
- `--events/--no-events`: stream newly observed workflow run events while polling.
- `--output json`: suppress watch progress/event text and print only final JSON payload.

## Troubleshooting

1. Ollama unavailable
- Symptom: ask endpoint fails with HTTP error.
- Action: verify Ollama process and model pull.

2. Vector index issues
- Symptom: query_index returns errors or no hits.
- Action: verify .agent_data/chroma permissions and index existence.

3. SQLite staging issues
- Symptom: staging calls fail.
- Action: verify .agent_data/proposals.db write access.

4. Fix-flow verification failure
- Symptom: assisted_fix applies patch but verification reports non-zero return code.
- Action: inspect verification stdout/stderr, review the patch, and decide whether to revert or apply a refined follow-up fix manually.

## Failure Analysis Workflow

1. Send raw traceback or test failure output to /analyze_failure.
2. Review referenced files, symbol hints, and suggested actions.
3. If a narrow exact-text correction is appropriate, call /assisted_fix with approved=true.
4. Optionally provide one verification command to validate the change.

## Recovery Checks

- Restart service and verify health.
- Re-run a known /ask request.
- Verify staged proposal listing still works.
