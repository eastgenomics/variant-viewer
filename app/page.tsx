export const dynamic = "force-dynamic";

import Link from "next/link";
import { query } from "@/lib/db";
import WorkflowBadge from "@/components/WorkflowBadge";

interface PatientRow {
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

async function getPatients(): Promise<PatientRow[]> {
  const result = await query<PatientRow>(`
    SELECT
      p.id,
      p.name,
      p.lab_number,
      p.nhs_number,
      p.dob::text,
      COUNT(s.id)::int AS sample_count,
      (SELECT s2.id FROM samples s2 WHERE s2.patient_id = p.id ORDER BY s2.ingested_at DESC LIMIT 1) AS latest_sample_id,
      (SELECT s2.name FROM samples s2 WHERE s2.patient_id = p.id ORDER BY s2.ingested_at DESC LIMIT 1) AS latest_sample_name,
      (SELECT w.status FROM workflow w
       JOIN samples s3 ON w.sample_id = s3.id
       WHERE s3.patient_id = p.id ORDER BY w.updated_at DESC LIMIT 1) AS latest_workflow_status,
      (SELECT s2.ingested_at::text FROM samples s2 WHERE s2.patient_id = p.id ORDER BY s2.ingested_at DESC LIMIT 1) AS latest_ingested_at,
      (SELECT s2.pipeline_key FROM samples s2 WHERE s2.patient_id = p.id ORDER BY s2.ingested_at DESC LIMIT 1) AS pipeline_key
    FROM patients p
    LEFT JOIN samples s ON s.patient_id = p.id
    GROUP BY p.id
    ORDER BY p.id DESC
  `);
  return result.rows;
}

export default async function PatientsPage() {
  let patients: PatientRow[] = [];
  let dbError: string | null = null;

  try {
    patients = await getPatients();
  } catch (err) {
    console.error("Failed to load patients:", err);
    dbError = "Failed to load patients. Please try again later.";
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Patients</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {patients.length} patient{patients.length !== 1 ? "s" : ""} in system
          </p>
        </div>
        <Link href="/upload" className="btn btn-primary">
          Upload VCF
        </Link>
      </div>

      {dbError && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6 text-sm text-red-700">
          Database error: {dbError}
        </div>
      )}

      {patients.length === 0 && !dbError ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg">No patients yet</p>
          <p className="text-sm mt-1">
            <Link href="/upload" className="text-blue-600 hover:underline">
              Upload a VCF file
            </Link>{" "}
            to get started.
          </p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Lab No.</th>
                <th className="px-4 py-3">NHS No.</th>
                <th className="px-4 py-3">DOB</th>
                <th className="px-4 py-3">Samples</th>
                <th className="px-4 py-3">Latest Sample</th>
                <th className="px-4 py-3">Pipeline</th>
                <th className="px-4 py-3">Workflow</th>
                <th className="px-4 py-3">Ingested</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {patients.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {p.name ?? <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono text-gray-700">
                    {p.lab_number}
                  </td>
                  <td className="px-4 py-3 font-mono text-gray-500">
                    {p.nhs_number ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {p.dob
                      ? new Date(p.dob).toLocaleDateString("en-GB")
                      : "—"}
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
                      ? new Date(p.latest_ingested_at).toLocaleDateString(
                          "en-GB"
                        )
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
