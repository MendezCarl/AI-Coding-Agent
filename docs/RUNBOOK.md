# Runbook

## Local Startup

1. Activate virtual environment.
2. Ensure Ollama is running and model is available.
3. Start server with `uvicorn agent:app --host 0.0.0.0 --port 8000`.
4. Check health endpoint.

## Basic Validation

- GET /health returns status ok.
- POST /ask returns response and retrieval metadata.
- Tool endpoints return status-based payloads.

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
