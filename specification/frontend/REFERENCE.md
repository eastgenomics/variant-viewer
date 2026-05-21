# REFERENCE — variant-viewer frontend SPA (PRs 8–11)

## 0. Backend pre-requisites

Several frontend features depend on backend extensions that do not yet exist in
the `main` branch. These **must be implemented before M19** (the frontend
scaffold). They are tracked as M_pre milestones in IMPLEMENTATION.md §2.

| # | Backend change | Affects |
|---|---|---|
| pre-1 | Extend `PatientSummary` with aggregate fields (`sample_count`, `latest_*`); `dob` NOT added (dropped by migration 004) | Patient list table columns |
| pre-2 | Extend `list_sample_variants` with filter + sort query params | Variant table filter bar |
| pre-3 | Extend `VariantSummary` with `hgvs_c`, `hgvs_p`, `clinvar_sig`, `classification_id`, `classification_locked_at` | Variant table columns |
| pre-4 | Add `DELETE /api/patients/{id}` (cascade, audit log) | Delete patient button |
| pre-5 | Add `DELETE /api/samples/{id}` (cascade, audit log; no server-side block — high-risk warning for `reported`/`archived` is client-side only) | Delete sample button |
| pre-6 | Make `locked_by: str \| None` in `ClassificationSubmitRequest` (`None` = draft, truthy string = locked) | Save draft button |
| pre-7 | Add `vcf_filename` to `SampleSummary` in `PatientDetailResponse` | SpecimenCard display |
| pre-8 | Add `POST /api/ingest-direct` accepting `multipart/form-data` (VCF file + patient/specimen fields); enables dev upload without S3 | UploadForm dev path |

---

## 1. Backend API endpoint catalogue

All endpoints are prefixed `/api`. In dev, Vite proxies `/api/*` to
`http://localhost:3000`. In production, nginx `proxy_pass` routes to the ECS
FastAPI service.

Authentication: all endpoints except `GET /api/health` require
`X-API-Key: <key>` header. Set via `VITE_API_KEY` env var.

### 1.1 Patient endpoints

| Method | Path | Purpose | Auth | Backend status |
|---|---|---|---|---|
| `GET` | `/api/patients` | Paginated patient list | ✓ | Exists (needs pre-1) |
| `GET` | `/api/patients/{id}` | Patient detail + sample list | ✓ | Exists (needs pre-7) |
| `DELETE` | `/api/patients/{id}` | Delete patient + cascade | ✓ | **Requires pre-4** |

**GET /api/patients — request params:**

| Param | Type | Required | Description |
|---|---|---|---|
| `search` | string | No | Filter by lab_number substring |
| `limit` | int | No | Page size (default 50) |
| `offset` | int | No | Page offset (default 0) |

**GET /api/patients response** (after pre-1):

