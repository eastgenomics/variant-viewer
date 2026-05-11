# REFERENCE — variant-viewer API layer (PRs 6 & 7)

## 1. Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | Yes (or `API_KEY_SECRET_ARN`) | — | Shared API key for `X-API-Key` header authentication |
| `API_KEY_SECRET_ARN` | Yes (or `API_KEY`) | — | ARN of Secrets Manager secret `{"api_key": "..."}` |
| `DATABASE_URL` | Yes (or `DB_SECRET_ARN`) | — | psycopg2 DSN — inherited from PRs 2–5 |
| `DB_SECRET_ARN` | Yes (or `DATABASE_URL`) | — | RDS credentials in Secrets Manager — inherited from PRs 2–5 |
| `VCF_BUCKET_NAME` | Yes (PR 7) | — | S3 bucket for VCF uploads, e.g. `variant-viewer-vcf-749929395031` |
| `AWS_REGION` | No | `eu-west-2` | AWS region for Secrets Manager + S3 clients |
| `APP_ENV` | No | — | Set to `production` to enable `sslmode=require` on DB |

**Secrets Manager format for `API_KEY_SECRET_ARN`:**
```json
{ "api_key": "your-secret-key-here" }
```

**`.env.example` additions for PRs 6–7:**
```
API_KEY=dev-api-key
VCF_BUCKET_NAME=variant-viewer-vcf-749929395031
```

---

## 2. Route catalogue

### PR 6 — Read routes

| Method | Path | Auth | Query params | Response |
|---|---|---|---|---|
| GET | `/api/health` | No | — | `HealthResponse` |
| GET | `/api/patients` | Yes | `limit` (1–200, default 50), `offset` (default 0), `search` (optional) | `PatientListResponse` |
| GET | `/api/patients/{patient_id}` | Yes | — | `PatientDetailResponse` |
| GET | `/api/samples/{sample_id}` | Yes | — | `SampleDetailResponse` |
| GET | `/api/samples/{sample_id}/variants` | Yes | `limit`, `offset` | `VariantListResponse` |
| GET | `/api/variants/{variant_id}` | Yes | — | `VariantDetailResponse` |
| GET | `/api/config/criteria/{framework}` | Yes | — | Criteria config JSON |

