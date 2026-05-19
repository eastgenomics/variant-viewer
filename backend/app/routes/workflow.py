"""PR 7 — Sample workflow status transitions.

PUT /api/workflow/{sample_id}  →  advance or archive a sample's review workflow.

Valid state machine:
    pending   → reviewing, archived
    reviewing → reported, archived
    reported  → archived
    archived  → (terminal)

Every transition appends an audit log entry.
"""
import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.lib import db
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/workflow", dependencies=[Depends(require_api_key)])


class _ConcurrentModification(Exception):
    """Raised inside the DB callback when optimistic lock fails; converted to 409 by the handler."""

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending":   ["reviewing", "archived"],
    "reviewing": ["reported", "archived"],
    "reported":  ["archived"],
    "archived":  [],
}


class WorkflowUpdateRequest(BaseModel):
    status: Literal["reviewing", "reported", "archived"]
    user_id: str


@router.put("/{sample_id}")
async def update_workflow(sample_id: int, body: WorkflowUpdateRequest) -> dict:
    """Transition a sample's workflow status and append an audit log entry."""
    rows = await asyncio.to_thread(
        db.query,
        "SELECT status FROM workflow WHERE sample_id = %s",
        (sample_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Sample workflow not found")

    current: str = rows[0]["status"]
    if body.status not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current} → {body.status}",
        )

    def _do(conn) -> None:
        with conn.cursor() as c:
            c.execute(
                "UPDATE workflow SET status=%s, updated_at=NOW(), updated_by=%s "
                "WHERE sample_id=%s AND status=%s",
                (body.status, body.user_id, sample_id, current),
            )
            if c.rowcount == 0:
                # Status changed between our SELECT and this UPDATE.
                raise _ConcurrentModification()
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    body.user_id,
                    "update_workflow",
                    "workflow",
                    sample_id,
                    json.dumps({"status": current}),
                    json.dumps({"status": body.status}),
                ),
            )

    try:
        await asyncio.to_thread(db.run_in_transaction, _do)
    except _ConcurrentModification as exc:
        raise HTTPException(
            status_code=409,
            detail="Concurrent modification: workflow status changed, please retry",
        ) from exc
    return {"sample_id": sample_id, "status": body.status}