```json
{
  "items": [
    {
      "id": 1,
      "lab_number": "LAB-2026-001",
      "name": null,
      "sample_count": 2,
      "latest_sample_id": 10,
      "latest_sample_name": "SPEC_001",
      "latest_workflow_status": "pending",
      "latest_ingested_at": "2026-04-01T12:00:00Z",
      "pipeline_key": "dragen_germline"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**GET /api/patients/{id} response** (after pre-7):

```json
{
  "id": 1,
  "lab_number": "LAB-2026-001",
  "name": null,
  "created_at": "2026-01-01T00:00:00Z",
  "samples": [
    {
      "id": 10,
      "name": "SPEC_001",
      "vcf_filename": "sample.vcf.gz",
      "case_type": "germline",
      "pipeline_key": "dragen_germline",
      "ingested_at": "2026-04-01T12:00:00Z",
      "workflow_status": "pending"
    }
  ]
}
```

---

### 1.2 Sample endpoints

| Method | Path | Purpose | Auth | Backend status |
|---|---|---|---|---|
| `GET` | `/api/samples/{id}` | Sample detail | ✓ | Exists |
| `DELETE` | `/api/samples/{id}` | Delete sample + cascade | ✓ | **Requires pre-5** |
| `GET` | `/api/samples/{id}/variants` | Paginated variant list | ✓ | Exists (needs pre-2, pre-3) |

**GET /api/samples/{id} response:**

```json
{
  "id": 10,
  "name": "SPEC_001",
  "s3_key": "runs/2026-04-01/sample.vcf.gz",
  "case_type": "germline",
  "pipeline_key": "dragen_germline",
  "tissue": "blood",
  "sequencing_date": "2026-01-01",
  "ingested_at": "2026-04-01T12:00:00Z",
  "patient": { "id": 1, "lab_number": "LAB-2026-001", "name": null },
  "workflow_status": "pending",
  "variant_count": 1523
}
```

**GET /api/samples/{id}/variants — request params** (after pre-2):

| Param | Type | Required | Description |
|---|---|---|---|
| `limit` | int | No | Page size (default 50) |
| `offset` | int | No | Page offset |
| `sort_by` | string | No | Column name: `chrom`, `gene`, `gnomad_af`, `revel_score`, `spliceai_max`, `classification` |
| `sort_dir` | `asc`\|`desc` | No | Sort direction (lowercase) |
| `gnomad_af_max` | float | No | Maximum gnomAD AF |
| `consequences` | string | No | Comma-separated VEP consequence terms |
| `clinvar_exclude` | string | No | Comma-separated ClinVar significance values to exclude |
| `gene` | string | No | Exact gene symbol match |

**Current backend (before pre-2):** only `limit` and `offset` are accepted.
All other params are silently ignored — the filter bar will render but have no effect.

**GET /api/samples/{id}/variants response** (after pre-3):

```json
{
  "items": [
    {
      "id": 200,
      "chrom": "17",
      "pos": 43094077,
      "ref": "A",
      "alt": "T",
      "gene": "BRCA1",
      "consequence": "missense_variant",
      "hgvs_c": "c.5096G>A",
      "hgvs_p": "p.Arg1699Gln",
      "gnomad_af": 0.000012,
      "clinvar_sig": "Pathogenic",
      "revel_score": 0.892,
      "spliceai_max": 0.01,
      "classification": "Likely_Pathogenic",
      "score": 9,
      "framework": "acgs_snv",
      "locked_at": "2026-05-01T10:00:00Z"
    }
  ],
  "total": 1523,
  "limit": 50,
  "offset": 0
}
```

**Current backend (before pre-3)** returns `items` with:
`{ id, chrom, pos, ref, alt, gene, consequence, gnomad_af, revel_score, spliceai_max, classification, score, framework, locked_at }` — missing `hgvs_c`, `hgvs_p`, `clinvar_sig`.

---

### 1.3 Variant endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/api/variants/{id}` | Variant detail + active classification + criteria | ✓ |
| `POST` | `/api/variants/{id}/classify` | Score only (no DB write) | ✓ |
| `PUT` | `/api/variants/{id}/classification` | Persist (and optionally lock) classification | ✓ |
| `DELETE` | `/api/variants/{id}/classification/{cls_id}` | Soft-delete + insert blank replacement | ✓ |

**GET /api/variants/{id} response** (current backend — `active_classification` with nested criteria):

```json
{
  "id": 200,
  "chrom": "17",
  "pos": 43094077,
  "ref": "A",
  "alt": "T",
  "gene": "BRCA1",
  "consequence": "missense_variant",
  "hgvs_c": "c.5096G>A",
  "hgvs_p": "p.Arg1699Gln",
  "gnomad_af": 0.000012,
  "clinvar_sig": "Pathogenic",
  "revel_score": 0.892,
  "spliceai_max": 0.01,
  "info_json": {},
  "active_classification": {
    "id": 45,
    "framework": "acgs_snv",
    "framework_version": "ACGS 2024",
    "score": 9,
    "classification": "Likely_Pathogenic",
    "locked_at": "2026-05-01T10:00:00Z",
    "locked_by": "analyst-1",
    "criteria": [
      {
        "id": 10,
        "criterion_code": "PVS1",
        "applied": true,
        "strength": "very_strong",
        "notes": null,
        "evidence_links": [],
        "pre_computed": true,
        "pre_computed_value": "Predicted LoF"
      }
    ]
  }
}
```

Note: `active_classification` is `null` when no classification exists. The
`ClassificationPage` splits this into `initialClassification` (minus `criteria`)
and `initialCriteria` when passing to `<ClassificationPanel>`.

**POST /api/variants/{id}/classify — request body:**

```json
{
  "criteria": [
    { "criterion_code": "PVS1", "applied": true, "strength": "very_strong" },
    { "criterion_code": "PM2",  "applied": true, "strength": "supporting" }
  ],
  "framework": "acgs_snv",
  "combination_rules": []
}
```

