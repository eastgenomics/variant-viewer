import { useState, useEffect } from "react";

/** Validate evidence link URLs — only http/https protocols accepted (Invariant 3). */
export function isValidEvidenceLink(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export interface CriterionDef {
  code: string;
  description: string;
  category: string;
  direction: string;
  default_strength: string;
  adjustable: boolean;
  permitted_strengths: string[];
}

export interface CriterionState {
  criterion_code: string;
  applied: boolean;
  strength: string;
  notes: string;
  evidence_links: string[];
  pre_computed: boolean;
  pre_computed_value: string | null;
}

const DIRECTION_COLORS: Record<string, string> = {
  pathogenic: "text-red-700",
  benign: "text-green-700",
  oncogenic: "text-orange-700",
};

export default function CriterionRow({
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
  const [showNotes, setShowNotes] = useState(false);
  const [pendingLink, setPendingLink] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);

  // Clear notes panel state whenever the criterion is unchecked
  useEffect(() => {
    if (!crit.applied) {
      setShowNotes(false);
      setPendingLink("");
      setLinkError(null);
    }
  }, [crit.applied]);

  const directionColor = DIRECTION_COLORS[def.direction] ?? "text-gray-700";

  function addLink() {
    if (!pendingLink) return;
    if (!isValidEvidenceLink(pendingLink)) {
      setLinkError("Only http:// and https:// links are accepted.");
      return;
    }
    setLinkError(null);
    onChange({ evidence_links: [...crit.evidence_links, pendingLink] });
    setPendingLink("");
  }

  return (
    <div className={`rounded border px-3 py-2 ${crit.applied ? "border-blue-200 bg-blue-50/40" : "border-gray-200 bg-white"}`}>
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
            <span className="text-xs text-gray-500 truncate">{def.description}</span>
            {crit.pre_computed && crit.pre_computed_value && (
              <span className="badge bg-purple-100 text-purple-700 text-xs">
                {crit.pre_computed_value}
              </span>
            )}
          </div>

          {crit.applied && (
            <div className="mt-2 flex items-center gap-3 flex-wrap">
              {def.adjustable ? (
                <select
                  value={crit.strength}
                  disabled={locked}
                  onChange={(e) => onChange({ strength: e.target.value })}
                  className="border border-gray-300 rounded px-2 py-0.5 text-xs"
                >
                  {def.permitted_strengths.map((s) => (
                    <option key={s} value={s}>
                      {s.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="text-xs text-gray-500 italic">
                  {crit.strength.replace(/_/g, " ")} (fixed)
                </span>
              )}

              <button
                type="button"
                onClick={() => {
                  if (showNotes) {
                    setPendingLink("");
                    setLinkError(null);
                  }
                  setShowNotes((v) => !v);
                }}
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
                            evidence_links: crit.evidence_links.filter((_, j) => j !== i),
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
                  <>
                    <div className="flex items-center gap-1">
                      <input
                        type="url"
                        value={pendingLink}
                        onChange={(e) => setPendingLink(e.target.value)}
                        placeholder="https://…"
                        className="border border-gray-300 rounded px-2 py-0.5 text-xs flex-1"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") addLink();
                        }}
                      />
                      <button
                        type="button"
                        disabled={!pendingLink}
                        onClick={addLink}
                        className="btn btn-secondary text-xs py-0.5"
                      >
                        Add
                      </button>
                    </div>
                    {linkError && (
                      <p className="text-xs text-red-600 mt-1">{linkError}</p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
