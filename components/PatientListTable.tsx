import Link from "next/link";
import WorkflowBadge from "@/components/WorkflowBadge";
import DeletePatientButton from "@/app/DeletePatientButton";
import { formatYearOfBirth } from "@/lib/display-utils";

export interface PatientRow {
  id: number;
  name: string;
  lab_number: string;
  nhs_number: string | null;
  dob: string | null;
  sample_count: number;
  latest_sample_id: number | null;
  latest_sample_name: string | null;
  latest_workflow_status: string | null;
  latest_ingested_at: string | null;
  pipeline_key: string | null;
}

export default function PatientListTable({
  patients,
}: {
  patients: PatientRow[];
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            <th className="px-4 py-3">MRN</th>
            <th className="px-4 py-3">YOB</th>
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
              <td className="px-4 py-3 text-gray-500">
                {formatYearOfBirth(p.dob)}
              </td>
              <td className="px-4 py-3 text-gray-500">{p.sample_count}</td>
              <td className="px-4 py-3 text-gray-600">
                {p.latest_sample_name ?? "—"}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {p.pipeline_key
                  ? p.pipeline_key.replace(/_/g, " ")
                  : "—"}
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
                  href={`/patients/${p.id}`}
                  className="text-blue-600 hover:underline text-xs"
                >
                  View →
                </Link>
              </td>
              <td className="px-4 py-3">
                <DeletePatientButton id={p.id} name={p.lab_number} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
