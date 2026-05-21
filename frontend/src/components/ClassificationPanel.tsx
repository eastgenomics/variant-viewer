import { useState, useCallback, useMemo } from "react";
import {
  classify,
  selectFramework,
  classificationLabel,
  classificationBadgeClass,
  type Framework,
} from "../lib/classification-engine";
import { putClassification, resetClassification as apiReset } from "../lib/api";
import type { ClassificationDetail, CriterionDetail } from "../lib/api";
import acgsCriteria from "../config/acgs-snv-criteria.json";
import svigCriteria from "../config/svig-criteria.json";
import CriterionRow, { isValidEvidenceLink } from "./CriterionRow";
import type { CriterionDef, CriterionState } from "./CriterionRow";

const EVIDENCE_CATEGORIES = [
  "population",
  "computational",
  "functional",
  "segregation",
  "case_evidence",
  "other_databases",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  population: "Population",
  computational: "Computational",
  functional: "Functional / Null Variant",
  segregation: "Segregation",
  case_evidence: "Case Evidence",
  other_databases: "Other Databases",
};

function getCriteriaDefs(framework: Framework): CriterionDef[] {
  return (framework === "acgs_snv"
    ? acgsCriteria.criteria
    : svigCriteria.criteria) as unknown as CriterionDef[];
}

function initCriteriaState(
  defs: CriterionDef[],
  existing: Partial<CriterionDetail>[]
): CriterionState[] {
  return defs.map((def) => {
    const e = existing.find((c) => c.criterion_code === def.code);
    const rawLinks = e?.evidence_links ?? [];
    // Re-validate server-loaded links before storing in state (defence against
    // insider threat: a valid API key holder could inject javascript: URLs via API)
    const safeLinks = rawLinks.filter(isValidEvidenceLink);
    return {
      criterion_code: def.code,
      applied: e?.applied ?? false,
      strength: e?.strength ?? def.default_strength,
      notes: e?.notes ?? "",
      evidence_links: safeLinks,
      pre_computed: e?.pre_computed ?? false,
      pre_computed_value: e?.pre_computed_value ?? null,
    };
  });
}

