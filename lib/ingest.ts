/**
 * Core VCF ingest logic.
 * Shared by Lambda handler (lambda/ingest-handler.ts) and API route (app/api/ingest/route.ts).
 */

import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { Readable } from "stream";
import { createGunzip } from "zlib";
import { PoolClient } from "pg";
import Ajv from "ajv";
import { parseVcf, VcfVariant } from "./vcf-parser";
import { parseManifest, ParsedManifest } from "./fhir-manifest";
import { withTransaction } from "./db";
import { preComputeCriteria } from "./pre-compute-criteria";
import { selectFramework, getFrameworkVersion } from "./classification-engine";
import { detectPipelineKey } from "./pipeline-config";
import manifestSchema from "../config/manifest-schema.json";

export interface IngestOptions {
  s3Key: string;
  s3Bucket: string;
  /** Pre-parsed manifest (from sidecar JSON). If omitted, derived from S3 sidecar. */
  manifest?: ParsedManifest;
  s3Client?: S3Client;
}

export interface IngestResult {
  patientId: number;
  sampleId: number;
  variantCount: number;
  pipelineKey: string | null;
}

function getS3Client(provided?: S3Client): S3Client {
  return (
    provided ??
    new S3Client({ region: process.env.AWS_REGION ?? "eu-west-2" })
  );
}

/** Derive the sidecar manifest S3 key from the VCF key */
export function sidecarKeyFromVcfKey(vcfKey: string): string {
  return vcfKey.replace(/\.(vcf\.gz|vcf)$/, ".manifest.json");
}

/** Read and parse the sidecar manifest from S3 */
async function readManifest(
  s3: S3Client,
  bucket: string,
  vcfKey: string
): Promise<ParsedManifest> {
  const sidecarKey = sidecarKeyFromVcfKey(vcfKey);
  const cmd = new GetObjectCommand({ Bucket: bucket, Key: sidecarKey });
  const resp = await s3.send(cmd);
  if (!resp.Body) throw new Error(`No body in S3 response for ${sidecarKey}`);
  const raw = await resp.Body.transformToString("utf-8");
  const manifestJson = JSON.parse(raw);

  // Validate against JSON schema before parsing
  const ajv = new Ajv();
  const validate = ajv.compile(manifestSchema);
  if (!validate(manifestJson)) {
    const errors = validate.errors?.map((e) => `${e.instancePath} ${e.message}`).join("; ");
    throw new Error(`Manifest schema validation failed: ${errors}`);
  }

  return parseManifest(manifestJson);
}

/** Upsert patient row and return patient id */
async function upsertPatient(
  client: PoolClient,
  manifest: ParsedManifest
): Promise<number> {
  const { lab_number, name, dob, nhs_number } = manifest.patient;
  const res = await client.query<{ id: number }>(
    `INSERT INTO patients (lab_number, name, dob, nhs_number)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (lab_number) DO UPDATE SET
       name = COALESCE(EXCLUDED.name, patients.name),
       dob  = COALESCE(EXCLUDED.dob,  patients.dob),
       nhs_number = COALESCE(EXCLUDED.nhs_number, patients.nhs_number)
     RETURNING id`,
    [lab_number, name ?? null, dob ?? null, nhs_number ?? null]
  );
  return res.rows[0].id;
}

/** Insert sample row and return sample id */
async function insertSample(
  client: PoolClient,
  patientId: number,
  manifest: ParsedManifest,
  s3Key: string,
  pipelineKey: string | null
): Promise<number> {
  const { sample_name, case_type, tissue, sequencing_date } = manifest.specimen;
  const vcfFilename = s3Key.split("/").pop() ?? s3Key;
  const res = await client.query<{ id: number }>(
    `INSERT INTO samples
       (patient_id, name, vcf_filename, s3_key, pipeline_key, case_type, tissue, sequencing_date)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     RETURNING id`,
    [
      patientId,
      sample_name,
      vcfFilename,
      s3Key,
      pipelineKey,
      case_type,
      tissue ?? null,
      sequencing_date ?? null,
    ]
  );
  return res.rows[0].id;
}

/** Batch-insert variants (1000 per batch) */
async function insertVariantBatch(
  client: PoolClient,
  sampleId: number,
  batch: VcfVariant[]
): Promise<number[]> {
  if (batch.length === 0) return [];
  const rows: unknown[][] = batch.map((v) => [
    sampleId,
    v.chrom,
    v.pos,
    v.ref,
    v.alt,
    v.qual,
    v.filter,
    v.gene,
    v.consequence,
    v.hgvs_c,
    v.hgvs_p,
    v.gnomad_af,
    v.clinvar_sig,
    v.revel_score,
    v.spliceai_max,
    JSON.stringify(v.info_json),
  ]);

  const placeholders = rows
    .map(
      (_, i) =>
        `($${i * 16 + 1},$${i * 16 + 2},$${i * 16 + 3},$${i * 16 + 4},$${
          i * 16 + 5
        },$${i * 16 + 6},$${i * 16 + 7},$${i * 16 + 8},$${i * 16 + 9},$${
          i * 16 + 10
        },$${i * 16 + 11},$${i * 16 + 12},$${i * 16 + 13},$${i * 16 + 14},$${
          i * 16 + 15
        },$${i * 16 + 16})`
    )
    .join(",");

  const params = rows.flat();
  const result = await client.query<{ id: number }>(
    `INSERT INTO variants
       (sample_id, chrom, pos, ref, alt, qual, filter, gene, consequence,
        hgvs_c, hgvs_p, gnomad_af, clinvar_sig, revel_score, spliceai_max, info_json)
     VALUES ${placeholders}
     RETURNING id`,
    params
  );
  return result.rows.map((r) => r.id);
}

