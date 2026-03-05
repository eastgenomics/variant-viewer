import { NextRequest, NextResponse } from "next/server";
import { withTransaction } from "@/lib/db";

export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const idRaw = searchParams.get("id");

  if (!idRaw) {
    return NextResponse.json({ error: "id query parameter required" }, { status: 400 });
  }

  const id = parseInt(idRaw, 10);
  if (isNaN(id) || id <= 0) {
    return NextResponse.json({ error: "id must be a positive integer" }, { status: 400 });
  }

  try {
    await withTransaction(async (client) => {
      const sampleRes = await client.query<{ name: string; s3_key: string }>(
        `SELECT name, s3_key FROM samples WHERE id = $1`,
        [id]
      );

      if (sampleRes.rows.length === 0) {
        throw new Error("Sample not found");
      }

      const { name, s3_key } = sampleRes.rows[0];

      await client.query(
        `INSERT INTO audit_log (action, entity_type, entity_id, old_value)
         VALUES ('delete', 'sample', $1, $2)`,
        [id, JSON.stringify({ name, s3_key })]
      );

      await client.query(`DELETE FROM samples WHERE id = $1`, [id]);
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message === "Sample not found") {
      return NextResponse.json({ error: message }, { status: 404 });
    }
    console.error("Sample delete error:", error);
    return NextResponse.json({ error: "Delete failed" }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
