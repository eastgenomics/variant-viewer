export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Link from "next/link";
import { query } from "@/lib/db";
import PatientHeader from "@/components/PatientHeader";
import SpecimenCard, { type SpecimenRow } from "@/components/SpecimenCard";
import { getDefaultFilters } from "@/lib/pipeline-config";

interface PatientDetail {
  id: number;
  name: string | null;
  lab_number: string;
  nhs_number: string | null;
  dob: string | null;
}

async function getPatient(id: string): Promise<PatientDetail | null> {
  const r = await query<PatientDetail>(
    `SELECT id, name, lab_number, nhs_number, dob::text FROM patients WHERE id = $1`,
    [id]
  );
  return r.rows[0] ?? null;
}

async function getSamples(patientId: string): Promise<SpecimenRow[]> {
  const r = await query<SpecimenRow>(
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
  const [patient, specimens] = await Promise.all([
    getPatient(id),
    getSamples(id),
  ]);

  if (!patient) notFound();

  const primarySpecimen = specimens[0] ?? null;
  const defaultFilters = primarySpecimen?.pipeline_key
    ? getDefaultFilters(primarySpecimen.pipeline_key)
    : getDefaultFilters("unknown");

  return (
    <div>
      <div className="mb-4">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
          ← Cases
        </Link>
      </div>

      <PatientHeader patient={patient} />

      {specimens.length === 0 ? (
        <div className="text-center py-10 text-gray-400">
          No specimens ingested yet.
        </div>
      ) : (
        specimens.map((specimen) => (
          <SpecimenCard
            key={specimen.id}
            specimen={specimen}
            patientId={patient.id}
            defaultFilters={defaultFilters}
            pipelineKey={specimen.pipeline_key}
          />
        ))
      )}
    </div>
  );
}
