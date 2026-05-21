import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { listPatients, ApiError, type PatientSummary } from "../lib/api";
import PatientListTable from "../components/PatientListTable";

export default function PatientsPage() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPatients()
      .then((r) => { setPatients(r.items); setTotal(r.total); })
      .catch((e) => setError(e instanceof ApiError ? e.detail : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Cases</h1>
          {!loading && !error && (
            <p className="text-sm text-gray-500 mt-0.5">
              {total} case{total !== 1 ? "s" : ""} in system
            </p>
          )}
        </div>
        <Link to="/upload" className="btn btn-primary">Upload VCF</Link>
      </div>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6 text-sm text-red-700">
          {error}
        </div>
      )}
      {loading && (
        <div className="text-center py-16 text-gray-400">Loading…</div>
      )}
      {!loading && patients.length === 0 && !error && (
        <div className="text-center py-16 text-gray-400">
          <p>No cases yet.</p>
        </div>
      )}
      {patients.length > 0 && (
        <PatientListTable
          patients={patients}
          onDelete={(id) => {
            setPatients((p) => p.filter((x) => x.id !== id));
            setTotal((t) => Math.max(0, t - 1));
          }}
        />
      )}
    </div>
  );
}
