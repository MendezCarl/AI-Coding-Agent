from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from tools.security import AGENT_ROOT

DB_PATH = AGENT_ROOT / ".agent_data" / "sessions.db"
ALLOWED_TURN_STATUSES = {"started", "completed", "failed"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _expiry_iso(ttl_hours: int) -> str:
    return (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat()


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_activity TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_turns (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            user_message_id TEXT,
            assistant_message_id TEXT,
            error_message_id TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            error_stage TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            failed_at TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_messages_session_id ON session_messages(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_turns_session_id ON session_turns(session_id, started_at)"
    )
    conn.commit()
    return conn


def _hydrate_session(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "last_activity": row["last_activity"],
        "expires_at": row["expires_at"],
        "metadata": json.loads(row["metadata"]),
    }


def _is_expired(expires_at: str) -> bool:
    try:
        return datetime.fromisoformat(expires_at) < datetime.now(UTC)
    except Exception:
        return True


def _load_session(conn: sqlite3.Connection, session_id: str) -> tuple[dict | None, dict | None]:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None, {"status": "error", "error": "Session not found", "session_id": session_id}
    session = _hydrate_session(row)
    if _is_expired(session["expires_at"]):
        return None, {"status": "error", "error": "Session expired", "session_id": session_id}
    return session, None


def _insert_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    created_at: str,
) -> str:
    msg_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO session_messages (id, session_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (msg_id, session_id, role, content, created_at),
    )
    return msg_id


def _merge_metadata(existing_json: str, patch: dict | None) -> str:
    existing = json.loads(existing_json) if existing_json else {}
    if patch:
        existing.update(patch)
    return json.dumps(existing)


def create_session(ttl_hours: int = 168, metadata: dict | None = None) -> dict:
    try:
        session_id = str(uuid4())
        now = _now_iso()
        expires_at = _expiry_iso(ttl_hours)
        metadata_json = json.dumps(metadata or {})

        with _db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, created_at, last_activity, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, now, now, expires_at, metadata_json),
            )
            conn.commit()

        return {
            "status": "ok",
            "session": {
                "id": session_id,
                "created_at": now,
                "last_activity": now,
                "expires_at": expires_at,
                "metadata": metadata or {},
            },
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def cleanup_expired_sessions() -> dict:
    try:
        now = _now_iso()
        with _db() as conn:
            sessions_cursor = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            messages_cursor = conn.execute(
                """
                DELETE FROM session_messages
                WHERE session_id NOT IN (SELECT id FROM sessions)
                """
            )
            turns_cursor = conn.execute(
                """
                DELETE FROM session_turns
                WHERE session_id NOT IN (SELECT id FROM sessions)
                """
            )
            conn.commit()

        return {
            "status": "ok",
            "deleted_sessions": sessions_cursor.rowcount,
            "deleted_messages": messages_cursor.rowcount,
            "deleted_turns": turns_cursor.rowcount,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_session(
    session_id: str,
    include_messages: bool = True,
    include_turns: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    try:
        with _db() as conn:
            session, error = _load_session(conn, session_id)
            if error:
                return error

            if include_messages:
                message_rows = conn.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?
                    """,
                    (session_id, limit, offset),
                ).fetchall()
                messages = [dict(m) for m in message_rows]
            else:
                messages = []

            if include_turns:
                turn_rows = conn.execute(
                    """
                    SELECT *
                    FROM session_turns
                    WHERE session_id = ?
                    ORDER BY started_at ASC
                    LIMIT ? OFFSET ?
                    """,
                    (session_id, limit, offset),
                ).fetchall()
                turns = [
                    {
                        "id": row["id"],
                        "status": row["status"],
                        "user_message_id": row["user_message_id"],
                        "assistant_message_id": row["assistant_message_id"],
                        "error_message_id": row["error_message_id"],
                        "metadata": json.loads(row["metadata"]),
                        "error": row["error"],
                        "error_stage": row["error_stage"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "failed_at": row["failed_at"],
                    }
                    for row in turn_rows
                ]
            else:
                turns = []

        return {
            "status": "ok",
            "session": session,
            "messages": messages,
            "turns": turns,
            "count": len(messages),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "session_id": session_id}


def list_sessions(limit: int = 50, offset: int = 0, include_expired: bool = False) -> dict:
    try:
        with _db() as conn:
            if include_expired:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY last_activity DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                count_row = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
            else:
                now = _now_iso()
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE expires_at >= ?
                    ORDER BY last_activity DESC
                    LIMIT ? OFFSET ?
                    """,
                    (now, limit, offset),
                ).fetchall()
                count_row = conn.execute(
                    "SELECT COUNT(*) AS count FROM sessions WHERE expires_at >= ?",
                    (now,),
                ).fetchone()

        sessions = [_hydrate_session(r) for r in rows]
        return {
            "status": "ok",
            "sessions": sessions,
            "count": len(sessions),
            "total": count_row["count"] if count_row else 0,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def append_message(session_id: str, role: str, content: str) -> dict:
    try:
        with _db() as conn:
            _, error = _load_session(conn, session_id)
            if error:
                return error

            now = _now_iso()
            msg_id = _insert_message(conn, session_id, role, content, now)
            conn.execute("UPDATE sessions SET last_activity = ? WHERE id = ?", (now, session_id))
            conn.commit()

        return {"status": "ok", "message_id": msg_id, "created_at": now}
    except Exception as e:
        return {"status": "error", "error": str(e), "session_id": session_id}


def get_recent_messages(session_id: str, limit: int = 8) -> dict:
    try:
        if limit <= 0:
            return {"status": "ok", "messages": [], "count": 0, "limit": 0}

        with _db() as conn:
            _, error = _load_session(conn, session_id)
            if error:
                return error

            rows = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM session_messages
                WHERE session_id = ? AND role IN ('user', 'assistant')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        messages = [dict(row) for row in reversed(rows)]
        return {
            "status": "ok",
            "messages": messages,
            "count": len(messages),
            "limit": limit,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "session_id": session_id}


def begin_turn(session_id: str, user_content: str, metadata: dict | None = None) -> dict:
    try:
        now = _now_iso()
        turn_id = str(uuid4())

        with _db() as conn:
            _, error = _load_session(conn, session_id)
            if error:
                return error

            user_message_id = _insert_message(conn, session_id, "user", user_content, now)
            conn.execute(
                """
                INSERT INTO session_turns (
                    id, session_id, status, user_message_id, metadata,
                    error, error_stage, started_at, completed_at, failed_at
                ) VALUES (?, ?, 'started', ?, ?, NULL, NULL, ?, NULL, NULL)
                """,
                (turn_id, session_id, user_message_id, json.dumps(metadata or {}), now),
            )
            conn.execute("UPDATE sessions SET last_activity = ? WHERE id = ?", (now, session_id))
            conn.commit()

        return {
            "status": "ok",
            "turn_id": turn_id,
            "user_message_id": user_message_id,
            "started_at": now,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "session_id": session_id}


def complete_turn(
    session_id: str,
    turn_id: str,
    assistant_content: str,
    metadata: dict | None = None,
) -> dict:
    try:
        now = _now_iso()
        with _db() as conn:
            _, error = _load_session(conn, session_id)
            if error:
                return error

            turn_row = conn.execute(
                "SELECT * FROM session_turns WHERE id = ? AND session_id = ?",
                (turn_id, session_id),
            ).fetchone()
            if not turn_row:
                return {"status": "error", "error": "Turn not found", "turn_id": turn_id}
            if turn_row["status"] not in ALLOWED_TURN_STATUSES or turn_row["status"] != "started":
                return {
                    "status": "error",
                    "error": f"Turn is not in started state: {turn_row['status']}",
                    "turn_id": turn_id,
                }

            assistant_message_id = _insert_message(conn, session_id, "assistant", assistant_content, now)
            merged_metadata = _merge_metadata(turn_row["metadata"], metadata)
            conn.execute(
                """
                UPDATE session_turns
                SET status = 'completed', assistant_message_id = ?, metadata = ?,
                    completed_at = ?, failed_at = NULL, error = NULL, error_stage = NULL
                WHERE id = ?
                """,
                (assistant_message_id, merged_metadata, now, turn_id),
            )
            conn.execute("UPDATE sessions SET last_activity = ? WHERE id = ?", (now, session_id))
            conn.commit()

        return {
            "status": "ok",
            "turn_id": turn_id,
            "assistant_message_id": assistant_message_id,
            "completed_at": now,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "turn_id": turn_id}


def fail_turn(
    session_id: str,
    turn_id: str,
    error: str,
    error_stage: str,
    metadata: dict | None = None,
) -> dict:
    try:
        now = _now_iso()
        error_content = f"stage={error_stage}: {error}"
        with _db() as conn:
            _, session_error = _load_session(conn, session_id)
            if session_error:
                return session_error

            turn_row = conn.execute(
                "SELECT * FROM session_turns WHERE id = ? AND session_id = ?",
                (turn_id, session_id),
            ).fetchone()
            if not turn_row:
                return {"status": "error", "error": "Turn not found", "turn_id": turn_id}

            error_message_id = _insert_message(conn, session_id, "error", error_content, now)
            merged_metadata = _merge_metadata(turn_row["metadata"], metadata)
            conn.execute(
                """
                UPDATE session_turns
                SET status = 'failed', error_message_id = ?, metadata = ?,
                    error = ?, error_stage = ?, failed_at = ?
                WHERE id = ?
                """,
                (error_message_id, merged_metadata, error, error_stage, now, turn_id),
            )
            conn.execute("UPDATE sessions SET last_activity = ? WHERE id = ?", (now, session_id))
            conn.commit()

        return {
            "status": "ok",
            "turn_id": turn_id,
            "error_message_id": error_message_id,
            "failed_at": now,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "turn_id": turn_id}