**POST /api/variants/{id}/classify — response:**

```json
{ "score": 9, "classification": "Likely_Pathogenic", "warnings": [] }
```

**PUT /api/variants/{id}/classification — request body** (after pre-6):

```json
{
  "criteria": [ "..." ],
  "framework": "acgs_snv",
  "combination_rules": [],
  "locked_by": "analyst-1",
  "user_id": "analyst-1"
}
```

Set `locked_by` to the user ID string to lock, or `null` for a draft save
(requires pre-6 — current backend requires non-null `locked_by`).

**PUT /api/variants/{id}/classification — response:**

```json
{
  "classification_id": 45,
  "score": 9,
  "classification": "Likely_Pathogenic",
  "warnings": []
}
```

Note: response field is `classification_id` (not `classification_id` within
a nested object). Update `ClassifyPersistResponse` TypeScript type accordingly.

**DELETE /api/variants/{id}/classification/{cls_id} — request body:**

```json
{ "user_id": "analyst-1" }
```

**DELETE response:**

```json
{ "new_classification_id": 46 }
```

---

### 1.4 Upload and ingest endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/api/upload-url` | Get presigned S3 PUT URLs | ✓ |
| `POST` | `/api/ingest` | Trigger manual ingest (dev / direct) | ✓ |

**POST /api/upload-url — request body:**

```json
{
  "vcf_filename": "sample.vcf.gz",
  "run_date": "2026-05-18"
}
```

**POST /api/upload-url — response:**

```json
{
  "vcf_url": "https://s3.amazonaws.com/bucket/runs/2026-05-18/sample.vcf.gz?...",
  "manifest_url": "https://s3.amazonaws.com/bucket/runs/2026-05-18/sample.manifest.json?...",
  "vcf_key": "runs/2026-05-18/sample.vcf.gz",
  "manifest_key": "runs/2026-05-18/sample.manifest.json",
  "expires_in": 3600
}
```

**POST /api/ingest — request body:**

```json
{
  "vcf_s3_key": "runs/2026-05-18/sample.vcf.gz",
  "user_id": "analyst-1"
}
```

**POST /api/ingest — response:**

```json
{ "sample_id": 42 }
```

---

### 1.4b Upload — dev path: `POST /api/ingest-direct`

Dev-only endpoint. Accepts a VCF file as `multipart/form-data` and ingests
directly without S3. Used by `UploadForm` when `import.meta.env.DEV` is true.

**Form fields:**

| Field | Required | Description |
|---|---|---|
| `vcf` | Yes | VCF file (.vcf or .vcf.gz) |
| `lab_number` | Yes | Patient lab record number |
| `specimen_name` | Yes | Specimen/sample name |
| `case_type` | No | `germline` (default) or `somatic` |
| `pipeline_key` | No | Pipeline identifier string |
| `user_id` | No | Analyst user ID (default: `analyst`) |
| `sequencing_date` | No | ISO date YYYY-MM-DD |

**Response (200):**

```json
{ "sample_id": 42, "message": "Ingested successfully" }
```

**Error responses:**
- 400: non-.vcf file, VCF parse error
- 409: duplicate upload (same filename + patient)
- 413: file too large (>500 MB)
- 500: other ingest failure

---

### 1.5 Workflow endpoint

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `PUT` | `/api/workflow/{sample_id}` | Advance or archive workflow status | ✓ |

**PUT /api/workflow/{sample_id} — request body:**

```json
{ "status": "reviewing", "user_id": "analyst-1" }
```

**Response:**

```json
{ "sample_id": 10, "status": "reviewing" }
```

**Error codes:**

| Code | Condition |
|---|---|
| 404 | Sample workflow not found |
| 409 | Concurrent modification — retry |
| 422 | Invalid state transition |

---

