# REFERENCE — variant-viewer backend core (PRs 2–5)

## 1. Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes (or `DB_SECRET_ARN`) | — | Full psycopg2 DSN: `postgresql://user:pass@host:port/dbname` |
| `DB_SECRET_ARN` | Yes (or `DATABASE_URL`) | — | ARN of Secrets Manager secret containing DB credentials JSON |
| `AWS_REGION` | No | `eu-west-2` | AWS region for Secrets Manager client |
| `APP_ENV` | No | — | Set to `production` to enable `sslmode=require` on the DB connection |

**Additional environment variables used by the Lambda function (PR 5):**

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_SECRET_ARN` | Yes | — | Same as ECS task — Lambda resolves DB credentials via Secrets Manager |
| `AWS_REGION` | No | `eu-west-2` | Region for S3 and Secrets Manager clients |
| `APP_ENV` | No | — | Set to `production` to enable `sslmode=require` |

**Secrets Manager secret format** (when `DB_SECRET_ARN` is set):

```json
{
  "username": "variants_admin",
  "password": "...",
  "host": "variant-viewer.xxxx.eu-west-2.rds.amazonaws.com",
  "port": 5432,
  "dbname": "variants"
}
```

Required fields: `username`, `password`, `host`, `dbname`. `port` is optional
(default 5432). `db.py` raises `RuntimeError` if any required field is absent.

---

## 2. External dependencies

| Library | Purpose | Version constraint |
|---|---|---|
| `fastapi` | HTTP framework (used in `main.py`, routes — not in PRs 2–4) | `>=0.115.0` |
| `pydantic` | Data validation and models | `>=2.0.0` |
| `psycopg2-binary` | PostgreSQL driver | `>=2.9.0` |
| `boto3` | AWS SDK — Secrets Manager, S3 (S3 used in PR 5) | `>=1.34.0` |
| `cyvcf2` | htslib-backed VCF/BCF parser — **introduced in PR 5** | `>=0.30.0` |
| `jsonschema` | Manifest JSON Schema validation — **introduced in PR 5** | `>=4.0.0` |
| `pyyaml` | Parse `pipelines.yaml` | `>=6.0.0` |
| `pytest` | Test runner | `>=8.0.0` |
| `pytest-cov` | Coverage reporting | `>=5.0.0` |

PRs 2–4 introduce no new dependencies beyond the existing `requirements.txt`.
PR 5 adds `cyvcf2` (C extension, requires `libz` and `libbz2` at build time)
and updates `requirements.txt` via `pip-compile --generate-hashes`.

**Dockerfile change required in PR 5:**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        zlib1g-dev libbz2-dev liblzma-dev && \
    rm -rf /var/lib/apt/lists/*
```
Add this before the `pip install` step.

---

## 3. Config file schemas

### 3.1 `backend/config/pipelines.yaml`

```yaml
pipelines:
  <key>:                     # pipeline identifier string, e.g. "dragen_germline"
    label: "<display label>"
    header_pattern: "<string>"  # case-insensitive substring of ##source/##pipeline header
    default_filters:
      gnomad_af_max: <float>
      consequences:
        - <consequence_term>   # VEP SO term, e.g. "missense_variant"
      clinvar_exclude:
        - <sig_string>         # e.g. "Benign"
```

Defined pipelines: `dragen_germline`, `dragen_somatic`, `gatk_haplotypecaller`,
`mutect2`, `strelka2`, `unknown`.

### 3.2 `backend/config/acgs-snv-criteria.json`