/** Insert pre-computed criteria suggestions for a variant */
async function insertPreComputedCriteria(
  client: PoolClient,
  variantId: number,
  variant: VcfVariant,
  caseType: "germline" | "somatic"
): Promise<void> {
  const { framework } = selectFramework(caseType, variant.gene);
  const frameworkVersion = getFrameworkVersion(framework);
  const suggestions = preComputeCriteria(variant, caseType);

  if (suggestions.length === 0) return;

  // Create a classification record to hold pre-computed criteria
  const classRes = await client.query<{ id: number }>(
    `INSERT INTO variant_classification
       (variant_id, framework, framework_version, score, classification)
     VALUES ($1, $2, $3, NULL, NULL)
     RETURNING id`,
    [variantId, framework, frameworkVersion]
  );
  const classId = classRes.rows[0].id;

  for (const s of suggestions) {
    await client.query(
      `INSERT INTO classification_criterion
         (classification_id, criterion_code, applied, strength,
          pre_computed, pre_computed_value)
       VALUES ($1, $2, FALSE, $3, TRUE, $4)`,
      [classId, s.criterion_code, s.suggested_strength, s.pre_computed_value]
    );
  }
}

const BATCH_SIZE = 1000;

/** Core ingest logic: takes a VCF stream + parsed manifest + a stable key for idempotency. */
export async function ingestFromStream(
  stream: NodeJS.ReadableStream,
  manifest: ParsedManifest,
  s3Key: string
): Promise<IngestResult> {
  const batchBuffer: VcfVariant[] = [];
  let totalVariants = 0;
  const caseType = manifest.specimen.case_type;

  const result = await withTransaction(async (client) => {
    let detectedPipelineKey: string | null = null;
    // Advisory lock on the s3_key hash to prevent concurrent re-ingest
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [s3Key]);

    // Idempotent: delete existing sample for this s3_key
    await client.query("DELETE FROM samples WHERE s3_key = $1", [s3Key]);

    const patientId = await upsertPatient(client, manifest);

    // Detect pipeline key from manifest task or VCF headers (resolved after parse)
    let pipelineKey = manifest.task.pipeline_key ?? null;

    // We need sampleId before inserting variants, but pipeline_key comes from VCF parse.
    // Insert sample with provisional pipeline_key, update after parse.
    const sampleId = await insertSample(
      client,
      patientId,
      manifest,
      s3Key,
      pipelineKey
    );

    // Create initial workflow record
    await client.query(
      `INSERT INTO workflow (sample_id, status) VALUES ($1, 'pending')`,
      [sampleId]
    );

    // Parse VCF
    await parseVcf(Readable.from(stream as AsyncIterable<string>), async (variant) => {
      batchBuffer.push(variant);
      totalVariants++;

      if (batchBuffer.length >= BATCH_SIZE) {
        const ids = await insertVariantBatch(client, sampleId, batchBuffer);
        // Pre-compute criteria per batch to keep memory bounded
        for (let i = 0; i < batchBuffer.length; i++) {
          await insertPreComputedCriteria(client, ids[i], batchBuffer[i], caseType);
        }
        batchBuffer.length = 0;
      }
    }).then(async (meta) => {
      // Insert remaining buffer
      if (batchBuffer.length > 0) {
        const ids = await insertVariantBatch(client, sampleId, batchBuffer);
        for (let i = 0; i < batchBuffer.length; i++) {
          await insertPreComputedCriteria(client, ids[i], batchBuffer[i], caseType);
        }
        batchBuffer.length = 0;
      }

      // Update pipeline_key if detected from VCF headers
      if (!pipelineKey) {
        detectedPipelineKey = detectPipelineKey(meta.header_lines);
        if (detectedPipelineKey) {
          await client.query(
            "UPDATE samples SET pipeline_key = $1 WHERE id = $2",
            [detectedPipelineKey, sampleId]
          );
          pipelineKey = detectedPipelineKey;
        }
      }
    });

    return { patientId, sampleId, variantCount: totalVariants, pipelineKey };
  });

  return result;
}

export async function ingestVcf(options: IngestOptions): Promise<IngestResult> {
  const { s3Key, s3Bucket, s3Client: providedClient } = options;
  const s3 = getS3Client(providedClient);

  const manifest = options.manifest ?? (await readManifest(s3, s3Bucket, s3Key));

  const vcfCmd = new GetObjectCommand({ Bucket: s3Bucket, Key: s3Key });
  const vcfResp = await s3.send(vcfCmd);
  if (!vcfResp.Body) throw new Error(`No body in S3 response for ${s3Key}`);
  let stream = vcfResp.Body as unknown as NodeJS.ReadableStream;

  // Decompress .vcf.gz files
  if (s3Key.endsWith(".vcf.gz")) {
    stream = stream.pipe(createGunzip());
  }

  return ingestFromStream(stream, manifest, s3Key);
}
