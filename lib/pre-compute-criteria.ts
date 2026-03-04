import { VcfVariant } from "./vcf-parser";
import canvigMtaf from "../config/canvig-gene-mtaf.json";

export interface PreComputedCriterion {
  criterion_code: string;
  pre_computed_value: string;
  framework: "acgs_snv" | "svig";
  suggested_strength: string;
}

const LOF_CONSEQUENCES = new Set([
  "frameshift_variant",
  "stop_gained",
  "stop_lost",
  "start_lost",
  "splice_donor_variant",
  "splice_acceptor_variant",
  "transcript_ablation",
]);

const CANONICAL_SPLICE_CONSEQUENCES = new Set([
  "splice_donor_variant",
  "splice_acceptor_variant",
]);

function getGnomadThresholds(gene: string | null): {
  ba1: number;
  bs1: number;
} {
  if (gene) {
    const mtaf = (canvigMtaf.genes as Record<string, { ba1_threshold: number; bs1_threshold: number }>)[gene];
    if (mtaf) return { ba1: mtaf.ba1_threshold, bs1: mtaf.bs1_threshold };
  }
  return { ba1: 0.05, bs1: 0.01 };
}

/** Pre-compute candidate criteria from VCF variant annotations.
 *  Returns suggestions — analyst must confirm each one.
 *  No external API calls; all from VCF INFO fields.
 */
