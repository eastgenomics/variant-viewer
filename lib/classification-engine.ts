/**
 * Classification scoring engine — pure functions, no side effects.
 * Implements Tavtigian point-based scoring for ACGS SNV and SVIG-UK frameworks.
 */

import canvigGeneMtaf from "../config/canvig-gene-mtaf.json";

export const ACGS_VERSION = "ACGS 2024 Best Practice Guidelines";
export const SVIG_VERSION = "SVIG-UK v1.0";

// CanVIG gene set for efficient case-insensitive lookup
const CANVIG_GENE_SET = new Set(
  Object.keys(canvigGeneMtaf.genes).map((g) => g.toUpperCase())
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
  strength: Strength;
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
};

const BENIGN_STRENGTH_POINTS: Record<string, number> = {
  standalone: -Infinity, // handled separately
  strong: -4,
  moderate: -2,
  supporting: -1,
};

/** Classify under ACGS SNV / CanVIG thresholds */
function classifyAcgs(score: number, hasBA1: boolean): string {
  if (hasBA1) return "Benign";
  if (score >= 10) return "Pathogenic";
  if (score >= 6) return "Likely_Pathogenic";
  if (score >= 0) return "VUS";
  if (score >= -6) return "Likely_Benign";
  return "Benign";
}

/** Classify under SVIG-UK thresholds */
function classifySvig(
  score: number,
  hasO1: boolean,
  hasB1: boolean,
  hasB2: boolean
): string {
  if (hasB2) return "VUS"; // B2 forces VUS regardless
  if (hasB1) return "Benign";
  if (hasO1) return "Oncogenic";
  if (score >= 10) return "Oncogenic";
  if (score >= 6) return "Likely_Oncogenic";
  if (score >= 0) return "VUS";
  if (score >= -6) return "Likely_Benign";
  return "Benign";
}

function countApplied(criteria: AppliedCriterion[]): number {
  return criteria.filter((c) => c.applied).length;
}

export function classify(
  criteria: AppliedCriterion[],
  framework: Framework,
  combinationRules: CombinationRule[]
): ClassificationResult {
  const applied = criteria.filter((c) => c.applied);
  const warnings: string[] = [];

  // Check combination rules
  for (const rule of combinationRules) {
    const matchingApplied = applied.filter((c) =>
      rule.codes.includes(c.criterion_code)
    );
    if (matchingApplied.length >= 2 || (rule.codes.length === 1 && matchingApplied.length === 1)) {
      // Only warn if this is a conflict rule (2+ codes), not standalone info rules
      if (rule.codes.length >= 2 && matchingApplied.length >= 2) {
        warnings.push(rule.message);
      }
    }
  }

  let score = 0;

  if (framework === "acgs_snv") {
    const hasBA1 = applied.some((c) => c.criterion_code === "BA1");

    if (hasBA1) {
      // BA1 standalone benign — score not meaningful but return -Infinity representative
      const classification = classifyAcgs(score, true);
      return { score: -999, classification, warnings };
    }

    for (const c of applied) {
      const direction = getCriterionDirection(c.criterion_code, framework);
      if (direction === "pathogenic") {
        if (c.strength === "standalone") {
          // treat standalone pathogenic as very_strong (PVS1 equivalent)
          score += 8;
        } else {
          score += STRENGTH_POINTS[c.strength] ?? 0;
        }
      } else if (direction === "benign") {
        score += BENIGN_STRENGTH_POINTS[c.strength] ?? 0;
      }
    }

    // ACGS: minimum 2 criteria required for non-VUS (except BA1)
    if (countApplied(applied) < 2 && score !== 0) {
      warnings.push(
        "ACGS requires a minimum of 2 applied criteria for any non-VUS classification (except BA1)."
      );
    }

    const classification = classifyAcgs(score, false);
    return { score, classification, warnings };
  } else {
    // SVIG
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

    const classification = classifySvig(score, false, false, false);
    return { score, classification, warnings };
  }
}

/** Determine criterion direction from code prefix */
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

/** Determine which framework to use for a variant */
export function selectFramework(
  caseType: "germline" | "somatic",
  gene: string | null
): { framework: Framework; isCanvig: boolean } {
  if (caseType === "somatic") {
    return { framework: "svig", isCanvig: false };
  }
  // germline — check if gene is in CanVIG gene list (case-insensitive)
  const normalisedGene = gene?.trim().toUpperCase();
  if (normalisedGene && CANVIG_GENE_SET.has(normalisedGene)) {
    return { framework: "acgs_snv", isCanvig: true };
  }
  return { framework: "acgs_snv", isCanvig: false };
}

export function getFrameworkVersion(framework: Framework): string {
  return framework === "acgs_snv" ? ACGS_VERSION : SVIG_VERSION;
}

/** Human-readable label for a classification */
export function classificationLabel(classification: string): string {
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

/** CSS class suffix for classification badge */
export function classificationBadgeClass(classification: string): string {
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
