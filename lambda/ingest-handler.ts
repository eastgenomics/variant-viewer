/**
 * Lambda entry point for S3-triggered VCF ingest.
 * Triggered by S3 ObjectCreated events on *.vcf.gz and *.vcf objects.
 */

import type { S3Event, Context } from "aws-lambda";
import { S3Client } from "@aws-sdk/client-s3";
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from "@aws-sdk/client-secrets-manager";
import { ingestVcf } from "../lib/ingest";

let secretsResolved = false;

async function resolveSecrets(): Promise<void> {
  if (secretsResolved) return;
  const secretArn = process.env.DB_SECRET_ARN;
  if (!secretArn) {
    // DATABASE_URL must be set via env when DB_SECRET_ARN is absent
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL or DB_SECRET_ARN must be set");
    }
    secretsResolved = true;
    return;
  }

  const sm = new SecretsManagerClient({
    region: process.env.AWS_REGION ?? "eu-west-2",
  });
  const resp = await sm.send(
    new GetSecretValueCommand({ SecretId: secretArn })
  );
  const secret = JSON.parse(resp.SecretString ?? "{}");

  // Secrets Manager stores: { username, password, host, port, dbname }
  process.env.DATABASE_URL = `postgresql://${secret.username}:${encodeURIComponent(
    secret.password
  )}@${secret.host}:${secret.port ?? 5432}/${secret.dbname}`;

  secretsResolved = true;
}

const s3Client = new S3Client({ region: process.env.AWS_REGION ?? "eu-west-2" });

export const handler = async (
  event: S3Event,
  _context: Context
): Promise<void> => {
  await resolveSecrets();

  const bucket = process.env.VCF_BUCKET_NAME;
  if (!bucket) {
    throw new Error("VCF_BUCKET_NAME environment variable not set");
  }

  for (const record of event.Records) {
    const s3Key = decodeURIComponent(
      record.s3.object.key.replace(/\+/g, " ")
    );

    // Guard: only process VCF files (S3 event filter should already do this)
    if (!s3Key.endsWith(".vcf.gz") && !s3Key.endsWith(".vcf")) {
      console.log(`Skipping non-VCF key: ${s3Key}`);
      continue;
    }

    console.log(`Ingesting s3://${bucket}/${s3Key}`);
    const start = Date.now();

    try {
      const result = await ingestVcf({
        s3Key,
        s3Bucket: bucket,
        s3Client,
      });
      const elapsed = ((Date.now() - start) / 1000).toFixed(1);
      console.log(
        `Ingest complete: patientId=${result.patientId} sampleId=${result.sampleId} ` +
          `variants=${result.variantCount} pipeline=${result.pipelineKey ?? "unknown"} ` +
          `elapsed=${elapsed}s`
      );
    } catch (err) {
      // Log and re-throw so Lambda marks as failed → DLQ picks it up
      console.error(`Ingest failed for ${s3Key}:`, err);
      throw err;
    }
  }
};
