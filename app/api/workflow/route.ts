import { NextRequest, NextResponse } from "next/server";
import { withTransaction } from "@/lib/db";

const VALID_STATUSES = ["pending", "reviewing", "reported", "archived"] as const;
type WorkflowStatus = (typeof VALID_STATUSES)[number];

export async function PATCH(req: NextRequest) {
  let body: { sample_id: number; status: string; user_id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { sample_id, status, user_id } = body;

  // Validate sample_id
  if (typeof sample_id !== "number" || !Number.isInteger(sample_id) || sample_id <= 0) {
    return NextResponse.json(
      { error: "sample_id must be a positive integer" },
      { status: 400 }
    );
  }

  // Validate and normalize status
  if (typeof status !== "string") {
    return NextResponse.json(
      { error: "status must be a string" },
      { status: 400 }
    );
  }

  const normalizedStatus = status.trim().toLowerCase();
  if (!VALID_STATUSES.includes(normalizedStatus as WorkflowStatus)) {
    return NextResponse.json(
      { error: `status must be one of: ${VALID_STATUSES.join(", ")}` },
      { status: 400 }
    );
  }

  await withTransaction(async (client) => {
    const existing = await client.query(
      `SELECT id, status AS old_status FROM workflow WHERE sample_id = $1`,
      [sample_id]
    );

    if (existing.rows.length === 0) {
      // Create if missing (shouldn't happen post-ingest, but be defensive)
      await client.query(
        `INSERT INTO workflow (sample_id, status, updated_at, updated_by)
         VALUES ($1, $2, NOW(), $3)`,
        [sample_id, normalizedStatus, user_id ?? null]
      );
    } else {
      const oldStatus = existing.rows[0].old_status;
      await client.query(
        `UPDATE workflow
         SET status = $1, updated_at = NOW(), updated_by = $2
         WHERE sample_id = $3`,
        [normalizedStatus, user_id ?? null, sample_id]
      );

      await client.query(
        `INSERT INTO audit_log
           (user_id, action, entity_type, entity_id, old_value, new_value)
         VALUES ($1, 'update_workflow', 'workflow', $2, $3, $4)`,
        [
          user_id ?? null,
          existing.rows[0].id,
          JSON.stringify({ status: oldStatus }),
          JSON.stringify({ status: normalizedStatus }),
        ]
      );
    }
  });

  return NextResponse.json({ success: true, sample_id, status: normalizedStatus });
}
