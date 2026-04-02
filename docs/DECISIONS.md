# Architecture Decision Log

## ADR-001: Local-first deployment
Status: Accepted

Context:
- Primary goal is a coding agent that runs locally.

Decision:
- Use FastAPI + local Ollama endpoint.

Consequences:
- Simpler deployment and privacy.
- Dependence on local model availability and resources.

## ADR-002: SQLite-first persistence with adapter boundary
Status: Accepted

Context:
- Need fast implementation with future robust storage path.

Decision:
- Build persistence with SQLite first and keep repository abstraction Postgres-ready.

Consequences:
- Fast MVP delivery.
- Additional adapter work needed for Postgres migration.

## ADR-003: Hard truths via ALL-CAPS markdown in docs/
Status: Accepted

Context:
- Need explicit non-negotiable constraints for agent behavior.

Decision:
- Any ALL-CAPS markdown filename in docs/ is treated as a hard-truth source.

Consequences:
- Clear convention and low authoring overhead.
- Requires deterministic precedence and conflict reporting.