### PR 7 — Write routes

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/upload-url` | Yes | `UploadUrlRequest` | `UploadUrlResponse` |
| POST | `/api/ingest` | Yes | `IngestRequest` | `{"sample_id": int}` |
| PUT | `/api/workflow/{sample_id}` | Yes | `WorkflowUpdateRequest` | `{"sample_id": int, "status": str}` |
| POST | `/api/variants/{variant_id}/classify` | Yes | `ClassifyRequest` | `ClassifyResponse` |
| PUT | `/api/variants/{variant_id}/classification` | Yes | `ClassificationSubmitRequest` | `ClassificationSubmitResponse` |
| DELETE | `/api/variants/{variant_id}/classification/{classification_id}` | Yes | `{"user_id": str}` | `{"new_classification_id": int}` |

---

## 3. Request/response schemas

### Health
```json
GET /api/health → 200
{ "status": "ok", "version": "0.2.0" }
```

### Patient list
```json
GET /api/patients?limit=2&offset=0 → 200
{
  "items": [
    { "id": 1, "lab_number": "LAB-2024-00123", "name": "Jane Smith" },
    { "id": 2, "lab_number": "LAB-2024-00124", "name": null }
  ],
  "total": 47,
  "limit": 2,
  "offset": 0
}
```

### Patient detail
```json
GET /api/patients/1 → 200
{
  "id": 1, "lab_number": "LAB-2024-00123", "name": "Jane Smith",
  "created_at": "2024-11-05T10:00:00Z",
  "samples": [
    {
      "id": 10, "name": "26041S0057", "case_type": "germline",
      "pipeline_key": "dragen_germline",
      "ingested_at": "2024-11-05T10:05:00Z",
      "workflow_status": "reviewing"
    }
  ]
}
```

### Sample detail
```json
GET /api/samples/10 → 200
{
  "id": 10, "name": "26041S0057",
  "s3_key": "runs/2024-11-05/26041S0057.vcf.gz",
  "case_type": "germline", "pipeline_key": "dragen_germline",
  "tissue": "Peripheral blood", "sequencing_date": "2024-11-05",
  "ingested_at": "2024-11-05T10:05:00Z",
  "patient": { "id": 1, "lab_number": "LAB-2024-00123", "name": "Jane Smith" },
  "workflow_status": "reviewing",
  "variant_count": 42
}
```

### Variant list
```json
GET /api/samples/10/variants?limit=3&offset=0 → 200
{
  "items": [
    {
      "id": 100, "chrom": "17", "pos": 41276045, "ref": "A", "alt": "T",
      "gene": "BRCA1", "consequence": "missense_variant",
      "gnomad_af": 0.0001, "revel_score": 0.75, "spliceai_max": 0.12,
      "classification": null, "score": null, "framework": null, "locked_at": null
    }
  ],
  "total": 42, "limit": 3, "offset": 0
}
```

### Variant detail
```json
GET /api/variants/100 → 200
{
  "id": 100, "chrom": "17", "pos": 41276045, "ref": "A", "alt": "T",
  "gene": "BRCA1", "consequence": "missense_variant",
  "hgvs_c": "c.100A>T", "hgvs_p": "p.Lys34Asn",
  "gnomad_af": 0.0001, "revel_score": 0.75, "spliceai_max": 0.12,
  "clinvar_sig": null, "info_json": {},
  "active_classification": {
    "id": 50, "framework": "acgs_snv", "framework_version": "ACGS 2024 Best Practice Guidelines",
    "score": null, "classification": null, "locked_at": null, "locked_by": null,
    "criteria": [
      {
        "id": 1, "criterion_code": "PM2", "applied": false, "strength": "supporting",
        "notes": null, "evidence_links": [], "pre_computed": true,
        "pre_computed_value": "gnomAD AF absent"
      }
    ]
  }
}
```

### Config criteria
```json
GET /api/config/criteria/acgs_snv → 200
{
  "version": "ACGS 2024 Best Practice Guidelines",
  "framework": "acgs_snv",
  "criteria": [
    {
      "code": "PVS1", "label": "PVS1", "category": "functional",
      "direction": "pathogenic", "default_strength": "very_strong",
      "permitted_strengths": ["very_strong", "strong", "moderate", "supporting"],
      "adjustable": true, "description": "...", "pre_computable": true
    }
    // ... 27 more criteria
  ],
  "combination_rules": [ ... ],
  "thresholds": { ... }
}
```

### Upload URL
```json
POST /api/upload-url
Body: { "vcf_filename": "26041S0057.vcf.gz", "run_date": "2024-11-05" }
→ 200
{
  "vcf_url": "https://variant-viewer-vcf-749929395031.s3.eu-west-2.amazonaws.com/runs/2024-11-05/26041S0057.vcf.gz?X-Amz-...",
  "manifest_url": "https://variant-viewer-vcf-749929395031.s3.eu-west-2.amazonaws.com/runs/2024-11-05/26041S0057.manifest.json?X-Amz-...",
  "vcf_key": "runs/2024-11-05/26041S0057.vcf.gz",
  "manifest_key": "runs/2024-11-05/26041S0057.manifest.json",
  "expires_in": 3600
}
```

### Ingest
```json
POST /api/ingest
Body: { "vcf_s3_key": "runs/2024-11-05/26041S0057.vcf.gz", "user_id": "jsmith" }
→ 200:  { "sample_id": 42 }
→ 400:  { "detail": "Unsupported VCF key format: ..." }
→ 409:  { "detail": "Duplicate submission: ..." }
```

### Workflow update
```json
PUT /api/workflow/10
Body: { "status": "reviewing", "user_id": "jsmith" }
→ 200:  { "sample_id": 10, "status": "reviewing" }
→ 404:  { "detail": "Sample workflow not found" }
→ 422:  { "detail": "Invalid transition: pending → reported" }
```

### Classify (score only)
```json
POST /api/variants/100/classify
Body:
{
  "criteria": [
    { "criterion_code": "PVS1", "applied": true, "strength": "very_strong" },
    { "criterion_code": "PM2",  "applied": true, "strength": "supporting" }
  ],
  "framework": "acgs_snv",
  "combination_rules": []
}
→ 200: { "score": 9, "classification": "Likely_Pathogenic", "warnings": [] }
```

### Classification submit (persist + lock)
```json
PUT /api/variants/100/classification
Body:
{
  "criteria": [
    { "criterion_code": "PVS1", "applied": true, "strength": "very_strong",
      "notes": "Frameshift confirmed", "evidence_links": [], "pre_computed": false },
    { "criterion_code": "PM2",  "applied": true, "strength": "supporting",
      "pre_computed": true, "pre_computed_value": "gnomAD AF absent" }
  ],
  "framework": "acgs_snv",
  "combination_rules": [],
  "locked_by": "jsmith",
  "user_id": "jsmith"
}
→ 200:
{
  "classification_id": 99,
  "score": 9, "classification": "Likely_Pathogenic",
  "warnings": [], "locked_at": "2024-11-05T14:30:00Z"
}
```

### Classification reset
```json
DELETE /api/variants/100/classification/50
Body: { "user_id": "jsmith" }
→ 200: { "new_classification_id": 51 }
→ 404: { "detail": "Classification not found" }
```

---

## 4. Error response shapes

All errors use FastAPI's default `{"detail": str}` shape.

| Status | When |
|---|---|
| 400 | `vcf_filename` not `.vcf`/`.vcf.gz`; `ValueError`; `jsonschema.ValidationError` |
| 401 | `X-API-Key` absent or wrong |
| 404 | Patient / sample / variant / classification not found |
| 409 | `DuplicateSubmissionError` from `ingest_sample()` |
| 422 | FastAPI request validation failure OR invalid workflow transition |
| 500 | Unhandled `psycopg2.OperationalError` or other exception |

---

## 5. Audit log action strings

All write operations insert one `audit_log` row. Action strings:

| Action | Trigger |
|---|---|
| `classify` | `PUT /api/variants/{id}/classification` |
| `reset_classification` | `DELETE /api/variants/{id}/classification/{id}` |
| `update_workflow` | `PUT /api/workflow/{sample_id}` |
| `ingest` | `POST /api/ingest` (on success) |

---

## 6. Workflow state machine

```
pending ──→ reviewing ──→ reported
    ↘            ↘           ↘
              archived  ←─────┘
