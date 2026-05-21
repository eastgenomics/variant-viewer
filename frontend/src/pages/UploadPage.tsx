import UploadForm from "../components/UploadForm";
import { getPipelineOptions } from "../lib/pipeline-config";

export default function UploadPage() {
  const pipelineOptions = getPipelineOptions();

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Upload VCF</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Submit a new VCF file for a patient. Variants will be imported and
          pre-computed criteria applied automatically.
        </p>
      </div>
      <UploadForm pipelineOptions={pipelineOptions} />
    </div>
  );
}
