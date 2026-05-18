"""PR 7 — Classification routes.

POST   /api/variants/{variant_id}/classify
    Score-only: run classification engine, return result, no DB write.

PUT    /api/variants/{variant_id}/classification
    Persist: score + soft-delete existing active classification + insert new
    record with all criteria + audit log entry.

DELETE /api/variants/{variant_id}/classification/{classification_id}
    Reset: soft-delete existing classification + insert blank replacement
    (no criteria, no score) + audit log entry.
"""
import asyncio
import json
from typing import Any, Literal

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.lib import db
from app.lib.classification_engine import (
    AppliedCriterion,
    CombinationRule,
    classify,
    get_framework_version,
)
from app.middleware.auth import require_api_key

router = APIRouter(
    prefix="/api/variants",
    dependencies=[Depends(require_api_key)],
)


# ── Pydantic request/response models ─────────────────────────────────────────


class CriterionIn(BaseModel):
    criterion_code: str
    applied: bool
    strength: str
    notes: str | None = None
    evidence_links: list[str] = []
    pre_computed: bool = False
    pre_computed_value: str | None = None


class CombinationRuleIn(BaseModel):
    rule: str
    codes: list[str]
    message: str


class ClassifyRequest(BaseModel):
    """Score-only — no DB write."""
    criteria: list[CriterionIn]
    framework: Literal["acgs_snv", "svig"]
    combination_rules: list[CombinationRuleIn] = []


class ClassificationSubmitRequest(BaseModel):
    """Persist — score + lock + store criteria."""
    criteria: list[CriterionIn]
    framework: Literal["acgs_snv", "svig"]
    combination_rules: list[CombinationRuleIn] = []
    locked_by: str
    user_id: str


class ResetRequest(BaseModel):
    user_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_criteria(criteria: list[CriterionIn]) -> list[AppliedCriterion]:
    return [
        AppliedCriterion(
            criterion_code=c.criterion_code,
            applied=c.applied,
            strength=c.strength,
        )
        for c in criteria
    ]


def _build_rules(rules: list[CombinationRuleIn]) -> list[CombinationRule]:
    return [CombinationRule(rule=r.rule, codes=r.codes, message=r.message) for r in rules]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/{variant_id}/classify")
async def score_classification(variant_id: int, body: ClassifyRequest) -> dict[str, Any]:
    """Return classification score without persisting to the database."""
    result = classify(_build_criteria(body.criteria), body.framework, _build_rules(body.combination_rules))
    return {
        "score": result.score,
        "classification": result.classification,
        "warnings": result.warnings,
    }


@router.put("/{variant_id}/classification")
async def submit_classification(
    variant_id: int, body: ClassificationSubmitRequest
) -> dict[str, Any]:
    """Score, persist, and lock a classification for a variant.

    Soft-deletes any existing active classification for the variant before
    inserting the new record.  All writes occur in a single transaction.
    """
    # Verify variant exists
    variant_rows = await asyncio.to_thread(
        db.query,
        "SELECT id, case_type, gene FROM variants WHERE id = %s",
        (variant_id,),
    )
    if not variant_rows:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Score
    result = classify(
        _build_criteria(body.criteria),
        body.framework,
        _build_rules(body.combination_rules),
    )
    framework_version = get_framework_version(body.framework)

    def _do(conn) -> int:
        with conn.cursor() as c:
            # Soft-delete any existing active classification
            c.execute(
                "UPDATE variant_classification SET deleted_at=NOW() "
                "WHERE variant_id=%s AND deleted_at IS NULL",
                (variant_id,),
            )

            # Insert new classification record
            c.execute(
                "INSERT INTO variant_classification "
                "(variant_id, framework, framework_version, score, classification, "
                "locked_at, locked_by) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), %s) RETURNING id",
                (
                    variant_id,
                    body.framework,
                    framework_version,
                    result.score,
                    result.classification,
                    body.locked_by,
                ),
            )
            classification_id: int = c.fetchone()[0]

            # Insert individual criteria
            for crit in body.criteria:
                c.execute(
                    "INSERT INTO classification_criterion "
                    "(classification_id, criterion_code, applied, strength, "
                    "notes, evidence_links, pre_computed, pre_computed_value) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        classification_id,
                        crit.criterion_code,
                        crit.applied,
                        crit.strength,
                        crit.notes,
                        psycopg2.extras.Json(crit.evidence_links),
                        crit.pre_computed,
                        crit.pre_computed_value,
                    ),
                )

            # Audit log
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'classify', 'classification', %s, NULL, %s)",
                (
                    body.user_id,
                    classification_id,
                    json.dumps(
                        {
                            "score": result.score,
                            "classification": result.classification,
                            "framework": body.framework,
                        }
                    ),
                ),
            )
        return classification_id

    classification_id = await asyncio.to_thread(db.run_in_transaction, _do)
    return {
        "classification_id": classification_id,
        "score": result.score,
        "classification": result.classification,
        "warnings": result.warnings,
    }


@router.delete("/{variant_id}/classification/{classification_id}")
async def reset_classification(
    variant_id: int, classification_id: int, body: ResetRequest
) -> dict[str, Any]:
    """Soft-delete a classification and insert a blank replacement.

    The blank record preserves the variant↔framework relationship while
    clearing the score, criteria, and lock — ready for re-classification.
    """
    rows = await asyncio.to_thread(
        db.query,
        "SELECT id, variant_id, framework, framework_version "
        "FROM variant_classification WHERE id = %s AND variant_id = %s AND deleted_at IS NULL",
        (classification_id, variant_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Classification not found")

    existing = rows[0]

    def _do(conn) -> int:
        with conn.cursor() as c:
            # Soft-delete existing
            c.execute(
                "UPDATE variant_classification SET deleted_at=NOW() WHERE id=%s",
                (classification_id,),
            )

            # Insert blank replacement
            c.execute(
                "INSERT INTO variant_classification "
                "(variant_id, framework, framework_version) "
                "VALUES (%s, %s, %s) RETURNING id",
                (
                    existing["variant_id"],
                    existing["framework"],
                    existing["framework_version"],
                ),
            )
            new_id: int = c.fetchone()[0]

            # Audit log
            c.execute(
                "INSERT INTO audit_log "
                "(user_id, action, entity_type, entity_id, old_value, new_value) "
                "VALUES (%s, 'reset_classification', 'classification', %s, %s, NULL)",
                (
                    body.user_id,
                    classification_id,
                    json.dumps({"classification_id": classification_id}),
                ),
            )
        return new_id

    new_classification_id = await asyncio.to_thread(db.run_in_transaction, _do)
    return {"new_classification_id": new_classification_id}