export function preComputeCriteria(
  variant: VcfVariant,
  caseType: "germline" | "somatic"
): PreComputedCriterion[] {
  const results: PreComputedCriterion[] = [];
  const framework: "acgs_snv" | "svig" = caseType === "somatic" ? "svig" : "acgs_snv";
  const { gnomad_af, consequence, revel_score, spliceai_max, clinvar_sig, gene } = variant;

  const { ba1: ba1Thresh, bs1: bs1Thresh } = getGnomadThresholds(gene);

  if (framework === "acgs_snv") {
    // BA1 — standalone benign if AF above threshold
    if (gnomad_af != null && gnomad_af > ba1Thresh) {
      const label = gene && (canvigMtaf.genes as Record<string, unknown>)[gene]
        ? `CanVIG ${gene}`
        : "ACGS standard";
      results.push({
        criterion_code: "BA1",
        pre_computed_value: `gnomAD AF = ${gnomad_af.toExponential(2)} [threshold ${ba1Thresh} — ${label}]`,
        framework,
        suggested_strength: "standalone",
      });
    }

    // BS1 — elevated AF
    if (gnomad_af != null && gnomad_af > bs1Thresh && gnomad_af <= ba1Thresh) {
      results.push({
        criterion_code: "BS1",
        pre_computed_value: `gnomAD AF = ${gnomad_af.toExponential(2)} [BS1 threshold ${bs1Thresh}]`,
        framework,
        suggested_strength: "strong",
      });
    }

    // PM2 — absent or very low AF
    if (gnomad_af == null || gnomad_af < 0.0001) {
      const afLabel = gnomad_af == null ? "absent in gnomAD" : `gnomAD AF = ${gnomad_af.toExponential(2)}`;
      results.push({
        criterion_code: "PM2",
        pre_computed_value: afLabel,
        framework,
        suggested_strength: "supporting",
      });
    }

    // PVS1 — null variant (LOF) suggestion
    if (consequence && LOF_CONSEQUENCES.has(consequence.split("&")[0])) {
      results.push({
        criterion_code: "PVS1",
        pre_computed_value: `Consequence: ${consequence}`,
        framework,
        suggested_strength: "very_strong",
      });
    }

    // PVS1_RNA — high SpliceAI score
    if (spliceai_max != null && spliceai_max >= 0.8) {
      results.push({
        criterion_code: "PVS1_RNA",
        pre_computed_value: `SpliceAI max delta = ${spliceai_max.toFixed(3)}`,
        framework,
        suggested_strength: "very_strong",
      });
    }

    // PP3 — damaging computational (REVEL ≥ 0.7)
    if (revel_score != null && revel_score >= 0.7) {
      results.push({
        criterion_code: "PP3",
        pre_computed_value: `REVEL score = ${revel_score.toFixed(3)}`,
        framework,
        suggested_strength: "supporting",
      });
    }

    // BP4 — benign computational (REVEL ≤ 0.4)
    if (revel_score != null && revel_score <= 0.4) {
      results.push({
        criterion_code: "BP4",
        pre_computed_value: `REVEL score = ${revel_score.toFixed(3)}`,
        framework,
        suggested_strength: "supporting",
      });
    }

    // BP7 — synonymous + low SpliceAI
    if (
      consequence?.includes("synonymous_variant") &&
      (spliceai_max == null || spliceai_max < 0.1)
    ) {
      results.push({
        criterion_code: "BP7",
        pre_computed_value: `Synonymous variant; SpliceAI max delta = ${
          spliceai_max != null ? spliceai_max.toFixed(3) : "N/A"
        }`,
        framework,
        suggested_strength: "supporting",
      });
    }

    // BP7_RNA — near-splice site with low SpliceAI
    if (
      consequence &&
      CANONICAL_SPLICE_CONSEQUENCES.has(consequence.split("&")[0]) &&
      spliceai_max != null &&
      spliceai_max < 0.1
    ) {
      results.push({
        criterion_code: "BP7_RNA",
        pre_computed_value: `SpliceAI max delta = ${spliceai_max.toFixed(3)} (near splice site)`,
        framework,
        suggested_strength: "supporting",
      });
    }

    // PS1 / PM5 — ClinVar same AA
    if (clinvar_sig && /pathogenic/i.test(clinvar_sig) && !/conflict/i.test(clinvar_sig)) {
      results.push({
        criterion_code: "PS1",
        pre_computed_value: `ClinVar: ${clinvar_sig}`,
        framework,
        suggested_strength: "strong",
      });
    }
  } else {
    // SVIG-UK framework

    // B1 — standalone benign (germline polymorphism in somatic context)
    if (gnomad_af != null && gnomad_af > 0.01) {
      results.push({
        criterion_code: "B1",
        pre_computed_value: `gnomAD AF = ${gnomad_af.toExponential(2)} (> 0.01)`,
        framework,
        suggested_strength: "standalone",
      });
    }

    // O3 — absent or very rare in population
    if (gnomad_af == null || gnomad_af < 0.0001) {
      const afLabel = gnomad_af == null ? "absent in gnomAD" : `gnomAD AF = ${gnomad_af.toExponential(2)}`;
      results.push({
        criterion_code: "O3",
        pre_computed_value: afLabel,
        framework,
        suggested_strength: "moderate",
      });
    }

    // O2 — null variant in TSG
    if (consequence && LOF_CONSEQUENCES.has(consequence.split("&")[0])) {
      results.push({
        criterion_code: "O2",
        pre_computed_value: `Consequence: ${consequence}`,
        framework,
        suggested_strength: "very_strong",
      });
    }

    // O6 — computational damaging
    if (revel_score != null && revel_score >= 0.7) {
      results.push({
        criterion_code: "O6",
        pre_computed_value: `REVEL score = ${revel_score.toFixed(3)}`,
        framework,
        suggested_strength: "supporting",
      });
    }

    // B3 — computational benign
    if (revel_score != null && revel_score <= 0.4) {
      results.push({
        criterion_code: "B3",
        pre_computed_value: `REVEL score = ${revel_score.toFixed(3)}`,
        framework,
        suggested_strength: "supporting",
      });
    }
    if (spliceai_max != null && spliceai_max < 0.1) {
      const existing = results.find((r) => r.criterion_code === "B3");
      if (!existing) {
        results.push({
          criterion_code: "B3",
          pre_computed_value: `SpliceAI max delta = ${spliceai_max.toFixed(3)}`,
          framework,
          suggested_strength: "supporting",
        });
      }
    }

    // O1 suggestion — ClinVar somatic pathogenic
    if (clinvar_sig && /oncogenic|pathogenic/i.test(clinvar_sig) && !/conflict/i.test(clinvar_sig)) {
      results.push({
        criterion_code: "O1",
        pre_computed_value: `ClinVar: ${clinvar_sig}`,
        framework,
        suggested_strength: "standalone",
      });
    }
  }

  return results;
}