### 1.6 Config endpoint

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/api/config/criteria/{framework}` | Criteria definitions + combination rules | ✓ |

`framework` values: `acgs_snv`, `svig`.

**Response:**

```json
{
  "framework": "acgs_snv",
  "criteria": [
    {
      "code": "PVS1",
      "description": "Null variant in a gene where LoF is a known mechanism",
      "category": "population",
      "direction": "pathogenic",
      "default_strength": "very_strong",
      "adjustable": true,
      "permitted_strengths": ["very_strong", "strong", "moderate", "supporting"]
    }
  ],
  "combination_rules": [
    {
      "rule": "two_pm_as_ps",
      "codes": ["PM1", "PM2"],
      "message": "Two moderate pathogenic criteria count as one strong"
    }
  ]
}
```

---

## 2. Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_API_KEY` | No | — | API key sent as `X-API-Key` header. Omit in dev (proxied locally). Required in production. |
| `VITE_APP_ENV` | No | — | Set to `"development"` (or use Vite dev server, where `import.meta.env.DEV` is automatically `true`) to enable the dev upload path (`POST /api/ingest-direct`). The S3 prod path is used in production builds (`npm run build`) unless `VITE_APP_ENV=development` is set. |
| `VITE_USER_ID` | No | `"analyst"` | User identifier sent in `user_id` field on write requests. |
| `VITE_BACKEND_URL` | No | — | Override backend URL (e.g. `https://api.vv.example.com`). Not needed when using Vite proxy or nginx. |

---

## 3. External dependencies

| Package | Purpose | Version constraint |
|---|---|---|
| `react` | UI framework | `^18.3.0` |
| `react-dom` | DOM rendering | `^18.3.0` |
| `react-router-dom` | Client-side routing | `^6.26.0` |
| `@tanstack/react-table` | Headless table (sorting, pagination) | `^8.20.0` |
| `tailwindcss` | Utility-first CSS | `^3.4.0` |
| `vite` | Build tool + dev server | `^5.4.0` |
| `@vitejs/plugin-react` | React JSX transform | `^4.3.0` |
| `typescript` | Type checking | `^5.5.0` |
| `vitest` | Test runner | `^2.0.0` |
| `jsdom` | DOM environment for Vitest | `^25.0.0` |
| `@testing-library/react` | Component testing | `^16.0.0` |
| `@testing-library/jest-dom` | DOM matchers | `^6.4.0` |
| `@testing-library/user-event` | User interaction simulation | `^14.5.0` |
| `autoprefixer` | CSS vendor prefixing | `^10.4.0` |
| `postcss` | CSS transformer | `^8.4.0` |

---

## 4. CSS class reference

### Badge classes

```css
/* Applied to <span> elements. Base class provides padding, rounded corners, inline-flex */
.badge           /* base: inline-flex items-center px-2 py-0.5 rounded text-xs font-medium */
.badge-pending          /* bg-yellow-100 text-yellow-800  */
.badge-reviewing        /* bg-blue-100   text-blue-800    */
.badge-reported         /* bg-green-100  text-green-800   */
.badge-archived         /* bg-gray-100   text-gray-600    */
.badge-pathogenic       /* bg-red-100    text-red-800     */
.badge-likely-pathogenic /* bg-orange-100 text-orange-800 */
.badge-vus              /* bg-yellow-100 text-yellow-800  */
.badge-likely-benign    /* bg-blue-100   text-blue-800    */
.badge-benign           /* bg-green-100  text-green-800   */
.badge-oncogenic        /* bg-red-100    text-red-800     */
.badge-likely-oncogenic /* bg-orange-100 text-orange-800  */
```

### Button classes

```css
.btn           /* base: inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded border transition-colors */
.btn-primary   /* bg-blue-600 text-white border-blue-600 hover:bg-blue-700    */
.btn-secondary /* bg-white text-gray-700 border-gray-300 hover:bg-gray-50    */
.btn-danger    /* bg-red-600 text-white border-red-600 hover:bg-red-700       */
```

---

## 5. `src/index.css` — complete content

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-gray-50 text-gray-900 antialiased;
  }
}

@layer components {
  .badge {
    @apply inline-flex items-center px-2 py-0.5 rounded text-xs font-medium;
  }
  .badge-pending       { @apply bg-yellow-100 text-yellow-800; }
  .badge-reviewing     { @apply bg-blue-100   text-blue-800;   }
  .badge-reported      { @apply bg-green-100  text-green-800;  }
  .badge-archived      { @apply bg-gray-100   text-gray-600;   }
  .badge-pathogenic    { @apply bg-red-100    text-red-800;    }
  .badge-likely-pathogenic { @apply bg-orange-100 text-orange-800; }
  .badge-vus           { @apply bg-yellow-100 text-yellow-800; }
  .badge-likely-benign { @apply bg-blue-100   text-blue-800;   }
  .badge-benign        { @apply bg-green-100  text-green-800;  }
  .badge-oncogenic     { @apply bg-red-100    text-red-800;    }
  .badge-likely-oncogenic { @apply bg-orange-100 text-orange-800; }

  .btn {
    @apply inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded border transition-colors;
  }
  .btn-primary   { @apply bg-blue-600 text-white border-blue-600 hover:bg-blue-700;  }
  .btn-secondary { @apply bg-white text-gray-700 border-gray-300 hover:bg-gray-50;  }
  .btn-danger    { @apply bg-red-600 text-white border-red-600 hover:bg-red-700;     }
}
```

---

## 6. `postcss.config.ts`

```typescript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

