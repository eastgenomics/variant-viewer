"use client";

import WorkflowBadge from "@/components/WorkflowBadge";
import WorkflowControl from "@/app/patients/[id]/WorkflowControl";
import DeleteSampleButton from "@/app/patients/[id]/DeleteSampleButton";
import VariantTable from "@/app/patients/[id]/VariantTable";
import type { PipelineFilters } from "@/lib/pipeline-config";

export interface SpecimenRow {
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

export default function SpecimenCard({
  specimen,
  patientId,
  defaultFilters,
  pipelineKey,
}: {
  specimen: SpecimenRow;
  patientId: number;
  defaultFilters: PipelineFilters;
  pipelineKey: string | null;
}) {
  return (
    <div className="mb-8">
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-medium text-gray-900">{specimen.name}</span>
            <span className="badge bg-gray-100 text-gray-600 capitalize">
              {specimen.case_type}
            </span>
            {specimen.pipeline_key && (
              <span className="badge bg-purple-50 text-purple-700">
                {specimen.pipeline_key.replace(/_/g, " ")}
              </span>
            )}
            <WorkflowBadge status={specimen.workflow_status} />
            <span className="text-xs text-gray-400">
              {specimen.variant_count.toLocaleString()} variants
            </span>
          </div>
          <div className="flex items-center gap-3">
            <WorkflowControl
              sampleId={specimen.id}
              currentStatus={specimen.workflow_status}
            />
            <DeleteSampleButton
              id={specimen.id}
              name={specimen.name}
              workflowStatus={specimen.workflow_status}
            />
          </div>
        </div>
        {(specimen.tissue || specimen.sequencing_date) && (
          <div className="flex gap-4 mt-2 text-xs text-gray-400">
            {specimen.tissue && <span>Tissue: {specimen.tissue}</span>}
            {specimen.sequencing_date && (
              <span>
                Collected:{" "}
                {new Date(specimen.sequencing_date).toLocaleDateString("en-GB")}
              </span>
            )}
            <span>
              Ingested:{" "}
              {new Date(specimen.ingested_at).toLocaleDateString("en-GB")}
            </span>
          </div>
        )}
      </div>

      <VariantTable
        sampleId={specimen.id}
        patientId={patientId}
        defaultFilters={defaultFilters}
        pipelineKey={pipelineKey}
      />
    </div>
  );
}
