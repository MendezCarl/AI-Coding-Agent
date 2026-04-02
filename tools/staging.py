from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from tools.security import AGENT_ROOT
from tools.vector_index import create_index, upsert_documents

DB_PATH = AGENT_ROOT / ".agent_data" / "proposals.db"
ALLOWED_STATUSES = {"pending", "approved", "rejected", "expired"}
ALLOWED_REFRESH_ACTIONS = {"reset_expiry", "mark_pending"}


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            index_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            approved_at TEXT,
            approved_by TEXT,
            rejection_reason TEXT,
            version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _expiry_iso(ttl_hours: int) -> str:
    return (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat()


def _hydrate(row: sqlite3.Row) -> dict:
    payload = json.loads(row["payload"])
    return {
        "id": row["id"],
        "status": row["status"],
        "index_name": row["index_name"],
        "payload": payload,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "approved_at": row["approved_at"],
        "approved_by": row["approved_by"],
        "rejection_reason": row["rejection_reason"],
        "version": row["version"],
    }


def cleanup_expired() -> dict:
    try:
        now = _now_iso()
        with _db() as conn:
            cursor = conn.execute(
                """
                UPDATE proposals
                SET status = 'expired', version = version + 1
                WHERE status = 'pending' AND expires_at < ?
                """,
                (now,),
            )
            conn.commit()

        return {
            "status": "ok",
            "expired_count": cursor.rowcount,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def stage_document(index_name: str, document: dict, ttl_hours: int = 168) -> dict:
    try:
        proposal_id = str(uuid4())
        now = _now_iso()
        expires_at = _expiry_iso(ttl_hours)
        payload = json.dumps(document)

        with _db() as conn:
            conn.execute(
                """
                INSERT INTO proposals (
                    id, status, index_name, payload, created_at, expires_at, version
                ) VALUES (?, 'pending', ?, ?, ?, ?, 1)
                """,
                (proposal_id, index_name, payload, now, expires_at),
            )
            conn.commit()

        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "proposal": {
                "id": proposal_id,
                "status": "pending",
                "index_name": index_name,
                "payload": document,
                "created_at": now,
                "expires_at": expires_at,
                "approved_at": None,
                "approved_by": None,
                "rejection_reason": None,
                "version": 1,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def get_proposal(proposal_id: str) -> dict:
    try:
        with _db() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

        if not row:
            return {
                "status": "error",
                "error": "Proposal not found",
                "proposal_id": proposal_id,
            }

        proposal = _hydrate(row)

        return {
            "status": "ok",
            "proposal": proposal,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "proposal_id": proposal_id,
        }


def list_proposals(
    index_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    try:
        if status is not None and status not in ALLOWED_STATUSES:
            return {
                "status": "error",
                "error": f"Invalid status: {status}",
            }

        clauses: list[str] = []
        params: list[object] = []

        if index_name:
            clauses.append("index_name = ?")
            params.append(index_name)

        if status:
            clauses.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        with _db() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM proposals
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()

            count_params = params[:-2]
            count_row = conn.execute(
                f"SELECT COUNT(*) AS count FROM proposals {where_clause}",
                count_params,
            ).fetchone()

        proposals = [_hydrate(row) for row in rows]

        return {
            "status": "ok",
            "total": count_row["count"] if count_row else 0,
            "count": len(proposals),
            "proposals": proposals,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def approve_proposal(proposal_id: str, approved_by: str | None = None) -> dict:
    try:
        with _db() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

            if not row:
                return {
                    "status": "error",
                    "error": "Proposal not found",
                    "proposal_id": proposal_id,
                }

            proposal = _hydrate(row)

            if proposal["status"] == "approved":
                return {
                    "status": "ok",
                    "proposal_id": proposal_id,
                    "already_approved": True,
                    "proposal": proposal,
                }

            if proposal["status"] != "pending":
                return {
                    "status": "error",
                    "error": f"Proposal is not pending (status={proposal['status']})",
                    "proposal_id": proposal_id,
                }

            create_result = create_index(index_name=proposal["index_name"], reset=False)
            if create_result.get("status") != "ok":
                return {
                    "status": "error",
                    "error": "Failed to ensure vector index",
                    "proposal_id": proposal_id,
                    "create_index": create_result,
                }

            upsert_result = upsert_documents(
                index_name=proposal["index_name"],
                documents=[proposal["payload"]],
            )
            if upsert_result.get("status") != "ok":
                return {
                    "status": "error",
                    "error": "Failed to upsert approved proposal",
                    "proposal_id": proposal_id,
                    "upsert": upsert_result,
                }

            approved_at = _now_iso()
            cursor = conn.execute(
                """
                UPDATE proposals
                SET status = 'approved',
                    approved_at = ?,
                    approved_by = ?,
                    rejection_reason = NULL,
                    version = version + 1
                WHERE id = ? AND status = 'pending' AND version = ?
                """,
                (approved_at, approved_by, proposal_id, proposal["version"]),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return {
                    "status": "error",
                    "error": "Proposal state changed during approval. Retry.",
                    "proposal_id": proposal_id,
                }

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "proposal": _hydrate(updated) if updated else None,
            "upsert": upsert_result,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "proposal_id": proposal_id,
        }


def reject_proposal(proposal_id: str, reason: str = "") -> dict:
    try:
        with _db() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

            if not row:
                return {
                    "status": "error",
                    "error": "Proposal not found",
                    "proposal_id": proposal_id,
                }

            proposal = _hydrate(row)
            if proposal["status"] == "approved":
                return {
                    "status": "error",
                    "error": "Cannot reject an approved proposal",
                    "proposal_id": proposal_id,
                }

            if proposal["status"] == "rejected":
                return {
                    "status": "ok",
                    "proposal_id": proposal_id,
                    "already_rejected": True,
                    "proposal": proposal,
                }

            cursor = conn.execute(
                """
                UPDATE proposals
                SET status = 'rejected',
                    rejection_reason = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (reason, proposal_id, proposal["version"]),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return {
                    "status": "error",
                    "error": "Proposal state changed during rejection. Retry.",
                    "proposal_id": proposal_id,
                }

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "proposal": _hydrate(updated) if updated else None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "proposal_id": proposal_id,
        }


def refresh_proposal(proposal_id: str, action: str, ttl_hours: int = 168) -> dict:
    try:
        if action not in ALLOWED_REFRESH_ACTIONS:
            return {
                "status": "error",
                "error": f"Invalid action: {action}",
                "proposal_id": proposal_id,
            }

        with _db() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

            if not row:
                return {
                    "status": "error",
                    "error": "Proposal not found",
                    "proposal_id": proposal_id,
                }

            proposal = _hydrate(row)
            if proposal["status"] == "approved":
                return {
                    "status": "error",
                    "error": "Cannot refresh an approved proposal",
                    "proposal_id": proposal_id,
                }

            expires_at = _expiry_iso(ttl_hours)
            new_status = "pending" if action == "mark_pending" else proposal["status"]

            cursor = conn.execute(
                """
                UPDATE proposals
                SET expires_at = ?,
                    status = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (expires_at, new_status, proposal_id, proposal["version"]),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return {
                    "status": "error",
                    "error": "Proposal state changed during refresh. Retry.",
                    "proposal_id": proposal_id,
                }

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()

        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "proposal": _hydrate(updated) if updated else None,
            "action": action,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "proposal_id": proposal_id,
        }