```json
{
  "version": "ACGS 2024 Best Practice Guidelines",
  "framework": "acgs_snv",
  "criteria": [
    {
      "code": "PVS1",
      "label": "PVS1",
      "category": "functional",
      "direction": "pathogenic",
      "default_strength": "very_strong",
      "permitted_strengths": ["very_strong", "strong", "moderate", "supporting"],
      "adjustable": true,
      "description": "...",
      "pre_computable": true,
      "pre_compute_hint": "..."
    }
  ],
  "combination_rules": [
    {
      "rule": "<rule_id>",
      "codes": ["<CODE1>", "<CODE2>"],
      "message": "Human-readable conflict warning"
    }
  ],
  "thresholds": {
    "pathogenic": 10,
    "likely_pathogenic_min": 6,
    "likely_pathogenic_max": 9,
    "vus_min": 0,
    "vus_max": 5,
    "likely_benign_min": -6,
    "likely_benign_max": -1,
    "benign": -7,
    "minimum_criteria_for_non_vus": 2
  }
}
```

28 criteria total. 3 combination rules: `BS2_BP2_not_together`,
`BA1_overrides_all`, `PP3_BP4_conflict`.

### 3.3 `backend/config/svig-criteria.json`

Same structure as `acgs-snv-criteria.json`. 4 combination rules.
Thresholds identical to ACGS SNV but use `oncogenic`/`likely_oncogenic` labels.

### 3.4 `backend/config/canvig-gene-mtaf.json`

```json
{
  "_comment": "CanVIG-UK gene-specific maximum tolerated allele frequency thresholds",
  "genes": {
    "BRCA1": { "ba1_threshold": 0.001, "bs1_threshold": 0.0003, "disease": "...", "inheritance": "AD" },
    "BRCA2": { ... },
    "TP53":  { ... }
  }
}
```

33 genes. Keys are HGNC official symbols (mixed case). `select_framework()` and
`pre_compute_criteria()` look up genes case-insensitively.

---

### 3.5 `backend/config/manifest-schema.json` (PR 5)

JSON Schema (Draft-07) used by `ingest_sample()` to validate the FHIR R4 Bundle
before calling `parse_manifest()`. The schema enforces:

- `resourceType` is `"Bundle"` and `type` is `"collection"`.
- `entry` array has exactly 3 items, each with a `resource` object.
- Resource types within `entry` must be `"Patient"`, `"Specimen"`, `"Task"`.
- `Patient` must have `identifier` array with at least one item containing
  a non-empty `value` string.
- `Specimen` must have at least one identifier.
- `Task` resource type must be present.

Validation is performed with `jsonschema.validate(raw, _MANIFEST_SCHEMA)` where
`_MANIFEST_SCHEMA` is loaded at module import time from the file path:
```python
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "manifest-schema.json"
```

**Important:** the schema enforces structure; `parse_manifest()` enforces
semantics (e.g. `case-type` extension present and valid). Both validations
run in sequence in `ingest_sample()`.

---

### 3.6 S3 key naming convention (PR 5)

Every VCF upload to the ingest bucket requires a sidecar manifest file in
the same S3 prefix. The Lambda derives the manifest key automatically:

```python
import re
manifest_key = re.sub(r'\.vcf(\.gz)?$', '.manifest.json', vcf_key)
```

| VCF key | Manifest key |
|---|---|
| `runs/2024-11-05/26041S0057.vcf.gz` | `runs/2024-11-05/26041S0057.manifest.json` |
| `runs/2024-11-05/26041S0057.vcf` | `runs/2024-11-05/26041S0057.manifest.json` |

VCF keys that do not end with `.vcf` or `.vcf.gz` (e.g. `.bam`) are rejected
by `ingest_sample()` with `ValueError("Unsupported VCF key format: ...")` before
any S3 download is attempted.

---

## 4. Database schema reference

Full schema is in `migrations/`. Key tables used by PRs 2–5 modules:

| Table | Primary key | Notable columns | FK constraints |
|---|---|---|---|
| `patients` | `id` SERIAL | `lab_number` UNIQUE NOT NULL | — |
| `samples` | `id` SERIAL | `s3_key` UNIQUE NOT NULL, `case_type` CHECK | → `patients(id)` |
| `variants` | `id` SERIAL | `info_json` JSONB | → `samples(id)` |
| `variant_classification` | `id` SERIAL | `framework` CHECK, partial unique on `(variant_id) WHERE deleted_at IS NULL` | → `variants(id)` |
| `classification_criterion` | `id` SERIAL | `strength` CHECK, `pre_computed` BOOL | → `variant_classification(id)` |
| `workflow` | `id` SERIAL | `status` CHECK | → `samples(id)` |
| `audit_log` | `id` SERIAL | Append-only (trigger prevents UPDATE/DELETE) | — |

