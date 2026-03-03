import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";

const ALLOWED_SORT_COLS = new Set([
  "chrom",
  "pos",
  "gene",
  "consequence",
  "gnomad_af",
  "clinvar_sig",
  "revel_score",
  "spliceai_max",
]);

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 500;

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  const sampleId = searchParams.get("sample_id");
  if (!sampleId) {
    return NextResponse.json(
      { error: "sample_id query parameter required" },
      { status: 400 }
    );
  }

  // Pagination
  const limit = Math.min(
    parseInt(searchParams.get("limit") ?? String(DEFAULT_LIMIT), 10),
    MAX_LIMIT
  );
  const offset = parseInt(searchParams.get("offset") ?? "0", 10);

  // Sorting
  const rawSortBy = searchParams.get("sort_by") ?? "pos";
  const sortBy = ALLOWED_SORT_COLS.has(rawSortBy) ? rawSortBy : "pos";
  const sortDir =
    searchParams.get("sort_dir")?.toUpperCase() === "DESC" ? "DESC" : "ASC";

  // Filters
  const gnomadAfMax = searchParams.get("gnomad_af_max");
  const consequences = searchParams.get("consequences")?.split(",").filter(Boolean);
  const clinvarExclude = searchParams.get("clinvar_exclude")?.split(",").filter(Boolean);
  const gene = searchParams.get("gene");

  const conditions: string[] = ["v.sample_id = $1"];
  const params: unknown[] = [sampleId];
  let paramIdx = 2;

  if (gnomadAfMax) {
    conditions.push(
      `(v.gnomad_af IS NULL OR v.gnomad_af <= $${paramIdx})`
    );
    params.push(parseFloat(gnomadAfMax));
    paramIdx++;
  }

  if (consequences && consequences.length > 0) {
    const placeholders = consequences
      .map((_, i) => `$${paramIdx + i}`)
      .join(", ");
    conditions.push(`v.consequence = ANY(ARRAY[${placeholders}]::text[])`);
    params.push(...consequences);
    paramIdx += consequences.length;
  }

  if (clinvarExclude && clinvarExclude.length > 0) {
    // Exclude variants whose ClinVar sig matches any excluded term
    const placeholders = clinvarExclude
      .map((_, i) => `$${paramIdx + i}`)
      .join(", ");
    conditions.push(
      `(v.clinvar_sig IS NULL OR v.clinvar_sig NOT IN (${placeholders}))`
    );
    params.push(...clinvarExclude);
    paramIdx += clinvarExclude.length;
  }

  if (gene) {
    conditions.push(`v.gene ILIKE $${paramIdx}`);
    params.push(`%${gene}%`);
    paramIdx++;
  }

  const whereClause = conditions.join(" AND ");

  const countResult = await query<{ total: string }>(
    `SELECT COUNT(*) AS total FROM variants v WHERE ${whereClause}`,
    params
  );
  const total = parseInt(countResult.rows[0].total, 10);

  // Fetch page of variants with latest active classification
  const dataResult = await query(
    `SELECT
       v.id, v.chrom, v.pos, v.ref, v.alt, v.qual, v.filter,
       v.gene, v.consequence, v.hgvs_c, v.hgvs_p,
       v.gnomad_af, v.clinvar_sig, v.revel_score, v.spliceai_max,
       vc.id          AS classification_id,
       vc.framework   AS classification_framework,
       vc.score       AS classification_score,
       vc.classification,
       vc.locked_at   AS classification_locked_at
     FROM variants v
     LEFT JOIN LATERAL (
       SELECT id, framework, score, classification, locked_at
       FROM variant_classification
       WHERE variant_id = v.id AND deleted_at IS NULL
       ORDER BY id DESC
       LIMIT 1
     ) vc ON TRUE
     WHERE ${whereClause}
     ORDER BY v.${sortBy} ${sortDir} NULLS LAST, v.id ASC
     LIMIT $${paramIdx} OFFSET $${paramIdx + 1}`,
    [...params, limit, offset]
  );

  return NextResponse.json({
    total,
    limit,
    offset,
    rows: dataResult.rows,
  });
}