```

| From | To | Allowed |
|---|---|---|
| pending | reviewing | ✅ |
| pending | archived | ✅ |
| pending | reported | ❌ 422 |
| reviewing | reported | ✅ |
| reviewing | archived | ✅ |
| reported | archived | ✅ |
| archived | any | ❌ 422 |

---

## 7. Key SQL reference

### Patient list with optional search
```sql
-- Count
SELECT COUNT(*) AS n FROM patients
[WHERE lab_number ILIKE %s OR name ILIKE %s]

-- Rows
SELECT id, lab_number, name FROM patients
[WHERE lab_number ILIKE %s OR name ILIKE %s]
ORDER BY lab_number LIMIT %s OFFSET %s
```

### Patient detail + samples
```sql
-- Patient
SELECT id, lab_number, name, created_at FROM patients WHERE id = %s

-- Samples with workflow status
SELECT s.id, s.name, s.case_type, s.pipeline_key, s.ingested_at,
       COALESCE(w.status, 'pending') AS workflow_status
FROM samples s
LEFT JOIN workflow w ON w.sample_id = s.id
WHERE s.patient_id = %s
ORDER BY s.ingested_at DESC NULLS LAST
```

### Sample detail (single join query)
```sql
SELECT s.id, s.name, s.s3_key, s.case_type, s.pipeline_key,
       s.tissue, s.sequencing_date, s.ingested_at,
       p.id AS patient_id, p.lab_number, p.name AS patient_name,
       COALESCE(w.status, 'pending') AS workflow_status,
       COUNT(v.id) AS variant_count
