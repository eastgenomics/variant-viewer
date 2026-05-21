import { useState, useEffect, useCallback } from "react";
import { useParams, Navigate } from "react-router-dom";
import { getPatient, getSample, ApiError } from "../lib/api";
import type { PatientDetailResponse, SampleDetail } from "../lib/api";
import PatientHeader from "../components/PatientHeader";
import SpecimenCard from "../components/SpecimenCard";

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  // patientId is only used in JSX after the patient loads (guarded by loading/notFound states)
  const patientId = Number(id);

  const [patient, setPatient] = useState<PatientDetailResponse | null>(null);
  const [samples, setSamples] = useState<SampleDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || isNaN(Number(id))) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    const numericId = Number(id);
    getPatient(numericId)
      .then(async (p) => {
        setPatient(p);
        // Fetch full sample details for each nested sample summary
        const details = await Promise.all(
          p.samples.map((s) => getSample(s.id))
        );
        setSamples(details);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setNotFound(true);
        else setError(e instanceof ApiError ? e.detail : "Failed to load");
      })
      .finally(() => setLoading(false));
  }, [id]); // use raw string id as dep (not derived Number) — avoids NaN===NaN ambiguity

  const handleDeleteSample = useCallback(
    (sampleId: number) => setSamples((prev) => prev.filter((x) => x.id !== sampleId)),
    []
  );

  if (notFound) return <Navigate to="/" replace />;

  return (
    <div>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6 text-sm text-red-700">
          {error}
        </div>
      )}
      {loading && (
        <div className="text-center py-16 text-gray-400">Loading…</div>
      )}
      {!loading && patient && (
        <>
          <PatientHeader patient={patient} />
          {samples.length === 0 && (
            <div className="text-gray-400 text-sm">No specimens found.</div>
          )}
          {samples.map((s) => (
            <SpecimenCard
              key={s.id}
              specimen={s}
              patientId={patientId}
            onDeleteSample={handleDeleteSample}
            />
          ))}
        </>
      )}
    </div>
  );
}
