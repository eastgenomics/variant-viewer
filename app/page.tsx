export const dynamic = "force-dynamic";

import Link from "next/link";
import { query } from "@/lib/db";
import PatientListTable, { PatientRow } from "@/components/PatientListTable";

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
          <h1 className="text-2xl font-semibold text-gray-900">Cases</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {patients.length} case{patients.length !== 1 ? "s" : ""} in system
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
          <p className="text-lg">No cases yet</p>
          <p className="text-sm mt-1">
            <Link href="/upload" className="text-blue-600 hover:underline">
              Upload a VCF file
            </Link>{" "}
            to get started.
          </p>
        </div>
      ) : (
        <PatientListTable patients={patients} />
      )}
    </div>
  );
}
