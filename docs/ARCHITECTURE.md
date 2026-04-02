# Architecture Overview

## Goals

- Run locally with clear safety boundaries.
- Provide coding-agent endpoints for ask, tools, retrieval, and staged knowledge.
- Evolve toward service-based orchestration without breaking current APIs.

## Current Component Map

+-------------+      +--------------+      +----------------+
| FastAPI App | ---> |   Routes     | ---> | Tool Modules   |
|  agent.py   |      | ask/tools.py |      | tools/*.py      |
+-------------+      +--------------+      +----------------+
         |                                           |
         |                                           v
         |                                  +----------------+
         +--------------------------------> | Data Backends  |
                                            | SQLite/Chroma  |
                                            +----------------+

## Ask Request Flow

Client -> /ask -> AskService -> Retrieval (optional) -> Ollama -> Response

Detailed:
1. Validate AskRequest.
2. Query vector index when retrieval is enabled.
3. Build prompt from context and user request.
4. Call Ollama generate endpoint.
5. Return model response + retrieval metadata.

## Planned Near-Term Evolution

- Add service boundaries for additional routes.
- Add session persistence and session-aware prompt assembly.
- Add docs-based instruction pipeline with hard-truth precedence.
- Add linear workflow orchestration, then async run tracking.
