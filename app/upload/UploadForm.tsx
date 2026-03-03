"use client";

import { useState } from "react";
import { buildManifest } from "@/lib/fhir-manifest";

interface PipelineOption {
  key: string;
  label: string;
}

const IS_DEV = process.env.NODE_ENV !== "production";

type UploadPhase =
  | "idle"
  | "requesting-urls"
  | "uploading-manifest"
  | "uploading-vcf"
  | "ingesting"
  | "done"
  | "error";

export default function UploadForm({
  pipelineOptions,
}: {
  pipelineOptions: PipelineOption[];
}) {
  // Patient fields
  const [labNumber, setLabNumber] = useState("");
  const [patientName, setPatientName] = useState("");
  const [dob, setDob] = useState("");
  const [nhsNumber, setNhsNumber] = useState("");

  // Sample fields
  const [sampleName, setSampleName] = useState("");
  const [caseType, setCaseType] = useState<"germline" | "somatic">("germline");
  const [sequencingDate, setSequencingDate] = useState("");

  // Pipeline fields
  const [pipelineKey, setPipelineKey] = useState(pipelineOptions[0]?.key ?? "");
  const [pipelineVersion, setPipelineVersion] = useState("");
  const [runId, setRunId] = useState("");

  // File
  const [file, setFile] = useState<File | null>(null);

  // Upload state
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resultSampleId, setResultSampleId] = useState<number | null>(null);

  function validateNhsLocally(nhs: string): boolean {
    const digits = nhs.replace(/\s/g, "");
    if (!/^\d{10}$/.test(digits)) return false;
    const weights = [10, 9, 8, 7, 6, 5, 4, 3, 2];
    let sum = 0;
    for (let i = 0; i < 9; i++) sum += parseInt(digits[i]) * weights[i];
    const rem = sum % 11;
    const check = 11 - rem;
    if (check === 11) return parseInt(digits[9]) === 0;
    if (check === 10) return false;
    return parseInt(digits[9]) === check;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!labNumber.trim()) {
      setError("Lab record number is required.");
      return;
    }
    if (!file) {
      setError("Please select a VCF file.");
      return;
    }
    if (nhsNumber.trim() && !validateNhsLocally(nhsNumber.replace(/\s/g, ""))) {
      setError("NHS number is invalid (failed Luhn modulo-11 checksum).");
      return;
    }

    try {
      if (IS_DEV) {
        await handleDevUpload();
      } else {
        await handleProdUpload();
      }
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  /** Dev: POST file directly to /api/ingest-upload (no S3) */
  async function handleDevUpload() {
    setPhase("ingesting");
    setProgress("Ingesting VCF…");

    const fd = new FormData();
    fd.append("vcf", file!);
    fd.append("lab_number", labNumber.trim());
    if (patientName.trim()) fd.append("patient_name", patientName.trim());
    if (dob) fd.append("dob", dob);
    if (nhsNumber.trim()) fd.append("nhs_number", nhsNumber.trim());
    fd.append("sample_name", sampleName.trim() || file!.name);
    fd.append("case_type", caseType);
    if (sequencingDate) fd.append("sequencing_date", sequencingDate);
    if (pipelineKey) fd.append("pipeline_key", pipelineKey);
    if (pipelineVersion.trim()) fd.append("pipeline_version", pipelineVersion.trim());
    if (runId.trim()) fd.append("run_id", runId.trim());

    const resp = await fetch("/api/ingest-upload", { method: "POST", body: fd });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error ?? "Ingest failed");

    setPhase("done");
    setProgress(
      `Ingested ${body.variantCount.toLocaleString()} variants for patient ${body.patientId}.`
    );
  }

  /** Prod: presigned S3 PUT → Lambda auto-triggers ingest */
  async function handleProdUpload() {
    const vcfKey = `uploads/${labNumber.trim()}/${file!.name}`;

    // 1. Get presigned URLs
    setPhase("requesting-urls");
    setProgress("Requesting upload URLs…");
    const urlResp = await fetch(
      `/api/upload-url?vcfKey=${encodeURIComponent(vcfKey)}`
    );
    if (!urlResp.ok) {
      const err = await urlResp.json();
      throw new Error(err.error ?? "Failed to get upload URL");
    }
    const { vcfUrl, manifestUrl } = await urlResp.json();

    // 2. Build + upload manifest
    const manifest = buildManifest(
      {
        lab_number: labNumber.trim(),
        nhs_number: nhsNumber.trim() || null,
        name: patientName.trim() || null,
        dob: dob || null,
      },
      {
        sample_name: sampleName.trim() || file!.name,
        case_type: caseType,
        tissue: null,
        sequencing_date: sequencingDate || null,
      },
      {
        pipeline_key: pipelineKey || null,
        pipeline_version: pipelineVersion.trim() || null,
        run_id: runId.trim() || null,
        vcf_filename: file!.name,
      }
    );

    setPhase("uploading-manifest");
    setProgress("Uploading manifest…");
    const manifestResp = await fetch(manifestUrl, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(manifest),
    });
    if (!manifestResp.ok) {
      throw new Error(`Manifest upload failed: ${manifestResp.status}`);
    }

    // 3. Upload VCF → triggers Lambda
    setPhase("uploading-vcf");
    setProgress("Uploading VCF…");
    const vcfResp = await fetch(vcfUrl, {
      method: "PUT",
      headers: {
        "Content-Type": file!.name.endsWith(".gz")
          ? "application/gzip"
          : "text/plain",
      },
      body: file,
    });
    if (!vcfResp.ok) {
      throw new Error(`VCF upload failed: ${vcfResp.status}`);
    }

    setPhase("done");
    setProgress(
      "Upload complete. Ingestion triggered via Lambda — check the patient list in a moment."
    );
  }

  if (phase === "done") {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-6">
        <h2 className="text-green-800 font-semibold mb-2">Upload complete</h2>
        <p className="text-green-700 text-sm">{progress}</p>
        <div className="mt-4 flex gap-3">
          <a href="/" className="btn btn-primary text-sm">
            View patients →
          </a>
          <button
            className="btn btn-secondary text-sm"
            onClick={() => {
              setPhase("idle");
              setFile(null);
              setLabNumber("");
              setPatientName("");
              setDob("");
              setNhsNumber("");
              setSampleName("");
              setSequencingDate("");
              setRunId("");
              setPipelineVersion("");
            }}
          >
            Upload another
          </button>
        </div>
      </div>
    );
  }

  const isUploading = [
    "requesting-urls",
    "uploading-manifest",
    "uploading-vcf",
    "ingesting",
  ].includes(phase);

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Patient details */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Patient</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Lab record number <span className="text-red-500">*</span>
            </label>
            <input
              required
              type="text"
              value={labNumber}
              onChange={(e) => setLabNumber(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="LAB-2026-00123"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              NHS number (optional)
            </label>
            <input
              type="text"
              value={nhsNumber}
              onChange={(e) => setNhsNumber(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="9000000009"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Patient name (optional)
            </label>
            <input
              type="text"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="Jane Smith"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Date of birth (optional)
            </label>
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            />
          </div>
        </div>
      </section>

      {/* Sample details */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Sample</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Sample name
            </label>
            <input
              type="text"
              value={sampleName}
              onChange={(e) => setSampleName(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="SAMPLE_001"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Case type
            </label>
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

      {/* Pipeline details */}
      <section className="bg-white border border-gray-200 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">Pipeline</label>
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
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Pipeline version (optional)
            </label>
            <input
              type="text"
              value={pipelineVersion}
              onChange={(e) => setPipelineVersion(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="3.9.5"
            />
          </div>
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">
              Run ID (optional)
            </label>
            <input
              type="text"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              placeholder="RUN_2026_001"
            />
          </div>
        </div>
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
