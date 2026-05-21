import { useState } from "react";
import { getUploadUrl, ingestSample, authHeaders } from "../lib/api";
import { buildManifest } from "../lib/fhir-manifest";

// Dev path is active when running via Vite dev server or explicitly set.
// Evaluated inside the submit handler (not at module level) so tests can control it.

type UploadPhase = "idle" | "uploading" | "ingesting" | "done" | "error";

export default function UploadForm({
  pipelineOptions,
}: {
  pipelineOptions: { key: string; label: string }[];
}) {
  const [labNumber, setLabNumber] = useState("");
  // Note: dob not collected — removed from patients table by migration 004 (GDPR)
  const [sampleName, setSampleName] = useState("");
  const [caseType, setCaseType] = useState<"germline" | "somatic">("germline");
  const [sequencingDate, setSequencingDate] = useState("");
  const [pipelineKey, setPipelineKey] = useState(pipelineOptions[0]?.key ?? "");
  const [file, setFile] = useState<File | null>(null);

  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isUploading = phase === "uploading" || phase === "ingesting";

  async function handleDevUpload() {
    setPhase("ingesting");
    setProgress("Ingesting VCF…");

    const fd = new FormData();
    fd.append("vcf", file!);
    fd.append("lab_number", labNumber.trim());
    fd.append("specimen_name", sampleName.trim() || file!.name);
    fd.append("case_type", caseType);
    if (pipelineKey) fd.append("pipeline_key", pipelineKey);
    if (sequencingDate) fd.append("sequencing_date", sequencingDate);

    const resp = await fetch("/api/ingest-direct", {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { detail = (await resp.json()).detail ?? detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    const body = await resp.json();

    setPhase("done");
    setProgress(`Sample ${body.sample_id} ingested successfully.`);
  }

  async function handleProdUpload() {
    setPhase("uploading");
    setProgress("Requesting upload URLs…");

    const urlResp = await getUploadUrl({
      vcf_filename: file!.name,
      // run_date omitted — backend defaults to today
    });

    setProgress("Uploading VCF to S3…");
    const vcfUploadResp = await fetch(urlResp.vcf_url, {
      method: "PUT",
      body: file!,
      headers: { "Content-Type": "application/octet-stream" },
    });
    if (!vcfUploadResp.ok) throw new Error("VCF S3 upload failed");

    setProgress("Uploading manifest…");
    const manifest = buildManifest({
      labNumber: labNumber.trim(),
      specimenName: sampleName.trim() || file!.name,
      caseType,
      pipelineKey: pipelineKey || null,
      sequencingDate: sequencingDate || null,
      vcfFilename: file!.name,
    });
    const manifestResp = await fetch(urlResp.manifest_url, {
      method: "PUT",
      body: JSON.stringify(manifest),
      headers: { "Content-Type": "application/json" },
    });
    if (!manifestResp.ok) throw new Error("Manifest S3 upload failed");

    setPhase("ingesting");
    setProgress("Triggering ingest…");
    const result = await ingestSample({
      vcf_s3_key: urlResp.vcf_key,
      user_id: (import.meta.env.VITE_USER_ID as string | undefined) ?? "analyst",
    });

    setPhase("done");
    setProgress(`Sample ${result.sample_id} ingested successfully.`);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPhase("idle"); // reset phase so submit button state machine starts clean on retry

    if (!labNumber.trim()) {
      setError("Lab record number is required.");
      return;
    }
    if (!file) {
      setError("Please select a VCF file.");
      return;
    }

    try {
      const isDev = import.meta.env.DEV || import.meta.env.VITE_APP_ENV === "development";
      if (isDev) {
        await handleDevUpload();
      } else {
        await handleProdUpload();
      }
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  if (phase === "done") {
    return (
      <div className="bg-green-50 border border-green-200 rounded p-5 text-sm text-green-700">
        ✓ {progress}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      {/* Patient */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Patient</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Lab record number <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={labNumber}
              onChange={(e) => setLabNumber(e.target.value)}
              required
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="LAB-2026-001"
            />
          </div>
        </div>
      </section>

      {/* Specimen */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Specimen</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Specimen name
            </label>
            <input
              type="text"
              value={sampleName}
              onChange={(e) => setSampleName(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="SPEC_001"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">Case type</label>
            <select
              value={caseType}
              onChange={(e) =>
                setCaseType(e.target.value as "germline" | "somatic")
              }
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            >
              <option value="germline">Germline</option>
              <option value="somatic">Somatic</option>
            </select>
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Sequencing date (optional)
            </label>
            <input
              type="date"
              value={sequencingDate}
              onChange={(e) => setSequencingDate(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            />
          </div>
        </div>
      </section>

      {/* Pipeline */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline</h2>
        <select
          value={pipelineKey}
          onChange={(e) => setPipelineKey(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
        >
          {pipelineOptions.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </section>

      {/* VCF file */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">VCF File</h2>
        <input
          type="file"
          accept=".vcf,.vcf.gz"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm text-gray-600"
        />
        {file && (
          <p className="text-xs text-gray-400 mt-1">
            {file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)
          </p>
        )}
      </section>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {isUploading && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-700">
          {progress}
        </div>
      )}

      <button
        type="submit"
        disabled={isUploading}
        className="btn btn-primary w-full py-2"
      >
        {isUploading ? progress : "Upload VCF"}
      </button>
    </form>
  );
}
