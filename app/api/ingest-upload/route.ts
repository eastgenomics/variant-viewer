/**
 * Local-dev direct upload route.
 * Accepts a multipart/form-data POST with the VCF file + patient fields.
 * Bypasses S3 entirely — reads the file buffer directly.
 * Not used in production (S3 presigned URL path is used there).
 */

import { NextRequest, NextResponse } from "next/server";
import { Readable } from "stream";
import { createGunzip } from "zlib";
import { ingestFromStream } from "@/lib/ingest";
import { buildManifest } from "@/lib/fhir-manifest";

export async function POST(req: NextRequest) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { error: "Direct upload not available in production" },
      { status: 403 }
    );
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data" }, { status: 400 });
  }

  const file = formData.get("vcf") as File | null;
  if (!file) {
    return NextResponse.json({ error: "vcf file field required" }, { status: 400 });
  }

  const labNumber = (formData.get("lab_number") as string | null)?.trim();
  if (!labNumber) {
    return NextResponse.json({ error: "lab_number required" }, { status: 400 });
  }

  const manifest = buildManifest(
    {
      lab_number: labNumber,
      nhs_number: (formData.get("nhs_number") as string | null) || null,
      name: (formData.get("patient_name") as string | null) || null,
      dob: (formData.get("dob") as string | null) || null,
    },
    {
      sample_name: (formData.get("sample_name") as string | null) || file.name,
      case_type:
        (formData.get("case_type") as "germline" | "somatic" | null) ??
        "germline",
      tissue: null,
      sequencing_date:
        (formData.get("sequencing_date") as string | null) || null,
    },
    {
      pipeline_key:
        (formData.get("pipeline_key") as string | null) || null,
      pipeline_version:
        (formData.get("pipeline_version") as string | null) || null,
      run_id: (formData.get("run_id") as string | null) || null,
      vcf_filename: file.name,
    }
  );

  // Use a synthetic s3_key for local uploads so idempotency still works
  const s3Key = `local://${labNumber}/${file.name}`;

  try {
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const isGzip = file.name.endsWith(".gz");

    let readable: NodeJS.ReadableStream = Readable.from(buffer);
    if (isGzip) {
      const gunzip = createGunzip();
      readable = Readable.from(buffer).pipe(gunzip);
    }

    // Parse the FHIR manifest (buildManifest returns a Bundle object — parse it back)
    const { parseManifest } = await import("@/lib/fhir-manifest");
    const parsedManifest = parseManifest(manifest);

    const result = await ingestFromStream(readable, parsedManifest, s3Key);

    return NextResponse.json({
      success: true,
      patientId: result.patientId,
      sampleId: result.sampleId,
      variantCount: result.variantCount,
      pipelineKey: result.pipelineKey,
    });
  } catch (err) {
    console.error("Local ingest error:", err);
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