---

## 5. FHIR R4 Bundle manifest — complete annotated skeleton

Used as sidecar `.manifest.json` for every VCF upload. The manifest parser
(`fhir_manifest.py`) reads this structure.

```json
{
  "resourceType": "Bundle",   // MUST be "Bundle"
  "type": "collection",       // MUST be "collection"
  "entry": [
    {
      "resource": {
        "resourceType": "Patient",
        "identifier": [
          {
            "system": "https://fhir.example-lab.org/Id/lab-number",
            "value": "LAB-2024-00123"     // primary key for upsert
          }
        ],
        "name": [                         // optional
          {
            "family": "Smith",
            "given": ["Jane"]
          }
        ],
        "birthDate": "1978-04-12"         // optional; ISO date YYYY-MM-DD
      }
    },
    {
      "resource": {
        "resourceType": "Specimen",
        "identifier": [
          { "value": "26041S0057" }       // sample name / specimen barcode
        ],
        "extension": [
          {
            "url": "https://example.org/fhir/StructureDefinition/case-type",
            "valueCode": "germline"       // "germline" | "somatic"
          }
        ],
        "type": {                         // optional
          "coding": [
            { "display": "Peripheral blood" }
          ]
        },
        "collection": {                   // optional
          "collectedDateTime": "2024-11-05T09:30:00Z"
        }
      }
    },
    {
      "resource": {
        "resourceType": "Task",
        "status": "completed",
        "identifier": [
          { "value": "RUN-20241105-001" } // optional run ID
        ],
        "code": {
          "text": "dragen_germline"       // pipeline_key (must match pipelines.yaml)
        },
        "input": [
          {
            "type": { "text": "pipeline_version" },
            "valueString": "4.2.4"
          }
        ],
        "output": [
          {
            "type": { "text": "vcf" },
            "valueString": "germline-example.vcf.gz"
          }
        ]
      }
    }
  ]
}
```

**Parser field resolution table:**

| `ParsedManifest` field | FHIR path | Fallback |
|---|---|---|
| `patient.lab_number` | `Patient.identifier[system=NHS_LAB_SYSTEM].value` | First identifier without system |
| `patient.name` | `Patient.name[0].given + family` joined | `None` |
| `patient.dob` | `Patient.birthDate` | `None` |
| `specimen.sample_name` | `Specimen.identifier[0].value` | `"unknown"` |
| `specimen.case_type` | `Specimen.extension[url=CASE_TYPE_EXT].valueCode` | `ValueError` if absent or not `"germline"`/`"somatic"` |
| `specimen.tissue` | `Specimen.type.coding[0].display` or `.text` | `None` |
| `specimen.sequencing_date` | `Specimen.collection.collectedDateTime` split on `T` | `None` |
| `task.pipeline_key` | `Task.code.text` | `None` |
| `task.pipeline_version` | `Task.input[type.text=pipeline_version].valueString` | `None` |
| `task.run_id` | `Task.identifier[0].value` | `None` |
| `task.vcf_filename` | `Task.output[type.text=vcf].valueString` | `None` |

---

## 6. VCF annotation field mapping

The VCF parser extracts fields from two annotation sources.

### VEP CSQ format

VEP header declares the field order:
```
##INFO=<ID=CSQ,...,Format: Allele|Consequence|SYMBOL|Gene|HGVSc|HGVSp|gnomADe_AF|...>
```

