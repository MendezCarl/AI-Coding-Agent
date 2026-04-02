# Sessions and Lifecycle

## Scope

Sessions will provide long-lived conversational continuity and execution history.

## Data Model (Planned)

- sessions
  - id
  - created_at
  - last_activity
  - expires_at
  - metadata

- session_messages
  - id
  - session_id
  - role
  - content
  - created_at

## Lifecycle

1. Create session.
2. Use session_id in ask calls.
3. Persist request/response entries.
4. Refresh last_activity.
5. Expire and cleanup after TTL.

## API Surface (Implemented)

- POST /create_session
  - Input: ttl_hours, metadata
  - Output: session object with id, timestamps, metadata

- POST /get_session
  - Input: session_id, include_messages, limit, offset
  - Output: session object and ordered message history

- POST /list_sessions
  - Input: limit, offset, include_expired
  - Output: paged session list

- POST /cleanup_expired_sessions
  - Input: none
  - Output: deleted session/message counts

## Ask Integration (Implemented)

- AskRequest supports optional session_id.
- AskRequest supports session_context_turns (default 8, max 20).
- When session_id is provided:
  - Recent user/assistant messages are replayed into prompt context before model call.
  - A turn is created atomically with status=started and user message persisted.
  - On success, turn status moves to completed and assistant message is persisted.
  - On failure, turn status moves to failed and an error event message is persisted.
  - Response includes session.id, turn_id, and replayed message count.

## Turn Lifecycle (Implemented)

- started: user message written and turn opened.
- completed: assistant message written and turn finalized.
- failed: error event written and failure stage recorded.

Turn metadata stores context such as retrieval hit count and instruction sources for replay diagnostics.

## Gate for completion

- Session history persists across server restarts.
- Session retrieval endpoint returns ordered message history.
