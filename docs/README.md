# Documentation Index

This folder contains implementation and operational documentation for the local coding agent.

## Documents

- ARCHITECTURE.md: component map and request/data flows.
- TOOLS.md: tool contracts and safety guardrails.
- DECISIONS.md: ADR-style decision log.
- SESSIONS.md: planned session lifecycle and persistence model.
- INSTRUCTIONS.md: markdown instruction loading and hard-truth precedence.
- ORCHESTRATOR.md: sync/async orchestration model and run states.
- RUNBOOK.md: local setup, troubleshooting, and recovery checks.

## Conventions

- Use ASCII diagrams only.
- Keep docs synchronized with code changes in the same PR.
- Prefer deterministic behavior and explicit failure semantics.
- Model-facing instruction markdown belongs under docs/instructions/.