| `VcfVariant` field | VEP CSQ field names (tried in order) |
|---|---|
| `gene` | `SYMBOL`, then `Gene` |
| `consequence` | `Consequence` |
| `hgvs_c` | `HGVSc` |
| `hgvs_p` | `HGVSp` |
| `gnomad_af` | `gnomADe_AF` → `gnomAD_AF` → `gnomADg_AF` → `MAX_AF` |
| `clinvar_sig` | `CLIN_SIG` → `ClinVar_CLNSIG` |
| `revel_score` | `REVEL` → `REVEL_score` |
| `spliceai_max` | `max(DS_AG, DS_AL, DS_DG, DS_DL)` from `SpliceAI_pred_DS_*` |

Canonical transcript selection: prefer entry with `CANONICAL=YES`; fall back to
first allele-matching entry; fall back to first entry overall.

### Flat CSQ\_\* fields (East Genomics pipeline)

INFO keys: `CSQ_SYMBOL`, `CSQ_Consequence`, `CSQ_HGVSc`, `CSQ_HGVSp`,
`CSQ_gnomADe_AF`, `CSQ_gnomADg_AF`, `CSQ_REVEL`, `CSQ_ClinVar_CLNSIG`,
`CSQ_SpliceAI_pred_DS_AG/AL/DG/DL`.

---

## 7. Classification scoring reference

### ACGS SNV strength points

| Direction | Strength | Points |
|---|---|---|
| Pathogenic | very\_strong | +8 |
| Pathogenic | strong | +4 |
| Pathogenic | moderate | +2 |
| Pathogenic | supporting | +1 |
| Pathogenic | standalone | +8 (treated as very\_strong) |
| Benign | standalone | −∞ (BA1 sentinel: returns Benign without scoring) |
| Benign | strong | −4 |
| Benign | moderate | −2 |
| Benign | supporting | −1 |

### ACGS SNV classification thresholds

| Score range | Classification |
|---|---|
| ≥ 10 | Pathogenic |
| 6 – 9 | Likely\_Pathogenic |
| 0 – 5 | VUS |
| −6 – −1 | Likely\_Benign |
| ≤ −7 | Benign |

### SVIG-UK sentinel overrides (checked before scoring)

| Criterion | Override |
|---|---|
| O1 (standalone) | Oncogenic (sentinel score 999) |
| B1 (standalone) | Benign (sentinel score −999) |
| B2 (standalone) | Forces VUS (score 0) regardless of other criteria |

### SVIG-UK score thresholds

| Score range | Classification |
|---|---|
| ≥ 10 | Oncogenic |
| 6 – 9 | Likely\_Oncogenic |
| 0 – 5 | VUS |
| −6 – −1 | Likely\_Benign |
| ≤ −7 | Benign |

---

## 8. Pre-compute criteria rules summary

### ACGS SNV (germline)

| Criterion | Trigger | Default strength |
|---|---|---|
| BA1 | gnomAD AF > ba1\_threshold (gene-specific or 0.05) | standalone |
| BS1 | bs1\_threshold < gnomAD AF ≤ ba1\_threshold | strong |
| PM2 | gnomAD AF absent or < 0.0001 | supporting |
| PVS1 | consequence ∈ LOF set | very\_strong |
| PVS1\_RNA | SpliceAI max ≥ 0.8 | very\_strong |
| PP3 | REVEL ≥ 0.7 | supporting |
| BP4 | REVEL ≤ 0.4 | supporting |
| BP7 | consequence contains `synonymous_variant` AND SpliceAI < 0.1 | supporting |
| PS1 | ClinVar contains `pathogenic` (no conflict) | strong |

### SVIG-UK (somatic)

| Criterion | Trigger | Default strength |
|---|---|---|
| B1 | gnomAD AF > 0.01 | standalone |
| O3 | gnomAD AF absent or < 0.0001 | moderate |
| O2 | consequence ∈ LOF set | very\_strong |
| O6 | REVEL ≥ 0.7 | supporting |
| B3 | REVEL ≤ 0.4 OR SpliceAI < 0.1 (first match) | supporting |
| O1 | ClinVar contains `oncogenic` or `pathogenic` (no conflict) | standalone |

