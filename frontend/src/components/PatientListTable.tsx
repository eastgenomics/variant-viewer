import { Link } from "react-router-dom";
import { useState } from "react";
import WorkflowBadge from "./WorkflowBadge";
import { deletePatient } from "../lib/api";
import type { PatientSummary } from "../lib/api";

function DeletePatientButton({
  id,
  label,
  onDelete,
}: {
  id: number;
  label: string;
  onDelete: (id: number) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (confirming) {
    return (
      <span className="flex gap-1 items-center">
        <span className="text-xs text-gray-700 mr-1">Delete <strong>{label}</strong>?</span>
        <button
          className="btn btn-danger text-xs py-0.5 px-2"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setDeleteError(null);
            try {
              await deletePatient(id);
              onDelete(id);
              setConfirming(false);
            } catch (e) {
              setDeleteError(e instanceof Error ? e.message : "Delete failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Deleting…" : "Yes, delete"}
        </button>
        <button
          className="btn btn-secondary text-xs py-0.5 px-2"
          onClick={() => { setConfirming(false); setDeleteError(null); }}
        >
          Cancel
        </button>
        {deleteError && (
          <span className="text-xs text-red-600 ml-1">{deleteError}</span>
        )}
      </span>
    );
  }
  return (
    <button
      className="text-red-500 hover:text-red-700 text-xs"
      onClick={() => setConfirming(true)}
    >
      Delete
    </button>
  );
}

export default function PatientListTable({
  patients,
  onDelete,
}: {
  patients: PatientSummary[];
  onDelete: (id: number) => void;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            <th className="px-4 py-3">MRN</th>
            <th className="px-4 py-3">Specimens</th>
            <th className="px-4 py-3">Latest Specimen</th>
            <th className="px-4 py-3">Pipeline</th>
            <th className="px-4 py-3">Workflow</th>
            <th className="px-4 py-3">Ingested</th>
            <th className="px-4 py-3"></th>
            <th className="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {patients.map((p) => (
            <tr key={p.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-mono font-medium text-gray-900">
                {p.lab_number}
              </td>
              <td className="px-4 py-3 text-gray-500">{p.sample_count}</td>
              <td className="px-4 py-3 text-gray-600">
                {p.latest_sample_name ?? "—"}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {p.pipeline_key ? p.pipeline_key.replace(/_/g, " ") : "—"}
              </td>
              <td className="px-4 py-3">
                {p.latest_workflow_status ? (
                  <WorkflowBadge status={p.latest_workflow_status} />
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs">
                {p.latest_ingested_at
                  ? new Date(p.latest_ingested_at).toLocaleDateString("en-GB")
                  : "—"}
              </td>
              <td className="px-4 py-3">
                <Link
                  to={`/patients/${p.id}`}
                  className="text-blue-600 hover:underline text-xs"
                >
                  View →
                </Link>
              </td>
              <td className="px-4 py-3">
                <DeletePatientButton
                  id={p.id}
                  label={p.lab_number}
                  onDelete={onDelete}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