FROM samples s
JOIN patients p ON p.id = s.patient_id
LEFT JOIN workflow w ON w.sample_id = s.id
LEFT JOIN variants v ON v.sample_id = s.id
WHERE s.id = %s
GROUP BY s.id, p.id, w.status
```

### Variant list with classification summary
```sql
-- Count
SELECT COUNT(*) AS n FROM variants WHERE sample_id = %s

-- Rows
SELECT v.id, v.chrom, v.pos, v.ref, v.alt, v.gene, v.consequence,
       v.gnomad_af, v.revel_score, v.spliceai_max,
       vc.classification, vc.score, vc.framework, vc.locked_at
FROM variants v
LEFT JOIN variant_classification vc
       ON vc.variant_id = v.id AND vc.deleted_at IS NULL
WHERE v.sample_id = %s
ORDER BY v.chrom, v.pos
LIMIT %s OFFSET %s
```

### Variant detail (3 queries)
```sql
-- 1. Variant + case_type
SELECT v.*, s.case_type FROM variants v
JOIN samples s ON s.id = v.sample_id WHERE v.id = %s

-- 2. Active classification
SELECT id, framework, framework_version, score, classification, locked_at, locked_by
FROM variant_classification
WHERE variant_id = %s AND deleted_at IS NULL

-- 3. Criteria
SELECT id, criterion_code, applied, strength, notes, evidence_links,
       pre_computed, pre_computed_value
FROM classification_criterion
WHERE classification_id = %s ORDER BY id
```

### Classification persist
```sql
-- Soft-delete current (if any)
UPDATE variant_classification
SET deleted_at = NOW()
WHERE variant_id = %s AND deleted_at IS NULL

-- Insert new locked classification
INSERT INTO variant_classification
  (variant_id, framework, framework_version, score, classification, locked_at, locked_by)
VALUES (%s, %s, %s, %s, %s, NOW(), %s)
RETURNING id

-- Insert each criterion
INSERT INTO classification_criterion
  (classification_id, criterion_code, applied, strength, notes, evidence_links,
   pre_computed, pre_computed_value)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

-- Audit log
INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_value, new_value)
VALUES (%s, 'classify', 'classification', %s, %s, %s)
```

### Classification reset (soft-delete + blank)
```sql
-- Verify exists and is active
SELECT id, variant_id, framework, framework_version
FROM variant_classification
WHERE id = %s AND variant_id = %s AND deleted_at IS NULL

-- Soft-delete
UPDATE variant_classification SET deleted_at = NOW() WHERE id = %s

-- Insert blank replacement (unlocked, unscored)
INSERT INTO variant_classification (variant_id, framework, framework_version)
VALUES (%s, %s, %s)
RETURNING id

-- Audit
INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_value, new_value)
VALUES (%s, 'reset_classification', 'classification', %s, %s, NULL)
```

---

## 8. Useful links

| Resource | URL |
|---|---|
| FastAPI docs | https://fastapi.tiangolo.com/ |
| Pydantic v2 | https://docs.pydantic.dev/latest/ |
| psycopg2 docs | https://www.psycopg.org/docs/ |
| boto3 S3 presigned URLs | https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html |
| FastAPI security (API key) | https://fastapi.tiangolo.com/tutorial/security/http-basic-auth/ |
| asyncio.to_thread | https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread |
| GitHub repo | https://github.com/eastgenomics/variant-viewer |
