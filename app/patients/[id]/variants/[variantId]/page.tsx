import { notFound } from "next/navigation";
import Link from "next/link";
import { query } from "@/lib/db";
import ClassificationPanel from "./ClassificationPanel";

interface VariantDetail {
  id: number;
  sample_id: number;
  patient_id: number;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  qual: number | null;
  filter: string | null;
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  gnomad_af: number | null;
  clinvar_sig: string | null;
  revel_score: number | null;
  spliceai_max: number | null;
  case_type: "germline" | "somatic";
  pipeline_key: string | null;
}

interface ClassificationDetail {
  id: number;
  framework: string;
  framework_version: string;
  score: number | null;
  classification: string | null;
  locked_at: string | null;
  locked_by: string | null;
}

interface CriterionDetail {
  id: number;
  criterion_code: string;
  applied: boolean;
  strength: string;
  notes: string | null;
  evidence_links: string[] | null;
  pre_computed: boolean;
  pre_computed_value: string | null;
}

async function getVariant(variantId: string): Promise<VariantDetail | null> {
  const r = await query<VariantDetail>(
    `SELECT
       v.id, v.sample_id, s.patient_id,
       v.chrom, v.pos, v.ref, v.alt, v.qual, v.filter,
       v.gene, v.consequence, v.hgvs_c, v.hgvs_p,
       v.gnomad_af, v.clinvar_sig, v.revel_score, v.spliceai_max,
       s.case_type, s.pipeline_key
     FROM variants v
     JOIN samples s ON v.sample_id = s.id
     WHERE v.id = $1`,
    [variantId]
  );
  return r.rows[0] ?? null;
}

async function getClassification(variantId: string): Promise<{
  classification: ClassificationDetail | null;
  criteria: CriterionDetail[];
}> {
  const cls = await query<ClassificationDetail>(
    `SELECT id, framework, framework_version, score, classification,
            locked_at::text, locked_by
     FROM variant_classification
     WHERE variant_id = $1 AND deleted_at IS NULL
     ORDER BY id DESC LIMIT 1`,
    [variantId]
  );

  if (cls.rows.length === 0) return { classification: null, criteria: [] };

  const criteria = await query<CriterionDetail>(
    `SELECT id, criterion_code, applied, strength, notes,
            evidence_links, pre_computed, pre_computed_value
     FROM classification_criterion
     WHERE classification_id = $1
     ORDER BY id ASC`,
    [cls.rows[0].id]
  );

  return { classification: cls.rows[0], criteria: criteria.rows };
}

export default async function ClassificationPage({
  params,
}: {
  params: Promise<{ id: string; variantId: string }>;
}) {
  const { id: patientId, variantId } = await params;
  const [variant, { classification, criteria }] = await Promise.all([
    getVariant(variantId),
    getClassification(variantId),
  ]);

  if (!variant) notFound();

  return (
    <div className="max-w-5xl">
      <div className="mb-4 flex items-center gap-2 text-sm text-gray-400">
        <Link href="/" className="hover:text-gray-600">Patients</Link>
        <span>/</span>
        <Link href={`/patients/${patientId}`} className="hover:text-gray-600">
          Patient {patientId}
        </Link>
        <span>/</span>
        <span>Classify Variant</span>
      </div>

      {/* Variant header */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Gene</div>
            <div className="font-semibold text-gray-900">{variant.gene ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">HGVSc</div>
            <div className="font-mono text-xs text-gray-700">{variant.hgvs_c ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">HGVSp</div>
            <div className="font-mono text-xs text-gray-700">{variant.hgvs_p ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Consequence</div>
            <div className="text-xs text-gray-700">
              {variant.consequence?.replace(/_/g, " ") ?? "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Location</div>
            <div className="font-mono text-xs text-gray-700">
              {variant.chrom}:{variant.pos} {variant.ref}&gt;{variant.alt}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">gnomAD AF</div>
            <div className="font-mono text-xs text-gray-700">
              {variant.gnomad_af != null
                ? variant.gnomad_af < 0.0001
                  ? variant.gnomad_af.toExponential(2)
                  : variant.gnomad_af.toFixed(5)
                : "absent"}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">REVEL</div>
            <div className="font-mono text-xs text-gray-700">
              {variant.revel_score?.toFixed(3) ?? "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">ClinVar</div>
            <div className="text-xs text-gray-700">{variant.clinvar_sig ?? "—"}</div>
          </div>
        </div>
      </div>

      {/* Classification panel (client component) */}
      <ClassificationPanel
        variantId={variant.id}
        caseType={variant.case_type}
        gene={variant.gene}
        initialClassification={classification}
        initialCriteria={criteria}
      />
    </div>
  );
}
