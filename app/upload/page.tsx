import UploadForm from "./UploadForm";
import { getPipelineKeys, getPipelinesConfig } from "@/lib/pipeline-config";

export default function UploadPage() {
  const keys = getPipelineKeys();
  const config = getPipelinesConfig();
  const pipelineOptions = keys.map((k) => ({
    key: k,
    label: config.pipelines[k].label,
  }));

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">Upload VCF</h1>
      <p className="text-sm text-gray-500 mb-6">
        Upload a VEP-annotated VCF file for a patient. The file will be uploaded
        directly to S3 and ingestion will be triggered automatically.
      </p>
      <UploadForm pipelineOptions={pipelineOptions} />
    </div>
  );
}
