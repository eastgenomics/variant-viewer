---
name: Lambda VCF ingest and S3 upload
description: Lambda ingest pipeline configuration, S3 presigned URL setup, manifest naming conventions, VCF annotation formats, and bulk upload patterns
type: project
originSessionId: 8256cc3d-ebf1-485b-b123-491e9f90eb74
---
## Lambda Configuration

- Lambda needs `NODE_ENV=production` in its environment — `lib/db.ts` gates SSL on this value. Without it, Lambda connects without SSL and RDS returns `no pg_hba.conf entry ... no encryption`.
- After pushing a new Lambda ECR image with a mutable tag (`latest`), run `aws lambda update-function-code --image-uri ...` to force Lambda to pull the new image — Terraform alone does not do this when the tag hasn't changed.
- Compile TypeScript before building: `./node_modules/.bin/tsc --project tsconfig.lambda.json` -> outputs to `dist/`.
- Ajv v8 strict mode: instantiate with `{ strict: false }` when using JSON schemas lacking explicit `"type":"object"`.
- Lambda needs `s3:ListBucket` IAM permission — without it, a missing manifest key returns 403 instead of 404.

## S3 Presigned Upload

- S3 bucket needs a **CORS policy** (`aws_s3_bucket_cors_configuration`) allowing `PUT` from the app domain — browser blocks the cross-origin request without it.
- Presigned URL `ContentType` must match the `Content-Type` header sent by the browser — S3 returns 403 if they differ. Generate the URL with the correct type based on file extension (`.vcf.gz` -> `application/gzip`, `.vcf` -> `text/plain`).
- Patient list has a short delay after upload — Lambda ingests asynchronously after the S3 event triggers.

## S3 Direct Upload (CLI)

- Must upload **manifest before VCF** — Lambda triggers on VCF ObjectCreated and immediately fetches the sidecar manifest.
- Manifest filename: replace `.vcf.gz` / `.vcf` with `.manifest.json` (e.g. `sample.vcf.gz` -> `sample.manifest.json`). Common mistake: uploading as `.json` instead of `.manifest.json`.
- Re-trigger Lambda after fixing a manifest: `aws s3 cp s3://bucket/key s3://bucket/key` (copy to same key fires ObjectCreated).
- The vv-dev profile does NOT have `s3:ListAllMyBuckets` — get the bucket name from Terraform output: `AWS_PROFILE=vv-admin terraform output s3_bucket_name`.

## VCF Annotation Formats Supported

The VCF parser (`lib/vcf-parser.ts`) auto-detects and handles three formats:
1. **Standard VEP pipe-delimited CSQ** — requires `##INFO=<ID=CSQ,...,Format:>` header line
2. **Flat CSQ_* fields** — East Genomics pipeline output (e.g. `CSQ_SYMBOL=BRCA1;CSQ_Consequence=missense_variant`). Added 2026-04-09.
3. **SnpEff ANN** — `##INFO=<ID=ANN,...>` format, gene and consequence only

## Manifest Format

- FHIR R4 Bundle (collection) with Patient, Specimen, Task resources.
- Patient must have a lab-number identifier (`system: https://fhir.example-lab.org/Id/lab-number`). NHS number is optional and stored but not displayed.
- `pipeline_key` in Task `code.text` must match a key in `config/pipelines.yaml` (e.g. `mutect2`, `gatk_haplotypecaller`). Omit to fall back to `unknown` filters.
- Example manifests in `docs/examples/`.

## Bulk Upload Script

Python script at `/tmp/upload_vcfs.py` generates FHIR manifests and uploads VCFs + manifests to S3 in bulk. Datasets configured:
- `~/Downloads/grab/haem_out` → somatic, mutect2, lab prefix `HAE-2026-`
- `~/Downloads/grab/twe_out` → germline, gatk_haplotypecaller, lab prefix `TWE-2026-`

Re-run after clearing test data: `python3 /tmp/upload_vcfs.py`