export default function ClassificationPanel({
  variantId,
  caseType,
  gene,
  initialClassification,
  initialCriteria,
}: {
  variantId: number;
  caseType: "germline" | "somatic";
  gene: string | null;
  initialClassification: Omit<ClassificationDetail, "criteria"> | null;
  initialCriteria: Partial<CriterionDetail>[];
}) {
  const { framework: defaultFramework } = selectFramework(caseType, gene);

  const [framework, setFramework] = useState<Framework>(
    (initialClassification?.framework as Framework) ?? defaultFramework
  );
  const [frameworkLocked, setFrameworkLocked] = useState(
    initialCriteria.some((c) => c.applied) || !!initialClassification?.locked_at
  );

  const defs = useMemo(() => getCriteriaDefs(framework), [framework]);
  const [criteria, setCriteria] = useState<CriterionState[]>(() =>
    initCriteriaState(defs, initialCriteria)
  );

  const [classId, setClassId] = useState<number | null>(
    initialClassification?.id ?? null
  );
  const [lockedAt, setLockedAt] = useState<string | null>(
    initialClassification?.locked_at ?? null
  );

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const appliedCriteria = useMemo(
    () =>
      criteria
        .filter((c) => c.applied)
        .map((c) => ({ criterion_code: c.criterion_code, applied: true, strength: c.strength })),
    [criteria]
  );

  const combinationRules = useMemo(
    () =>
      (framework === "acgs_snv"
        ? acgsCriteria.combination_rules
        : svigCriteria.combination_rules) as { rule: string; codes: string[]; message: string }[],
    [framework]
  );

  const { score, classification, warnings } = useMemo(
    () => classify(appliedCriteria, framework, combinationRules),
    [appliedCriteria, framework, combinationRules]
  );

  const updateCriterion = useCallback(
    (code: string, updates: Partial<CriterionState>) => {
      setCriteria((prev) =>
        prev.map((c) => (c.criterion_code === code ? { ...c, ...updates } : c))
      );
      if ("applied" in updates) setFrameworkLocked(true);
    },
    []
  );

  const userId = import.meta.env.VITE_USER_ID ?? "analyst";

  async function save(lock: boolean) {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await putClassification(variantId, {
        framework,
        user_id: userId,
        locked_by: lock ? userId : null,
        criteria: criteria.map((c) => ({
          criterion_code: c.criterion_code,
          applied: c.applied,
          strength: c.strength,
          notes: c.notes || undefined,
          evidence_links: c.evidence_links.length > 0 ? c.evidence_links : undefined,
        })),
      });
      setClassId(result.classification_id);
      if (lock) setLockedAt(new Date().toISOString());
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!classId) return;
    setSaving(true);
    setSaveError(null);
    try {
      await apiReset(variantId, classId, userId);
      setClassId(null);
      setLockedAt(null);
      setFrameworkLocked(false);
      setCriteria(initCriteriaState(defs, []));
      setShowResetConfirm(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Reset failed");
      setShowResetConfirm(false); // close confirm on failure so user can retry cleanly
    } finally {
      setSaving(false);
    }
  }

  const badgeClass = `badge badge-${classificationBadgeClass(classification)}`;
  const scoreDisplay = score === 999 ? "★" : score === -999 ? "✗" : score;

  return (
    <div className="bg-white border border-gray-200 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div className="flex items-center gap-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Framework</label>
            <select
              value={framework}
              disabled={frameworkLocked || !!lockedAt}
              onChange={(e) => {
                const next = e.target.value as Framework;
                setFramework(next);
                setClassId(null);
                setLockedAt(null);
                setFrameworkLocked(false);
                setCriteria(initCriteriaState(getCriteriaDefs(next), []));
              }}
              className="border border-gray-300 rounded px-2 py-1 text-sm"
            >
              <option value="acgs_snv">ACGS SNV / CanVIG</option>
              <option value="svig">SVIG-UK</option>
            </select>
          </div>

          <div className="text-center">
            <div className="text-xs text-gray-400 mb-1">Score</div>
            <div className="font-mono text-2xl font-bold text-gray-900">
              {scoreDisplay}
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-400 mb-1">Classification</div>
            <span className={badgeClass}>
              {classificationLabel(classification)}
            </span>
          </div>

          {lockedAt && (
            <span className="badge bg-gray-100 text-gray-500">
              Confirmed {new Date(lockedAt).toLocaleDateString("en-GB")}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {!lockedAt && (
            <>
              <button
                className="btn btn-secondary"
                disabled={saving}
                onClick={() => save(false)}
              >
                Save draft
              </button>
              <button
                className="btn btn-primary"
                disabled={saving}
                onClick={() => save(true)}
              >
                Confirm classification
              </button>
            </>
          )}
          {lockedAt && (
            <button
              className="btn btn-danger text-sm"
              onClick={() => setShowResetConfirm(true)}
            >
              Reset classification
            </button>
          )}
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="px-5 py-2 bg-amber-50 border-b border-amber-100">
          {warnings.map((w, i) => (
            <div key={i} className="text-xs text-amber-700">⚠ {w}</div>
          ))}
        </div>
      )}

      {saveError && (
        <div className="px-5 py-2 bg-red-50 border-b border-red-100 text-xs text-red-600">
          {saveError}
        </div>
      )}

      {showResetConfirm && (
        <div className="px-5 py-3 bg-red-50 border-b border-red-200 flex items-center gap-3">
          <span className="text-sm text-red-700">
            This will delete all criteria and unlock the framework. Continue?
          </span>
          <button className="btn btn-danger text-xs" onClick={handleReset}>
            Yes, reset
          </button>
          <button
            className="btn btn-secondary text-xs"
            onClick={() => setShowResetConfirm(false)}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Criteria by category */}
      <div className="p-5 space-y-6">
        {EVIDENCE_CATEGORIES.map((cat) => {
          const catDefs = defs.filter((d) => d.category === cat);
          if (catDefs.length === 0) return null;
          return (
            <div key={cat}>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                {CATEGORY_LABELS[cat]}
              </h3>
              <div className="space-y-2">
                {catDefs.map((def) => {
                  const crit = criteria.find((c) => c.criterion_code === def.code);
                  if (!crit) return null;
                  return (
                    <CriterionRow
                      key={def.code}
                      def={def}
                      crit={crit}
                      locked={!!lockedAt}
                      onChange={(updates) => updateCriterion(def.code, updates)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
