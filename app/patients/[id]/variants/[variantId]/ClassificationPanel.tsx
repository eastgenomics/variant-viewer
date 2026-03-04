"use client";

import { useState, useCallback, useMemo } from "react";
import {
  classify,
  Framework,
  Strength,
  classificationLabel,
  classificationBadgeClass,
  selectFramework,
} from "@/lib/classification-engine";
import acgsCriteria from "@/config/acgs-snv-criteria.json";
import svigCriteria from "@/config/svig-criteria.json";

/** Validate evidence link URLs - only allow http/https protocols */
function isValidEvidenceLink(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

type CriterionDef = (typeof acgsCriteria.criteria)[number];

interface ClassificationState {
  id: number;
  framework: string;
  framework_version: string;
  score: number | null;
  classification: string | null;
  locked_at: string | null;
  locked_by: string | null;
}

interface CriterionState {
  id?: number;
  criterion_code: string;
  applied: boolean;
  strength: Strength;
  notes: string;
  evidence_links: string[];
  pre_computed: boolean;
  pre_computed_value: string | null;
  // editing state
  _pendingLink?: string;
}

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
    : svigCriteria.criteria) as CriterionDef[];
}

function initCriteriaState(
  defs: CriterionDef[],
  existingCriteria: {
    criterion_code: string;
    applied: boolean;
    strength: string;
    notes: string | null;
    evidence_links: string[] | null;
    pre_computed: boolean;
    pre_computed_value: string | null;
  }[]
): CriterionState[] {
  return defs.map((def) => {
    const existing = existingCriteria.find(
      (c) => c.criterion_code === def.code
    );
    return {
      criterion_code: def.code,
      applied: existing?.applied ?? false,
      strength: (existing?.strength ?? def.default_strength) as Strength,
      notes: existing?.notes ?? "",
      evidence_links: existing?.evidence_links ?? [],
      pre_computed: existing?.pre_computed ?? false,
      pre_computed_value: existing?.pre_computed_value ?? null,
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
  initialClassification: ClassificationState | null;
  initialCriteria: {
    id?: number;
    criterion_code: string;
    applied: boolean;
    strength: string;
    notes: string | null;
    evidence_links: string[] | null;
    pre_computed: boolean;
    pre_computed_value: string | null;
  }[];
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
        .map((c) => ({
          criterion_code: c.criterion_code,
          applied: true,
          strength: c.strength,
        })),
    [criteria]
  );

  const combinationRules = useMemo(
    () =>
      (
        framework === "acgs_snv"
          ? acgsCriteria.combination_rules
          : svigCriteria.combination_rules
      ) as { rule: string; codes: string[]; message: string }[],
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
      // Lock framework on first criterion change
      if ("applied" in updates) {
        setFrameworkLocked(true);
      }
    },
    []
  );

  async function save(lock: boolean) {
    setSaving(true);
    setSaveError(null);
    try {
      const body = {
        variant_id: variantId,
        framework,
        criteria: criteria.map((c) => ({
          criterion_code: c.criterion_code,
          applied: c.applied,
          strength: c.strength,
          notes: c.notes || null,
          evidence_links: c.evidence_links.length > 0 ? c.evidence_links : null,
          pre_computed: c.pre_computed,
          pre_computed_value: c.pre_computed_value,
        })),
        locked: lock,
      };

      const resp = classId
        ? await fetch("/api/classification", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, classification_id: classId }),
          })
        : await fetch("/api/classification", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error ?? "Save failed");
      }
      const result = await resp.json();
      if (result.classId) setClassId(result.classId);
      if (lock) setLockedAt(new Date().toISOString());
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function resetClassification() {
    if (!classId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const resp = await fetch(`/api/classification?id=${classId}`, {
        method: "DELETE",
      });
      if (!resp.ok) throw new Error("Reset failed");
      setClassId(null);
      setLockedAt(null);
      setFrameworkLocked(false);
      setCriteria(initCriteriaState(defs, []));
      setShowResetConfirm(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setSaving(false);
    }
  }

  const badgeClass = `badge badge-${classificationBadgeClass(classification)}`;

  return (
    <div className="bg-white border border-gray-200 rounded-lg">
      {/* Header bar */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div className="flex items-center gap-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Framework</label>
            <select
              value={framework}
              disabled={frameworkLocked || !!lockedAt}
              onChange={(e) => {
                const nextFramework = e.target.value as Framework;
                setFramework(nextFramework);
                setClassId(null);  // force POST on next save
                setLockedAt(null);
                setFrameworkLocked(false);
                setCriteria(initCriteriaState(getCriteriaDefs(nextFramework), []));
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
              {score === 999 ? "★" : score === -999 ? "✗" : score}
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

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="px-5 py-2 bg-amber-50 border-b border-amber-100">
          {warnings.map((w, i) => (
            <div key={i} className="text-xs text-amber-700">
              ⚠ {w}
            </div>
          ))}
        </div>
      )}

      {saveError && (
        <div className="px-5 py-2 bg-red-50 border-b border-red-100 text-xs text-red-600">
          {saveError}
        </div>
      )}

      {/* Reset confirm */}
      {showResetConfirm && (
        <div className="px-5 py-3 bg-red-50 border-b border-red-200 flex items-center gap-3">
          <span className="text-sm text-red-700">
            This will delete all criteria and unlock the framework. Continue?
          </span>
          <button
            className="btn btn-danger text-xs"
            onClick={resetClassification}
          >
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
          const catDefs = defs.filter(
            (d) =>
              (d as { category: string }).category === cat
          );
          if (catDefs.length === 0) return null;
          return (
            <div key={cat}>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                {CATEGORY_LABELS[cat]}
              </h3>
              <div className="space-y-2">
                {catDefs.map((def) => {
                  const crit = criteria.find(
                    (c) => c.criterion_code === def.code
                  );
                  if (!crit) return null;
                  return (
                    <CriterionRow
                      key={def.code}
                      def={def as CriterionDef}
                      crit={crit}
                      locked={!!lockedAt}
                      onChange={(updates) =>
                        updateCriterion(def.code, updates)
                      }
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

function CriterionRow({
  def,
  crit,
  locked,
  onChange,
}: {
  def: CriterionDef;
  crit: CriterionState;
  locked: boolean;
  onChange: (updates: Partial<CriterionState>) => void;
}) {
  const [showNotes, setShowNotes] = useState(
    !!(crit.notes || crit.evidence_links.length > 0)
  );
  const [pendingLink, setPendingLink] = useState("");

  const directionColor =
    (def as { direction: string }).direction === "pathogenic" ||
    (def as { direction: string }).direction === "oncogenic"
      ? "text-red-600"
      : "text-green-700";

  return (
    <div
      className={`rounded border p-3 transition-colors ${
        crit.applied
          ? "border-blue-200 bg-blue-50"
          : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={crit.applied}
          disabled={locked}
          onChange={(e) => onChange({ applied: e.target.checked })}
          className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 cursor-pointer"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-mono font-semibold text-sm ${directionColor}`}>
              {def.code}
            </span>
            <span className="text-xs text-gray-500 truncate">
              {def.description}
            </span>
            {crit.pre_computed && crit.pre_computed_value && (
              <span className="badge bg-purple-100 text-purple-700 text-xs">
                {crit.pre_computed_value}
              </span>
            )}
          </div>

          {crit.applied && (
            <div className="mt-2 flex items-center gap-3 flex-wrap">
              {/* Strength selector */}
              {(def as { adjustable: boolean }).adjustable && (
                <select
                  value={crit.strength}
                  disabled={locked}
                  onChange={(e) =>
                    onChange({ strength: e.target.value as Strength })
                  }
                  className="border border-gray-300 rounded px-2 py-0.5 text-xs"
                >
                  {(def as { permitted_strengths: string[] }).permitted_strengths.map(
                    (s) => (
                      <option key={s} value={s}>
                        {s.replace(/_/g, " ")}
                      </option>
                    )
                  )}
                </select>
              )}
              {!(def as { adjustable: boolean }).adjustable && (
                <span className="text-xs text-gray-500 italic">
                  {crit.strength.replace(/_/g, " ")} (fixed)
                </span>
              )}

              <button
                type="button"
                onClick={() => setShowNotes((v) => !v)}
                className="text-xs text-blue-500 hover:underline"
              >
                {showNotes ? "Hide notes" : "Add notes / links"}
              </button>
            </div>
          )}

          {showNotes && crit.applied && (
            <div className="mt-2 space-y-2">
              <textarea
                value={crit.notes}
                disabled={locked}
                onChange={(e) => onChange({ notes: e.target.value })}
                placeholder="Notes…"
                rows={2}
                className="w-full border border-gray-300 rounded px-2 py-1 text-xs resize-none"
              />

              {/* Evidence links */}
              <div className="space-y-1">
                {crit.evidence_links.map((link, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <a
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline truncate max-w-xs"
                    >
                      {link}
                    </a>
                    {!locked && (
                      <button
                        type="button"
                        onClick={() =>
                          onChange({
                            evidence_links: crit.evidence_links.filter(
                              (_, j) => j !== i
                            ),
                          })
                        }
                        className="text-xs text-red-400 hover:text-red-600"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
                {!locked && (
                  <div className="flex items-center gap-1">
                    <input
                      type="url"
                      value={pendingLink}
                      onChange={(e) => setPendingLink(e.target.value)}
                      placeholder="https://…"
                      className="border border-gray-300 rounded px-2 py-0.5 text-xs flex-1"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && pendingLink) {
                          if (!isValidEvidenceLink(pendingLink)) {
                            alert("Invalid URL. Only http:// and https:// links are allowed.");
                            return;
                          }
                          onChange({
                            evidence_links: [...crit.evidence_links, pendingLink],
                          });
                          setPendingLink("");
                        }
                      }}
                    />
                    <button
                      type="button"
                      disabled={!pendingLink}
                      onClick={() => {
                        if (!pendingLink) return;
                        if (!isValidEvidenceLink(pendingLink)) {
                          alert("Invalid URL. Only http:// and https:// links are allowed.");
                          return;
                        }
                        onChange({
                          evidence_links: [...crit.evidence_links, pendingLink],
                        });
                        setPendingLink("");
                      }}
                      className="btn btn-secondary text-xs py-0.5"
                    >
                      Add
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
