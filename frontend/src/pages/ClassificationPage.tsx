import { useState, useEffect } from "react";
import { useParams, Navigate, Link } from "react-router-dom";
import { getVariant, ApiError } from "../lib/api";
import type { VariantDetailResponse } from "../lib/api";
import ClassificationPanel from "../components/ClassificationPanel";

export default function ClassificationPage() {
  const { patientId, variantId } = useParams<{
    patientId: string;
    variantId: string;
  }>();

  const [variant, setVariant] = useState<VariantDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!variantId || isNaN(Number(variantId))) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    getVariant(Number(variantId))
      .then(setVariant)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setNotFound(true);
        else setError(e instanceof ApiError ? e.detail : "Failed to load");
      })
      .finally(() => setLoading(false));
  }, [variantId]);

  if (notFound) return <Navigate to={`/patients/${patientId}`} replace />;

  return (
    <div>
      <div className="mb-4">
        <Link
          to={`/patients/${patientId}`}
          className="text-sm text-blue-600 hover:underline"
        >
          ← Back to patient
        </Link>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-16 text-gray-400">Loading…</div>
      )}

      {!loading && variant && (
        <>
          {/* Variant detail card */}
          <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
            <div className="font-mono font-medium text-gray-900">
              {variant.gene ?? "—"} · {variant.chrom}:{variant.pos}{" "}
              {variant.ref}&gt;{variant.alt}
            </div>
            <div className="flex gap-4 mt-2 text-xs text-gray-500">
              {variant.hgvs_c && <span>{variant.hgvs_c}</span>}
              {variant.hgvs_p && <span>{variant.hgvs_p}</span>}
              {variant.consequence && (
                <span>{variant.consequence.replace(/_/g, " ")}</span>
              )}
            </div>
          </div>

          <ClassificationPanel
            variantId={variant.id}
            caseType={
              // Runtime validation: DB stores only germline/somatic, but guard against future values
              variant.case_type === "somatic" ? "somatic" : "germline"
            }
            gene={variant.gene}
            initialClassification={
              variant.active_classification
                ? {
                    id: variant.active_classification.id,
                    framework: variant.active_classification.framework,
                    framework_version:
                      variant.active_classification.framework_version,
                    score: variant.active_classification.score,
                    classification: variant.active_classification.classification,
                    locked_at: variant.active_classification.locked_at,
                    locked_by: variant.active_classification.locked_by,
                  }
                : null
            }
            initialCriteria={variant.active_classification?.criteria ?? []}
          />
        </>
      )}
    </div>
  );
}
