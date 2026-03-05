import { NextRequest, NextResponse } from "next/server";
import { withTransaction } from "@/lib/db";

export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const idRaw = searchParams.get("id");

  if (!idRaw) {
    return NextResponse.json({ error: "id query parameter required" }, { status: 400 });
  }

  if (!/^[1-9]\d*$/.test(idRaw)) {
    return NextResponse.json({ error: "id must be a positive integer" }, { status: 400 });
  }
  const id = Number(idRaw);
  if (!Number.isSafeInteger(id)) {
    return NextResponse.json({ error: "id must be a positive integer" }, { status: 400 });
  }

  try {
    await withTransaction(async (client) => {
      const deleted = await client.query<{ name: string; lab_number: string }>(
        `DELETE FROM patients WHERE id = $1 RETURNING name, lab_number`,
        [id]
      );

      if (deleted.rowCount !== 1) {
        throw new Error("Patient not found");
      }

      const { name, lab_number } = deleted.rows[0];

      await client.query(
        `INSERT INTO audit_log (action, entity_type, entity_id, old_value)
         VALUES ('delete', 'patient', $1, $2::jsonb)`,
        [id, JSON.stringify({ name, lab_number })]
      );
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message === "Patient not found") {
      return NextResponse.json({ error: message }, { status: 404 });
    }
    console.error("Patient delete error:", error);
    return NextResponse.json({ error: "Delete failed" }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
