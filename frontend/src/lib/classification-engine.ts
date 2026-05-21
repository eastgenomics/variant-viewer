/**
 * Classification scoring engine — pure functions, no side effects.
 * Ported from discovery/nextjs:lib/classification-engine.ts
 * Implements Tavtigian point-based scoring for ACGS SNV and SVIG-UK frameworks.
 */

import canvigGeneMtaf from "../config/canvig-gene-mtaf.json";

export const ACGS_VERSION = "ACGS 2024 Best Practice Guidelines";
export const SVIG_VERSION = "SVIG-UK v1.0";

const CANVIG_GENE_SET = new Set(
  Object.keys((canvigGeneMtaf as { genes: Record<string, unknown> }).genes).map(
    (g) => g.toUpperCase()
  )
);

export type Framework = "acgs_snv" | "svig";

export type Strength =
  | "very_strong"
  | "strong"
  | "moderate"
  | "supporting"
  | "standalone";

export interface AppliedCriterion {
  criterion_code: string;
  applied: boolean;
  strength: string;
  direction?: "pathogenic" | "benign" | "oncogenic";
}

export interface CombinationRule {
  rule: string;
  codes: string[];
  message: string;
}

export interface ClassificationResult {
  score: number;
  classification: string;
  warnings: string[];
}

const STRENGTH_POINTS: Record<string, number> = {
  very_strong: 8,
  strong: 4,
  moderate: 2,
  supporting: 1,
  // 'standalone' kept as fallback only — BA1/O1/B1/B2 sentinels are intercepted
  // before this table is reached and will never look up this value in practice.
  standalone: 8,
};

const BENIGN_STRENGTH_POINTS: Record<string, number> = {
  // 'standalone' intentionally absent — BA1 is intercepted by early return
  strong: -4,
  moderate: -2,
  supporting: -1,
};

function classifyAcgs(score: number, hasBA1: boolean): string {
  if (hasBA1) return "Benign";
  if (score >= 10) return "Pathogenic";
  if (score >= 6) return "Likely_Pathogenic";
  if (score >= 0) return "VUS";
  if (score >= -6) return "Likely_Benign";
  return "Benign";
}

function classifySvig(
  score: number,
  hasO1: boolean,
  hasB1: boolean,
  hasB2: boolean
): string {
  // Priority matches Python backend: O1 → B1 → B2 → point thresholds
  if (hasO1) return "Oncogenic";
  if (hasB1) return "Benign";
  if (hasB2) return "VUS";
  if (score >= 10) return "Oncogenic";
  if (score >= 6) return "Likely_Oncogenic";
  if (score >= 0) return "VUS";
  if (score >= -6) return "Likely_Benign";
  return "Benign";
}

function getCriterionDirection(
  code: string,
  framework: Framework
): "pathogenic" | "benign" | "oncogenic" | null {
  if (framework === "acgs_snv") {
    if (/^(PVS|PS|PM|PP)/.test(code)) return "pathogenic";
    if (/^(BA|BS|BP)/.test(code)) return "benign";
  } else {
    if (/^O/.test(code)) return "oncogenic";
    if (/^B/.test(code)) return "benign";
  }
  return null;
}

export function classify(
  criteria: AppliedCriterion[],
  framework: Framework,
  combinationRules: CombinationRule[]
): ClassificationResult {
  const applied = criteria.filter((c) => c.applied);
  const warnings: string[] = [];

  // Build set of applied codes once for combination-rule checks (matches Python logic)
  const appliedCodeSet = new Set(applied.map((c) => c.criterion_code));
  for (const rule of combinationRules) {
    if (rule.codes.length < 2) continue;
    const matchCount = rule.codes.filter((code) => appliedCodeSet.has(code)).length;
    if (matchCount >= 2) warnings.push(rule.message);
  }

  let score = 0;

  if (framework === "acgs_snv") {
    const hasBA1 = applied.some((c) => c.criterion_code === "BA1");

    if (hasBA1) {
      return { score: -999, classification: "Benign", warnings };
    }

    for (const c of applied) {
      const direction = getCriterionDirection(c.criterion_code, framework);
      if (direction === "pathogenic") {
        score += STRENGTH_POINTS[c.strength] ?? 0;
      } else if (direction === "benign") {
        score += BENIGN_STRENGTH_POINTS[c.strength] ?? 0;
      }
    }

    if (applied.length < 2 && score !== 0) {
      warnings.push(
        "ACGS requires a minimum of 2 applied criteria for any non-VUS classification (except BA1)."
      );
    }

    return { score, classification: classifyAcgs(score, false), warnings };
  } else {
    const hasO1 = applied.some((c) => c.criterion_code === "O1");
    const hasB1 = applied.some((c) => c.criterion_code === "B1");
    const hasB2 = applied.some((c) => c.criterion_code === "B2");

    if (hasO1 || hasB1 || hasB2) {
      const classification = classifySvig(0, hasO1, hasB1, hasB2);
      const sentinelScore =
        classification === "Oncogenic"
          ? 999
          : classification === "Benign"
            ? -999
            : 0;
      return { score: sentinelScore, classification, warnings };
    }

    for (const c of applied) {
      const direction = getCriterionDirection(c.criterion_code, framework);
      if (direction === "oncogenic") {
        score += STRENGTH_POINTS[c.strength] ?? 0;
      } else if (direction === "benign") {
        score += BENIGN_STRENGTH_POINTS[c.strength] ?? 0;
      }
    }

    return { score, classification: classifySvig(score, false, false, false), warnings };
  }
}

export function selectFramework(
  caseType: "germline" | "somatic",
  gene: string | null
): { framework: Framework; isCanvig: boolean } {
  if (caseType === "somatic") {
    return { framework: "svig", isCanvig: false };
  }
  const normalisedGene = gene?.trim().toUpperCase();
  if (normalisedGene && CANVIG_GENE_SET.has(normalisedGene)) {
    return { framework: "acgs_snv", isCanvig: true };
  }
  return { framework: "acgs_snv", isCanvig: false };
}

export function getFrameworkVersion(framework: Framework): string {
  return framework === "acgs_snv" ? ACGS_VERSION : SVIG_VERSION;
}

export function classificationLabel(classification: string | null): string {
  if (!classification) return "—";
  const labels: Record<string, string> = {
    Pathogenic: "Pathogenic",
    Likely_Pathogenic: "Likely Pathogenic",
    VUS: "Variant of Uncertain Significance",
    Likely_Benign: "Likely Benign",
    Benign: "Benign",
    Oncogenic: "Oncogenic",
    Likely_Oncogenic: "Likely Oncogenic",
  };
  return labels[classification] ?? classification;
}

export function classificationBadgeClass(classification: string | null): string {
  if (!classification) return "vus";
  const map: Record<string, string> = {
    Pathogenic: "pathogenic",
    Likely_Pathogenic: "likely-pathogenic",
    VUS: "vus",
    Likely_Benign: "likely-benign",
    Benign: "benign",
    Oncogenic: "oncogenic",
    Likely_Oncogenic: "likely-oncogenic",
  };
  return map[classification] ?? "vus";
}
