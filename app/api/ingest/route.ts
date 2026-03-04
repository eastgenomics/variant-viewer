/**
 * Manual ingest trigger — POST with an S3 VCF key.
 * Calls the same lib/ingest.ts logic as the Lambda handler.
 * Use when: VCF was placed in S3 without going through upload form,
 * or Lambda auto-ingest failed.
 */

import { NextRequest, NextResponse } from "next/server";
import { ingestVcf } from "@/lib/ingest";

export async function POST(req: NextRequest) {
  let body: { s3Key?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { s3Key } = body;
  if (!s3Key) {
    return NextResponse.json(
      { error: "s3Key is required in request body" },
      { status: 400 }
    );
  }

  const bucket = process.env.VCF_BUCKET_NAME;
  if (!bucket) {
    return NextResponse.json(
      { error: "VCF_BUCKET_NAME environment variable not set" },
      { status: 500 }
    );
  }

  try {
    const result = await ingestVcf({ s3Key, s3Bucket: bucket });
    return NextResponse.json({
      success: true,
      patientId: result.patientId,
      sampleId: result.sampleId,
      variantCount: result.variantCount,
      pipelineKey: result.pipelineKey,
    });
  } catch (err) {
    console.error("Ingest error:", err);
    return NextResponse.json(
      { error: "Ingest failed. Please check the logs for details." },
      { status: 500 }
    );
  }
}
