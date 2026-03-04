export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Link from "next/link";
import { query } from "@/lib/db";
import WorkflowBadge from "@/components/WorkflowBadge";
import VariantTable from "./VariantTable";
import WorkflowControl from "./WorkflowControl";
import { getDefaultFilters } from "@/lib/pipeline-config";

interface PatientDetail {
  id: number;
  name: string | null;
  lab_number: string;
  nhs_number: string | null;
  dob: string | null;
}

interface SampleRow {
  id: number;
  name: string;
  vcf_filename: string | null;
  s3_key: string;
  pipeline_key: string | null;
  case_type: string;
  tissue: string | null;
  sequencing_date: string | null;
  ingested_at: string;
  workflow_status: string;
  workflow_updated_at: string | null;
  variant_count: number;
}

async function getPatient(id: string): Promise<PatientDetail | null> {
  const r = await query<PatientDetail>(
    `SELECT id, name, lab_number, nhs_number, dob::text FROM patients WHERE id = $1`,
    [id]
  );
  return r.rows[0] ?? null;
}

async function getSamples(patientId: string): Promise<SampleRow[]> {
  const r = await query<SampleRow>(
    `SELECT
       s.id, s.name, s.vcf_filename, s.s3_key, s.pipeline_key,
       s.case_type, s.tissue, s.sequencing_date::text, s.ingested_at::text,
       COALESCE(w.status, 'pending') AS workflow_status,
       w.updated_at::text AS workflow_updated_at,
       COUNT(v.id)::int AS variant_count
     FROM samples s
     LEFT JOIN workflow w ON w.sample_id = s.id
     LEFT JOIN variants v ON v.sample_id = s.id
     WHERE s.patient_id = $1
     GROUP BY s.id, w.status, w.updated_at
     ORDER BY s.ingested_at DESC`,
    [patientId]
  );
  return r.rows;
}

export default async function PatientPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [patient, samples] = await Promise.all([
    getPatient(id),
    getSamples(id),
  ]);

  if (!patient) notFound();

  const primarySample = samples[0] ?? null;
  const defaultFilters = primarySample?.pipeline_key
    ? getDefaultFilters(primarySample.pipeline_key)
    : getDefaultFilters("unknown");

  return (
    <div>
      <div className="mb-4">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
          ← Patients
        </Link>
      </div>

      {/* Patient header */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              {patient.name ?? patient.lab_number}
            </h1>
            <div className="flex gap-4 mt-1 text-sm text-gray-500">
              <span>
                Lab: <span className="font-mono">{patient.lab_number}</span>
              </span>
              {patient.nhs_number && (
                <span>
                  NHS: <span className="font-mono">{patient.nhs_number}</span>
                </span>
              )}
              {patient.dob && (
                <span>
                  DOB:{" "}
                  {new Date(patient.dob).toLocaleDateString("en-GB")}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Samples */}
      {samples.length === 0 ? (
        <div className="text-center py-10 text-gray-400">
          No samples ingested yet.
        </div>
      ) : (
        samples.map((sample) => (
          <div key={sample.id} className="mb-8">
            <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-gray-900">{sample.name}</span>
                  <span className="badge bg-gray-100 text-gray-600 capitalize">
                    {sample.case_type}
                  </span>
                  {sample.pipeline_key && (
                    <span className="badge bg-purple-50 text-purple-700">
                      {sample.pipeline_key.replace(/_/g, " ")}
                    </span>
                  )}
                  <WorkflowBadge status={sample.workflow_status} />
                  <span className="text-xs text-gray-400">
                    {sample.variant_count.toLocaleString()} variants
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <WorkflowControl
                    sampleId={sample.id}
                    currentStatus={sample.workflow_status}
                  />
                </div>
              </div>
              {(sample.tissue || sample.sequencing_date) && (
                <div className="flex gap-4 mt-2 text-xs text-gray-400">
                  {sample.tissue && <span>Tissue: {sample.tissue}</span>}
                  {sample.sequencing_date && (
                    <span>
                      Collected:{" "}
                      {new Date(sample.sequencing_date).toLocaleDateString(
                        "en-GB"
                      )}
                    </span>
                  )}
                  <span>
                    Ingested:{" "}
                    {new Date(sample.ingested_at).toLocaleDateString("en-GB")}
                  </span>
                </div>
              )}
            </div>

            <VariantTable
              sampleId={sample.id}
              patientId={patient.id}
              defaultFilters={defaultFilters}
              pipelineKey={sample.pipeline_key}
            />
          </div>
        ))
      )}
    </div>
  );
}