### CanVIG gene-specific AF thresholds

All 33 CanVIG genes have `ba1_threshold = 0.001` and `bs1_threshold = 0.0003`
(versus ACGS defaults of 0.05 / 0.01). Check `canvig-gene-mtaf.json` for the
full gene list.

**LOF consequence set** (shared by ACGS PVS1 and SVIG O2):
`frameshift_variant`, `stop_gained`, `stop_lost`, `start_lost`,
`splice_donor_variant`, `splice_acceptor_variant`, `transcript_ablation`.

---

## 9. Golden fixture schema

All four JSON files in `tests/golden/` follow these schemas.

### `classify_acgs_cases.json` / `classify_svig_cases.json`

```json
[
  {
    "description": "<human-readable test name>",
    "criteria": [
      { "criterion_code": "<str>", "applied": true|false, "strength": "<Strength>" }
    ],
    "combination_rules": [
      { "rule": "<str>", "codes": ["<str>"], "message": "<str>" }
    ],
    "expected": {
      "score": <int>,
      "classification": "<Classification>",
      "warnings": ["<str>"]
    }
  }
]
```

### `select_framework_cases.json`

```json
[
  {
    "description": "<str>",
    "case_type": "germline" | "somatic",
    "gene": "<str>" | null,
    "expected": { "framework": "acgs_snv" | "svig", "is_canvig": true | false }
  }
]
```

### `pre_compute_cases.json`

```json
[
  {
    "description": "<str>",
    "variant": {
      "gene": "<str>" | null,
      "consequence": "<str>" | null,
      "gnomad_af": <float> | null,
      "revel_score": <float> | null,
      "spliceai_max": <float> | null,
      "clinvar_sig": "<str>" | null
    },
    "case_type": "germline" | "somatic",
    "expected_codes": ["<criterion_code>"],
    "expected_strengths": { "<criterion_code>": "<Strength>" }
  }
]
```

---

## 10. Useful links

| Resource | URL |
|---|---|
| ACGS 2024 Best Practice Guidelines | https://www.acgs.uk.com/quality/best-practice-guidelines/ |
| SVIG-UK framework | Internal document; see `config/svig-criteria.json` |
| CanVIG-UK | https://www.canvig.org.uk/ |
| VEP documentation | https://www.ensembl.org/info/docs/tools/vep/ |
| psycopg2 connection pool | https://www.psycopg.org/docs/pool.html |
| FHIR R4 Bundle | https://www.hl7.org/fhir/bundle.html |
| AWS Secrets Manager Python SDK | https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager.html |
| Pydantic v2 docs | https://docs.pydantic.dev/latest/ |

---

## 11. Glossary

| Term | Definition |
|---|---|
| ACGS SNV | Association for Clinical Genomic Science guidelines for sequence variant interpretation in germline settings |
| SVIG-UK | Somatic Variant Interpretation Guidelines — UK framework for classifying somatic variants |
| CanVIG | Cancer Variant Interpretation Group UK; provides gene-specific AF thresholds |
| BA1 | Benign Allele 1 — standalone benign criterion: AF > threshold → Benign regardless of other evidence |
| CSQ | VEP consequence annotation field in VCF INFO column |
| Framework | The variant classification ruleset in use: `acgs_snv` (germline) or `svig` (somatic) |
| Golden fixture | Pre-computed expected input/output pairs used to verify the Python port matches TypeScript behaviour |
| LOF | Loss-of-function variant consequence (frameshift, stop\_gained, canonical splice, etc.) |
| MTAF | Maximum Tolerated Allele Frequency — gene-specific BA1/BS1 thresholds from CanVIG |
| Sentinel score | Placeholder integer value (999 or −999) returned when a standalone criterion overrides scoring |
| Tavtigian scoring | Point-based variant classification framework described in Tavtigian et al. 2020; basis of both ACGS and SVIG frameworks |
| VUS | Variant of Uncertain Significance |