---

## 7. Pipeline config schema (`src/config/pipelines.json`)

```json
{
  "pipelines": {
    "<pipeline_key>": {
      "label": "Human-readable pipeline name",
      "default_filters": {
        "gnomad_af_max": 0.01,
        "consequences": "comma,separated,vep,terms",
        "clinvar_exclude": "Benign,Likely_benign"
      }
    }
  }
}
```

Known pipeline keys (from `backend/config/pipelines.yaml`):

| Key | Label |
|---|---|
| `dragen_germline` | DRAGEN Germline |
| `dragen_somatic` | DRAGEN Somatic |

---

## 8. Workflow state machine

The frontend enforces transitions by rendering only valid buttons:

```
pending   → reviewing, archived
reviewing → reported,  archived
reported  → archived
archived  → (terminal — no buttons rendered)
```

The backend (`PUT /api/workflow/{id}`) independently validates the same state
machine and returns 422 for invalid transitions.

---

## 9. Classification scoring quick reference

### ACGS SNV — Tavtigian point weights

| Strength | Weight |
|---|---|
| `very_strong` | 8 |
| `strong` | 4 |
| `moderate` | 2 |
| `supporting` | 1 |
| `stand_alone` | ∞ (sentinel 999) → Pathogenic |
| `benign_stand_alone` | −∞ (sentinel −999) → Benign |
| `benign_strong` | −4 |
| `benign_moderate` | −2 |
| `benign_supporting` | −1 |

### ACGS SNV — classification thresholds

| Score | Classification |
|---|---|
| ≥ 10 | Pathogenic |
| 6 – 9 | Likely_Pathogenic |
| 0 – 5 | VUS |
| −1 to −5 | Likely_Benign |
| ≤ −6 | Benign |

---

## 10. Useful links

- React 18 docs: https://react.dev
- React Router v6: https://reactrouter.com/en/main
- TanStack Table v8: https://tanstack.com/table/v8
- Vite docs: https://vitejs.dev
- Vitest docs: https://vitest.dev
- Tailwind CSS v3: https://tailwindcss.com/docs
- ACGS-G guidelines: https://www.acgs.uk.com/quality/quality-guidelines/

---

## 11. Glossary

| Term | Definition |
|---|---|
| MRN | Medical Record Number — the `lab_number` field, used as the primary patient identifier displayed in the UI |
| YOB | Year of Birth — **no longer displayed** (dob removed by migration 004; would have been extracted via `formatYearOfBirth(dob)`) |
| VEP | Variant Effect Predictor — Ensembl tool used to annotate VCF files with consequence, gene, HGVS notation etc. |
| HGVSc | HGVS coding DNA nomenclature (e.g. `c.5096G>A`) |
| HGVSp | HGVS protein nomenclature (e.g. `p.Arg1699Gln`) |
| gnomAD AF | Allele frequency from the Genome Aggregation Database |
| REVEL | Rare Exome Variant Ensemble Learner — pathogenicity predictor (0–1, higher = more likely pathogenic) |
| SpliceAI | Deep learning splice site predictor (0–1, ≥ 0.5 = high confidence splice disruption) |
| ACGS SNV | Association for Clinical Genomic Science — SNV germline classification guidelines |
| SVIG-UK | Somatic Variant Interpretation Group UK — somatic variant classification guidelines |
| PVS/PS/PM/PP | Pathogenic evidence categories: Very Strong / Strong / Moderate / Supporting |
| BS/BP | Benign evidence categories: Stand-alone / Strong / Moderate / Supporting |
| Specimen | A biological sample (NGS run); corresponds to the `samples` database table |
| Workflow status | `pending → reviewing → reported → archived` (state machine per specimen) |
