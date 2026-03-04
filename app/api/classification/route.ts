import { NextRequest, NextResponse } from "next/server";
import { withTransaction, query } from "@/lib/db";
import {
  classify,
  Framework,
  AppliedCriterion,
  CombinationRule,
  getFrameworkVersion,
} from "@/lib/classification-engine";
import acgsCriteria from "@/config/acgs-snv-criteria.json";
import svigCriteria from "@/config/svig-criteria.json";
import { query as dbQuery } from "@/lib/db";

function getRules(framework: Framework): CombinationRule[] {
  return (
    (framework === "acgs_snv"
      ? acgsCriteria.combination_rules
      : svigCriteria.combination_rules) as CombinationRule[]
  );
}

/** POST /api/classification — create or replace classification + criteria */
export async function POST(req: NextRequest) {
  let body: {
    variant_id: number;
    framework: Framework;
    criteria: AppliedCriterion[];
    locked?: boolean;
    user_id?: string;
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // TODO: Do not trust client-supplied user_id - extract from authenticated session
  // For now, user_id is accepted but should be replaced with server-side auth
  const { variant_id, framework, criteria, locked = false, user_id } = body;
  if (!variant_id || !framework || !criteria) {
    return NextResponse.json(
      { error: "variant_id, framework, and criteria are required" },
      { status: 400 }
    );
  }

  const rules = getRules(framework);
  const { score, classification, warnings } = classify(criteria, framework, rules);
  const frameworkVersion = getFrameworkVersion(framework);

  try {
    const result = await withTransaction(async (client) => {
    // Check if an active locked classification already exists
    const lockedCheck = await client.query(
      `SELECT id FROM variant_classification
       WHERE variant_id = $1 AND deleted_at IS NULL AND locked_at IS NOT NULL`,
      [variant_id]
    );

    if (lockedCheck.rows.length > 0) {
      throw new Error("Cannot replace a locked classification");
    }

    // Soft-delete any existing non-locked classification for this variant
    await client.query(
      `UPDATE variant_classification
       SET deleted_at = NOW()
       WHERE variant_id = $1 AND deleted_at IS NULL AND locked_at IS NULL`,
      [variant_id]
    );

    // Create new classification record
    const classRes = await client.query<{ id: number }>(
      `INSERT INTO variant_classification
         (variant_id, framework, framework_version, score, classification,
          locked_at, locked_by)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING id`,
      [
        variant_id,
        framework,
        frameworkVersion,
        score,
        classification,
        locked ? new Date().toISOString() : null,
        locked ? (user_id ?? null) : null,
      ]
    );
    const classId = classRes.rows[0].id;

    // Insert criteria
    for (const c of criteria) {
      await client.query(
        `INSERT INTO classification_criterion
           (classification_id, criterion_code, applied, strength,
            notes, evidence_links, pre_computed, pre_computed_value)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          classId,
          c.criterion_code,
          c.applied,
          c.strength,
          (c as { notes?: string }).notes ?? null,
          (c as { evidence_links?: string[] }).evidence_links ?? null,
          (c as { pre_computed?: boolean }).pre_computed ?? false,
          (c as { pre_computed_value?: string }).pre_computed_value ?? null,
        ]
      );
    }

    // Audit log
    await client.query(
      `INSERT INTO audit_log (user_id, action, entity_type, entity_id, new_value)
       VALUES ($1, 'classify', 'classification', $2, $3)`,
      [
        user_id ?? null,
        classId,
        JSON.stringify({ variant_id, framework, score, classification, locked }),
      ]
    );

      return { classId, score, classification, warnings };
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Classification creation failed";
    if (message === "Cannot replace a locked classification") {
      return NextResponse.json({ error: message }, { status: 409 });
    }
    console.error("Classification creation error:", error);
    return NextResponse.json({ error: "Classification creation failed" }, { status: 500 });
  }
}

/** PATCH /api/classification — update criteria on an existing classification */
export async function PATCH(req: NextRequest) {
  let body: {
    classification_id: number;
    criteria: (AppliedCriterion & {
      id?: number;
      notes?: string;
      evidence_links?: string[];
    })[];
    lock?: boolean;
    user_id?: string;
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { classification_id, criteria, lock = false, user_id } = body;
  if (!classification_id || !criteria) {
    return NextResponse.json(
      { error: "classification_id and criteria are required" },
      { status: 400 }
    );
  }

  try {
    let score: number, classification: string, warnings: string[];

    await withTransaction(async (client) => {
      // Fetch current classification with row lock to prevent concurrent modification
      const existing = await client.query<{
        id: number;
        variant_id: number;
        framework: Framework;
        locked_at: string | null;
        deleted_at: string | null;
      }>(
        `SELECT id, variant_id, framework, locked_at, deleted_at
         FROM variant_classification
         WHERE id = $1
         FOR UPDATE`,
        [classification_id]
      );

      if (existing.rows.length === 0) {
        throw new Error("Classification not found");
      }

      const cls = existing.rows[0];
      if (cls.locked_at) {
        throw new Error("Classification is locked and cannot be modified");
      }
      if (cls.deleted_at) {
        throw new Error("Classification has been deleted");
      }

      const rules = getRules(cls.framework);
      const result = classify(
        criteria as AppliedCriterion[],
        cls.framework,
        rules
      );
      score = result.score;
      classification = result.classification;
      warnings = result.warnings;

      // Delete existing criteria and re-insert
      await client.query(
        "DELETE FROM classification_criterion WHERE classification_id = $1",
        [classification_id]
      );

      for (const c of criteria) {
        await client.query(
          `INSERT INTO classification_criterion
             (classification_id, criterion_code, applied, strength,
              notes, evidence_links, pre_computed, pre_computed_value)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
          [
            classification_id,
            c.criterion_code,
            c.applied,
            c.strength,
            c.notes ?? null,
            c.evidence_links ?? null,
            (c as { pre_computed?: boolean }).pre_computed ?? false,
            (c as { pre_computed_value?: string }).pre_computed_value ?? null,
          ]
        );
      }

      // Update score/classification and optionally lock with double-check
      const updateRes = await client.query(
        `UPDATE variant_classification
         SET score = $1, classification = $2,
             locked_at = $3, locked_by = $4
         WHERE id = $5 AND locked_at IS NULL AND deleted_at IS NULL`,
        [
          score,
          classification,
          lock ? new Date().toISOString() : null,
          lock ? (user_id ?? null) : null,
          classification_id,
        ]
      );

      if (updateRes.rowCount !== 1) {
        throw new Error("Classification changed concurrently");
      }

      // Audit log
      await client.query(
        `INSERT INTO audit_log (user_id, action, entity_type, entity_id, new_value)
         VALUES ($1, 'update_classification', 'classification', $2, $3)`,
        [
          user_id ?? null,
          classification_id,
          JSON.stringify({ score, classification, lock }),
        ]
      );
    });

    return NextResponse.json({ score, classification, warnings });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Update failed";
    if (message === "Classification not found") {
      return NextResponse.json({ error: message }, { status: 404 });
    }
    if (message === "Classification is locked and cannot be modified") {
      return NextResponse.json({ error: message }, { status: 409 });
    }
    if (message === "Classification has been deleted") {
      return NextResponse.json({ error: message }, { status: 410 });
    }
    if (message === "Classification changed concurrently") {
      return NextResponse.json({ error: message }, { status: 409 });
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

/** DELETE /api/classification — soft-delete (reset) a classification */
export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get("id");
  const userId = searchParams.get("user_id");
  if (!id) {
    return NextResponse.json({ error: "id query parameter required" }, { status: 400 });
  }

  await withTransaction(async (client) => {
    await client.query(
      `UPDATE variant_classification SET deleted_at = NOW() WHERE id = $1`,
      [id]
    );
    await client.query(
      `INSERT INTO audit_log (user_id, action, entity_type, entity_id, new_value)
       VALUES ($1, 'reset_classification', 'classification', $2, $3)`,
      [userId ?? null, id, JSON.stringify({ deleted: true })]
    );
  });

  return NextResponse.json({ success: true });
}

/** GET /api/classification?variant_id=X — fetch active classification + criteria */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const variantId = searchParams.get("variant_id");
  if (!variantId) {
    return NextResponse.json(
      { error: "variant_id query parameter required" },
      { status: 400 }
    );
  }

  const cls = await query(
    `SELECT id, framework, framework_version, score, classification,
            locked_at, locked_by
     FROM variant_classification
     WHERE variant_id = $1 AND deleted_at IS NULL
     ORDER BY id DESC
     LIMIT 1`,
    [variantId]
  );

  if (cls.rows.length === 0) {
    return NextResponse.json({ classification: null, criteria: [] });
  }

  const classId = cls.rows[0].id;
  const criteria = await query(
    `SELECT id, criterion_code, applied, strength, notes,
            evidence_links, pre_computed, pre_computed_value
     FROM classification_criterion
     WHERE classification_id = $1
     ORDER BY id ASC`,
    [classId]
  );

  return NextResponse.json({
    classification: cls.rows[0],
    criteria: criteria.rows,
  });
}
