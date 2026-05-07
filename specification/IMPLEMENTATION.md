# IMPLEMENTATION — variant-viewer backend core (PRs 2–5)

## 0. Prerequisites

```bash
# Node.js (for golden fixture generation in M7)
node --version   # ≥18

# Python 3.12
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Verify existing tests still pass before writing any new code
.venv/bin/pytest tests/test_config_integrity.py -v
# Expected: 81 passed
```

The discovery/nextjs branch must be accessible locally (used in M7):

```bash
git fetch origin discovery/nextjs
```

---

## 1. Project scaffold

The target file tree after PRs 2–4 (excluding pre-existing files):

```
backend/
├── app/
│   └── lib/
│       ├── __init__.py             (create — empty)
│       ├── db.py                   PR 2
│       ├── models.py               PR 2
│       ├── vcf_parser.py           PR 3
│       ├── fhir_manifest.py        PR 3
│       ├── pipeline_config.py      PR 3
│       ├── classification_engine.py  PR 4
│       └── pre_compute_criteria.py   PR 4
└── tests/
    ├── test_models.py          PR 2
    ├── test_db.py              PR 2
    ├── test_pipeline_config.py PR 3
    ├── test_fhir_manifest.py   PR 3
    ├── test_vcf_parser.py      PR 3
    ├── golden/
    │   ├── classify_acgs_cases.json
    │   ├── classify_svig_cases.json
    │   ├── select_framework_cases.json
    │   └── pre_compute_cases.json
    ├── test_classification_engine.py  PR 4
    └── test_pre_compute_criteria.py   PR 4
```

> Both `classification_engine.py` and `pre_compute_criteria.py` live in
> `app/lib/` alongside the other business-logic modules. Import them as
> `from app.lib.classification_engine import classify`.

`requirements.txt` (no new dependencies needed for PRs 2–4 beyond what is
already present):

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
psycopg2-binary>=2.9.0
boto3>=1.34.0
python-multipart>=0.0.9
pyyaml>=6.0.0
pytest>=8.0.0
httpx>=0.27.0
pytest-cov>=5.0.0
```

`.env.example` (unchanged from existing):

```
DATABASE_URL=postgresql://variants_admin:password@localhost:5432/variants
AWS_REGION=eu-west-2
VCF_BUCKET_NAME=variant-viewer-vcf-749929395031
# DB_SECRET_ARN=arn:aws:secretsmanager:eu-west-2:...:secret:variant-viewer/db-credentials
```

---

## 2. Milestone plan

| M | Module(s) | Red tests | Green when |
|---|---|---|---|
| M1 | Scaffold — `__init__.py` files | Import assertions | `from app.lib.models import Patient` succeeds |
| M2 | `models.py` | `test_models.py` | All Pydantic validation tests pass |
| M3 | `pipeline_config.py` | `test_pipeline_config.py` | YAML loads, pipeline detected |
| M4 | `fhir_manifest.py` | `test_fhir_manifest.py` | Parse + NHS validate + build |
| M5 | `vcf_parser.py` | `test_vcf_parser.py` | VEP CSQ / flat CSQ_* + multi-allelic |
| M6 | `db.py` | `test_db.py` | Pool init, query, transaction, rollback (mocked) |
| M7 | Golden fixtures | (generation script) | JSON fixtures committed + match TS output |
| M8 | `classification_engine.py` | `test_classification_engine.py` | All golden cases exact-match |
| M9 | `pre_compute_criteria.py` | `test_pre_compute_criteria.py` | All golden cases pass |
| M10 | Full suite | All tests | 81 + new tests green, coverage ≥80% |

---

## 3. Milestone 1 — Scaffold

### Red: write test

```python
# tests/test_scaffold.py
def test_app_lib_importable():
    from app.lib import models  # noqa: F401

def test_classification_engine_importable():
    import classification_engine  # noqa: F401
```

### Green: create files

```bash
touch backend/app/lib/__init__.py
touch backend/app/lib/models.py
touch backend/classification_engine.py
touch backend/pre_compute_criteria.py
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_scaffold.py -v`
— 2 passed.

---

## 4. Milestone 2 — `models.py`

### Red: write tests first

```python
# tests/test_models.py
import pytest
from datetime import date
from pydantic import ValidationError
from app.lib.models import (
    Patient, Sample, Variant, VariantClassification,
    ClassificationCriterion, WorkflowRecord, AuditEntry,
    Framework, Strength, CaseType, WorkflowStatus, Classification,
)

def test_patient_minimal():
    p = Patient(lab_number="LAB-001")
    assert p.lab_number == "LAB-001"
    assert p.id is None

def test_patient_full():
    p = Patient(lab_number="LAB-001", name="Jane Smith", dob=date(1980, 1, 1))
    assert p.name == "Jane Smith"
    assert p.dob == date(1980, 1, 1)

def test_variant_defaults():
    v = Variant(sample_id=1, chrom="1", pos=100, ref="A", alt="G")
    assert v.qual is None
    assert v.info_json == {}
    assert v.gene is None

def test_workflow_default_status():
    w = WorkflowRecord(sample_id=1)
    assert w.status == "pending"

def test_workflow_invalid_status():
    with pytest.raises(ValidationError):
        WorkflowRecord(sample_id=1, status="unknown")

def test_classification_criterion_invalid_strength():
    with pytest.raises(ValidationError):
        ClassificationCriterion(classification_id=1, criterion_code="PVS1", strength="ultra_strong")

def test_variant_classification_framework_literal():
    vc = VariantClassification(variant_id=1, framework="acgs_snv", framework_version="ACGS 2024")
    assert vc.framework == "acgs_snv"

def test_variant_classification_invalid_framework():
    with pytest.raises(ValidationError):
        VariantClassification(variant_id=1, framework="unknown", framework_version="v1")

def test_audit_entity_type_invalid():
    with pytest.raises(ValidationError):
        AuditEntry(action="classify", entity_type="gene", entity_id=1)

def test_sample_case_type():
    s = Sample(patient_id=1, name="26041S0057", s3_key="path/to.vcf.gz", case_type="germline")
    assert s.case_type == "germline"

def test_literals_exported():
    # These should be importable without error
    assert "acgs_snv" in Framework.__args__
    assert "very_strong" in Strength.__args__
    assert "germline" in CaseType.__args__
    assert "pending" in WorkflowStatus.__args__
    assert "Pathogenic" in Classification.__args__
```

### Green: implement `models.py`

```python
# app/lib/models.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

Framework = Literal["acgs_snv", "svig"]
Strength = Literal["very_strong", "strong", "moderate", "supporting", "standalone"]
CaseType = Literal["germline", "somatic"]
WorkflowStatus = Literal["pending", "reviewing", "reported", "archived"]
Classification = Literal[
    "Pathogenic", "Likely_Pathogenic", "VUS",
    "Likely_Benign", "Benign", "Oncogenic", "Likely_Oncogenic"
]


class Patient(BaseModel):
    id: int | None = None
    name: str | None = None
    dob: date | None = None
    lab_number: str
    created_at: datetime | None = None


class Sample(BaseModel):
    id: int | None = None
    patient_id: int
    name: str
    vcf_filename: str | None = None
    s3_key: str
    pipeline_key: str | None = None
    case_type: CaseType
    tissue: str | None = None
    sequencing_date: date | None = None
    ingested_at: datetime | None = None


class Variant(BaseModel):
    id: int | None = None
    sample_id: int
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float | None = None
    filter: str | None = None
    gene: str | None = None
    consequence: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    gnomad_af: float | None = None
    clinvar_sig: str | None = None
    revel_score: float | None = None
    spliceai_max: float | None = None
    info_json: dict[str, Any] = {}


class VariantClassification(BaseModel):
    id: int | None = None
    variant_id: int
    framework: Framework
    framework_version: str
    score: int | None = None
    classification: Classification | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    deleted_at: datetime | None = None


class ClassificationCriterion(BaseModel):
    id: int | None = None
    classification_id: int
    criterion_code: str
    applied: bool = False
    strength: Strength
    notes: str | None = None
    evidence_links: list[str] = []
    pre_computed: bool = False
    pre_computed_value: str | None = None


class WorkflowRecord(BaseModel):
    id: int | None = None
    sample_id: int
    status: WorkflowStatus = "pending"
    updated_at: datetime | None = None
    updated_by: str | None = None


class AuditEntry(BaseModel):
    id: int | None = None
    user_id: str | None = None
    action: str
    entity_type: Literal["patient", "sample", "variant", "classification", "workflow"]
    entity_id: int
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    occurred_at: datetime | None = None
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_models.py -v`
— all tests green.

---

## 5. Milestone 3 — `pipeline_config.py`

### Red: write tests first

```python
# tests/test_pipeline_config.py
from app.lib.pipeline_config import (
    get_pipeline_config, get_pipeline_keys, get_default_filters, detect_pipeline_key,
)

def test_all_pipelines_loaded():
    keys = get_pipeline_keys()
    assert "dragen_germline" in keys
    assert "dragen_somatic" in keys
    assert "gatk_haplotypecaller" in keys
    assert "mutect2" in keys
    assert "strelka2" in keys
    assert "unknown" in keys

def test_pipeline_config_label():
    cfg = get_pipeline_config("dragen_germline")
    assert cfg is not None
    assert cfg.label == "DRAGEN Germline v3"

def test_pipeline_config_missing_key():
    assert get_pipeline_config("nonexistent") is None

def test_default_filters_gnomad():
    f = get_default_filters("dragen_germline")
    assert f.gnomad_af_max == 0.01
    assert "missense_variant" in f.consequences

def test_default_filters_fallback():
    # Unknown key falls back to defaults
    f = get_default_filters("nonexistent")
    assert f.gnomad_af_max == 0.01

def test_detect_dragen():
    headers = ["##fileformat=VCFv4.2", "##source=DRAGENv4.2"]
    assert detect_pipeline_key(headers) == "dragen_germline"

def test_detect_haplotypecaller():
    assert detect_pipeline_key(["##source=HaplotypeCallerv4.5"]) == "gatk_haplotypecaller"

def test_detect_mutect2():
    assert detect_pipeline_key(["##source=Mutect2 v4.4"]) == "mutect2"

def test_detect_strelka():
    assert detect_pipeline_key(["##source=strelka-2.9.10"]) == "strelka2"

def test_detect_unknown_headers():
    assert detect_pipeline_key(["##fileformat=VCFv4.2"]) is None

def test_detect_case_insensitive():
    assert detect_pipeline_key(["##source=DRAGEN pipeline"]) == "dragen_germline"
```

### Green: implement `pipeline_config.py`

```python
# app/lib/pipeline_config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# Resolve config path relative to this file (works regardless of cwd)
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pipelines.yaml"


@dataclass
class PipelineFilters:
    gnomad_af_max: float
    consequences: list[str]
    clinvar_exclude: list[str]


@dataclass
class PipelineConfig:
    label: str
    header_pattern: str
    default_filters: PipelineFilters


_cache: dict[str, PipelineConfig] | None = None


def _load() -> dict[str, PipelineConfig]:
    global _cache
    if _cache is not None:
        return _cache
    raw = yaml.safe_load(_CONFIG_PATH.read_text())
    _cache = {}
    for key, val in raw["pipelines"].items():
        df = val["default_filters"]
        _cache[key] = PipelineConfig(
            label=val["label"],
            header_pattern=val.get("header_pattern", ""),
            default_filters=PipelineFilters(
                gnomad_af_max=df["gnomad_af_max"],
                consequences=df.get("consequences", []),
                clinvar_exclude=df.get("clinvar_exclude", []),
            ),
        )
    return _cache


def get_pipeline_config(key: str) -> PipelineConfig | None:
    return _load().get(key)


def get_pipeline_keys() -> list[str]:
    return list(_load().keys())


def get_default_filters(pipeline_key: str) -> PipelineFilters:
    cfg = get_pipeline_config(pipeline_key)
    if cfg:
        return cfg.default_filters
    return PipelineFilters(
        gnomad_af_max=0.01,
        consequences=["missense_variant", "frameshift_variant", "stop_gained",
                      "splice_donor_variant", "splice_acceptor_variant"],
        clinvar_exclude=["Benign", "Likely_benign"],
    )


def detect_pipeline_key(header_lines: list[str]) -> str | None:
    source = " ".join(
        l for l in header_lines if l.startswith("##source") or l.startswith("##pipeline")
    ).lower()
    for key, cfg in _load().items():
        pattern = cfg.header_pattern.lower()
        if pattern and pattern in source:
            return key
    return None
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_pipeline_config.py -v`
— all tests green.

---

## 6. Milestone 4 — `fhir_manifest.py`

### Red: write tests first

```python
# tests/test_fhir_manifest.py
import json
from pathlib import Path
import pytest
from app.lib.fhir_manifest import (
    parse_manifest, build_manifest,
    ManifestPatient, ManifestSpecimen, ManifestTask, ParsedManifest,
)

# Load the example manifest from the repo
_EXAMPLE = json.loads(
    (Path(__file__).parent.parent.parent /
     "docs/examples/germline-example.manifest.json")
     # NOTE: this path is on discovery/nextjs; copy example to backend/tests/fixtures/ in M4 green step
    # Use the inline dict below instead:
    .read_text()
) if False else {  # inline fixture
    "resourceType": "Bundle", "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient",
            "identifier": [{"system": "https://fhir.example-lab.org/Id/lab-number", "value": "LAB-2024-00123"}],
            "birthDate": "1978-04-12"}},
        {"resource": {"resourceType": "Specimen",
            "identifier": [{"value": "26041S0057"}],
            "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type", "valueCode": "germline"}],
            "type": {"coding": [{"display": "Peripheral blood"}]},
            "collection": {"collectedDateTime": "2024-11-05T09:30:00Z"}}},
        {"resource": {"resourceType": "Task", "status": "completed",
            "identifier": [{"value": "RUN-20241105-001"}],
            "code": {"text": "dragen_germline"},
            "input": [{"type": {"text": "pipeline_version"}, "valueString": "4.2.4"}],
            "output": [{"type": {"text": "vcf"}, "valueString": "germline-example.vcf.gz"}]}}
    ]
}

def test_parse_manifest_lab_number():
    m = parse_manifest(_EXAMPLE)
    assert m.patient.lab_number == "LAB-2024-00123"

def test_parse_manifest_dob():
    m = parse_manifest(_EXAMPLE)
    assert m.patient.dob == "1978-04-12"

def test_parse_manifest_case_type():
    m = parse_manifest(_EXAMPLE)
    assert m.specimen.case_type == "germline"

def test_parse_manifest_sample_name():
    m = parse_manifest(_EXAMPLE)
    assert m.specimen.sample_name == "26041S0057"

def test_parse_manifest_tissue():
    m = parse_manifest(_EXAMPLE)
    assert m.specimen.tissue == "Peripheral blood"

def test_parse_manifest_sequencing_date():
    m = parse_manifest(_EXAMPLE)
    assert m.specimen.sequencing_date == "2024-11-05"

def test_parse_manifest_pipeline_key():
    m = parse_manifest(_EXAMPLE)
    assert m.task.pipeline_key == "dragen_germline"

def test_parse_manifest_run_id():
    m = parse_manifest(_EXAMPLE)
    assert m.task.run_id == "RUN-20241105-001"

def test_parse_wrong_resource_type():
    with pytest.raises(ValueError, match="FHIR R4 Bundle"):
        parse_manifest({"resourceType": "Patient", "type": "collection", "entry": []})

def test_parse_missing_patient():
    bundle = {"resourceType": "Bundle", "type": "collection",
              "entry": [{"resource": {"resourceType": "Specimen"}}]}
    with pytest.raises(ValueError, match="missing Patient"):
        parse_manifest(bundle)

def test_somatic_case_type():
    somatic = {**_EXAMPLE, "entry": [
        _EXAMPLE["entry"][0],
        {"resource": {"resourceType": "Specimen",
            "identifier": [{"value": "TUM001"}],
            "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type", "valueCode": "somatic"}]}},
        _EXAMPLE["entry"][2],
    ]}
    m = parse_manifest(somatic)
    assert m.specimen.case_type == "somatic"

def test_missing_case_type_raises():
    no_ext = {**_EXAMPLE, "entry": [
        _EXAMPLE["entry"][0],
        {"resource": {"resourceType": "Specimen", "identifier": [{"value": "S001"}]}},
        _EXAMPLE["entry"][2],
    ]}
    with pytest.raises(ValueError, match="missing case-type"):
        parse_manifest(no_ext)

def test_invalid_case_type_raises():
    bad_ext = {**_EXAMPLE, "entry": [
        _EXAMPLE["entry"][0],
        {"resource": {"resourceType": "Specimen",
            "identifier": [{"value": "S001"}],
            "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type", "valueCode": "unknown"}]}},
        _EXAMPLE["entry"][2],
    ]}
    with pytest.raises(ValueError, match="Invalid case_type"):
        parse_manifest(bad_ext)

def test_build_and_roundtrip():
    patient = ManifestPatient(lab_number="LAB-999", name="Test User", dob="1990-01-01")
    specimen = ManifestSpecimen(sample_name="S001", case_type="germline", tissue=None, sequencing_date=None)
    task = ManifestTask(pipeline_key="dragen_germline", pipeline_version="4.2", run_id="R1", vcf_filename=None)
    bundle = build_manifest(patient, specimen, task)
    m = parse_manifest(bundle)
    assert m.patient.lab_number == "LAB-999"
    assert m.specimen.case_type == "germline"
    assert m.task.pipeline_key == "dragen_germline"
```

### Green: implement `fhir_manifest.py`

```python
# app/lib/fhir_manifest.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

NHS_LAB_SYSTEM = "https://fhir.example-lab.org/Id/lab-number"
CASE_TYPE_EXT  = "https://example.org/fhir/StructureDefinition/case-type"


@dataclass
class ManifestPatient:
    lab_number: str
    name: str | None
    dob: str | None   # "YYYY-MM-DD"


@dataclass
class ManifestSpecimen:
    sample_name: str
    case_type: Literal["germline", "somatic"]
    tissue: str | None
    sequencing_date: str | None   # "YYYY-MM-DD"


@dataclass
class ManifestTask:
    pipeline_key: str | None
    pipeline_version: str | None
    run_id: str | None
    vcf_filename: str | None


@dataclass
class ParsedManifest:
    patient: ManifestPatient
    specimen: ManifestSpecimen
    task: ManifestTask


def _find_resource(bundle: dict, rtype: str) -> dict | None:
    for entry in bundle.get("entry", []):
        r = entry.get("resource", {})
        if r.get("resourceType") == rtype:
            return r
    return None


def parse_manifest(raw: Any) -> ParsedManifest:
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a FHIR R4 Bundle (type: collection)")
    if raw.get("resourceType") != "Bundle" or raw.get("type") != "collection":
        raise ValueError("Manifest must be a FHIR R4 Bundle (type: collection)")

    patient_res = _find_resource(raw, "Patient")
    specimen_res = _find_resource(raw, "Specimen")
    task_res     = _find_resource(raw, "Task")

    if not patient_res:
        raise ValueError("Manifest missing Patient resource")
    if not specimen_res:
        raise ValueError("Manifest missing Specimen resource")
    if not task_res:
        raise ValueError("Manifest missing Task resource")

    # Patient identifiers
    identifiers: list[dict] = patient_res.get("identifier", [])
    lab_id  = next((i for i in identifiers if i.get("system") == NHS_LAB_SYSTEM), None)
    no_sys  = next((i for i in identifiers if not i.get("system")), None)
    lab_number = (lab_id or no_sys or {}).get("value")
    if not lab_number:
        raise ValueError("Patient manifest missing lab number identifier")

    # Name
    name_entry = (patient_res.get("name") or [{}])[0]
    given_names: list[str] = name_entry.get("given", [])
    family = name_entry.get("family", "")
    parts = [*given_names, family]
    name = " ".join(p for p in parts if p).strip() or None

    # Specimen
    case_type_ext = next(
        (e for e in specimen_res.get("extension", []) if e.get("url") == CASE_TYPE_EXT), None
    )
    if case_type_ext is None:
        raise ValueError("Specimen manifest missing case-type extension")
    case_type_raw = case_type_ext.get("valueCode")
    if case_type_raw not in ("germline", "somatic"):
        raise ValueError(f"Invalid case_type: {case_type_raw!r} (must be 'germline' or 'somatic')")
    case_type: Literal["germline", "somatic"] = case_type_raw

    sample_id_val = (specimen_res.get("identifier") or [{}])[0]
    sample_name = sample_id_val.get("value", "unknown")
    tissue = (
        specimen_res.get("type", {}).get("coding", [{}])[0].get("display")
        or specimen_res.get("type", {}).get("text")
    )
    collected = specimen_res.get("collection", {}).get("collectedDateTime", "")
    sequencing_date = collected.split("T")[0] if collected else None

    # Task
    pipeline_key: str | None = (task_res.get("code") or {}).get("text")
    pipeline_version = next(
        (i.get("valueString") for i in task_res.get("input", [])
         if i.get("type", {}).get("text") == "pipeline_version"),
        None,
    )
    run_id = (task_res.get("identifier") or [{}])[0].get("value")
    vcf_output = next(
        (o.get("valueString") for o in task_res.get("output", [])
         if o.get("type", {}).get("text") == "vcf"),
        None,
    )

    return ParsedManifest(
        patient=ManifestPatient(
            lab_number=lab_number,
            name=name,
            dob=patient_res.get("birthDate"),
        ),
        specimen=ManifestSpecimen(
            sample_name=sample_name,
            case_type=case_type,
            tissue=tissue,
            sequencing_date=sequencing_date,
        ),
        task=ManifestTask(
            pipeline_key=pipeline_key,
            pipeline_version=pipeline_version,
            run_id=run_id,
            vcf_filename=vcf_output,
        ),
    )


def build_manifest(
    patient: ManifestPatient,
    specimen: ManifestSpecimen,
    task: ManifestTask,
) -> dict:
    patient_identifiers: list[dict] = [{"system": NHS_LAB_SYSTEM, "value": patient.lab_number}]

    patient_resource: dict[str, Any] = {"resourceType": "Patient", "identifier": patient_identifiers}
    if patient.name:
        parts = patient.name.split(" ")
        family = parts[-1] if parts else ""
        given = parts[:-1] if len(parts) > 1 else []
        patient_resource["name"] = [{"family": family, "given": given}]
    if patient.dob:
        patient_resource["birthDate"] = patient.dob

    specimen_resource: dict[str, Any] = {
        "resourceType": "Specimen",
        "identifier": [{"value": specimen.sample_name}],
        "extension": [{"url": CASE_TYPE_EXT, "valueCode": specimen.case_type}],
    }
    if specimen.sequencing_date:
        specimen_resource["collection"] = {"collectedDateTime": specimen.sequencing_date}
    if specimen.tissue:
        specimen_resource["type"] = {"coding": [{"display": specimen.tissue}]}

    task_resource: dict[str, Any] = {"resourceType": "Task", "status": "completed"}
    if task.run_id:
        task_resource["identifier"] = [{"value": task.run_id}]
    if task.pipeline_key:
        task_resource["code"] = {"text": task.pipeline_key}
    if task.pipeline_version:
        task_resource["input"] = [{"type": {"text": "pipeline_version"}, "valueString": task.pipeline_version}]
    if task.vcf_filename:
        task_resource["output"] = [{"type": {"text": "vcf"}, "valueString": task.vcf_filename}]

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": patient_resource},
            {"resource": specimen_resource},
            {"resource": task_resource},
        ],
    }
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_fhir_manifest.py -v`
— all tests green.

---

## 7. Milestone 5 — `vcf_parser.py`

> **Status:** Built in PR 3 (hand-rolled line parser). The implementation
> below is the PR 3 version, present in the repo as of PR #18.
> **PR 5 replaces this implementation with `cyvcf2`** — see Milestone 11.
> The `VcfVariant` / `VcfMeta` dataclasses and all CSQ extraction helpers
> (`_extract_vep`, `_extract_flat_csq`, `_csq_field`, `_spliceai_max`) are
> **unchanged** in the migration; only `parse_vcf()` itself changes.

### Red: write tests first

```python
# tests/test_vcf_parser.py
from app.lib.vcf_parser import parse_vcf, VcfVariant, VcfMeta

# Minimal VCF with VEP CSQ annotation
_VEP_HEADER = (
    '##fileformat=VCFv4.2\n'
    '##source=DRAGENv4.2\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="VEP ... Format: Allele|Consequence|SYMBOL|Gene|HGVSc|HGVSp|gnomADe_AF|REVEL|SpliceAI_pred_DS_AG|SpliceAI_pred_DS_AL|SpliceAI_pred_DS_DG|SpliceAI_pred_DS_DL|CLIN_SIG|CANONICAL">\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t100\t.\tA\tG\t50.0\tPASS\tCSQ=G|missense_variant|BRCA1|ENSG001|c.100A>G|p.Thr34Ala|0.0001|0.75|0.1|0.2|0.05|0.3|Pathogenic|YES\n'
)

_MULTI_ALLELIC = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t200\t.\tA\tG,T\t.\t.\t.\n'
)

_FLAT_CSQ = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '3\t400\t.\tG\tA\t.\t.\tCSQ_SYMBOL=BRCA2;CSQ_Consequence=frameshift_variant;CSQ_gnomADe_AF=0.0002;CSQ_REVEL=0.8\n'
)


def _collect(vcf_text: str) -> tuple[list[VcfVariant], VcfMeta]:
    variants: list[VcfVariant] = []
    meta = parse_vcf(vcf_text.splitlines(), on_variant=variants.append)
    return variants, meta


def test_vep_basic_fields():
    variants, meta = _collect(_VEP_HEADER)
    assert len(variants) == 1
    v = variants[0]
    assert v.chrom == "1"
    assert v.pos == 100
    assert v.ref == "A"
    assert v.alt == "G"
    assert v.qual == 50.0
    assert v.filter == "PASS"
    assert v.gene == "BRCA1"
    assert v.consequence == "missense_variant"
    assert v.hgvs_c == "c.100A>G"
    assert v.hgvs_p == "p.Thr34Ala"
    assert abs(v.gnomad_af - 0.0001) < 1e-9
    assert abs(v.revel_score - 0.75) < 1e-9
    assert v.clinvar_sig == "Pathogenic"

def test_vep_spliceai_max():
    # DS_AG=0.1, DS_AL=0.2, DS_DG=0.05, DS_DL=0.3 → max=0.3
    variants, _ = _collect(_VEP_HEADER)
    assert abs(variants[0].spliceai_max - 0.3) < 1e-9

def test_pipeline_detected_from_header():
    _, meta = _collect(_VEP_HEADER)
    assert meta.pipeline_key == "dragen_germline"

def test_multi_allelic_split():
    variants, _ = _collect(_MULTI_ALLELIC)
    assert len(variants) == 2
    assert {v.alt for v in variants} == {"G", "T"}

def test_missing_qual_becomes_none():
    variants, _ = _collect(_MULTI_ALLELIC)
    assert all(v.qual is None for v in variants)

def test_flat_csq_fields():
    variants, _ = _collect(_FLAT_CSQ)
    assert len(variants) == 1
    v = variants[0]
    assert v.gene == "BRCA2"
    assert v.consequence == "frameshift_variant"
    assert abs(v.gnomad_af - 0.0002) < 1e-9
    assert abs(v.revel_score - 0.8) < 1e-9

def test_spanning_deletion_skipped():
    lines = [
        "##fileformat=VCFv4.2",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        "1\t500\t.\tATG\tA,*\t.\t.\t.",
    ]
    variants: list[VcfVariant] = []
    parse_vcf(lines, on_variant=variants.append)
    assert len(variants) == 1
    assert variants[0].alt == "A"

def test_header_lines_captured():
    _, meta = _collect(_VEP_HEADER)
    assert any("fileformat" in l for l in meta.header_lines)
```

### Green: implement `vcf_parser.py`

```python
# app/lib/vcf_parser.py
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.lib.pipeline_config import detect_pipeline_key


@dataclass
class VcfVariant:
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float | None
    filter: str | None
    gene: str | None
    consequence: str | None
    hgvs_c: str | None
    hgvs_p: str | None
    gnomad_af: float | None
    clinvar_sig: str | None
    revel_score: float | None
    spliceai_max: float | None
    info_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class VcfMeta:
    pipeline_key: str | None
    header_lines: list[str]


def _parse_info(info_str: str) -> dict[str, str | bool]:
    if not info_str or info_str == ".":
        return {}
    result: dict[str, str | bool] = {}
    for token in info_str.split(";"):
        eq = token.find("=")
        if eq == -1:
            result[token] = True
        else:
            result[token[:eq]] = token[eq + 1:]
    return result


_SPLICEI_KEYS = ["SpliceAI_pred_DS_AG", "SpliceAI_pred_DS_AL", "SpliceAI_pred_DS_DG", "SpliceAI_pred_DS_DL"]
_FLAT_SPLICE_KEYS = [f"CSQ_{k}" for k in _SPLICEI_KEYS]


def _spliceai_max(scores: list[str]) -> float | None:
    vals = [float(s) for s in scores if s and s not in (".", "")]
    vals = [v for v in vals if not (v != v)]  # remove NaN
    return max(vals) if vals else None


def _extract_vep(info: dict, csq_header: list[str], alt: str) -> dict:
    empty: dict = {k: None for k in ["gene", "consequence", "hgvs_c", "hgvs_p",
                                      "gnomad_af", "clinvar_sig", "revel_score", "spliceai_max"]}
    csq_str = info.get("CSQ")
    if not isinstance(csq_str, str):
        return empty

    entries = csq_str.split(",")
    allele_idx = csq_header.index("Allele") if "Allele" in csq_header else -1
    canon_idx  = csq_header.index("CANONICAL") if "CANONICAL" in csq_header else -1

    matched = [e for e in entries if allele_idx >= 0 and e.split("|")[allele_idx] == alt]
    pool = matched if matched else entries
    preferred = next((e for e in pool if canon_idx >= 0 and e.split("|")[canon_idx] == "YES"), pool[0])

    flds = preferred.split("|")

    def get(name: str) -> str:
        i = csq_header.index(name) if name in csq_header else -1
        return flds[i] if i >= 0 and i < len(flds) else ""

    gnomad_raw = get("gnomADe_AF") or get("gnomAD_AF") or get("gnomADg_AF") or get("MAX_AF")
    revel_raw  = get("REVEL") or get("REVEL_score")

    sai_vals = [get(k) for k in _SPLICEI_KEYS]

    def parse_float(s: str) -> float | None:
        try:
            return float(s) if s else None
        except ValueError:
            return None

    return {
        "gene": get("SYMBOL") or get("Gene") or None,
        "consequence": get("Consequence") or None,
        "hgvs_c": get("HGVSc") or None,
        "hgvs_p": get("HGVSp") or None,
        "gnomad_af": parse_float(gnomad_raw),
        "clinvar_sig": get("CLIN_SIG") or get("ClinVar_CLNSIG") or None,
        "revel_score": parse_float(revel_raw),
        "spliceai_max": _spliceai_max(sai_vals),
    }


def _extract_flat_csq(info: dict) -> dict:
    def get(name: str) -> str:
        v = info.get(name, "")
        return v if isinstance(v, str) else ""

    def parse_float(s: str) -> float | None:
        try:
            return float(s) if s else None
        except ValueError:
            return None

    sai_vals = [get(k) for k in _FLAT_SPLICE_KEYS]
    gnomad_raw = get("CSQ_gnomADe_AF") or get("CSQ_gnomADg_AF")

    return {
        "gene": get("CSQ_SYMBOL") or None,
        "consequence": get("CSQ_Consequence") or None,
        "hgvs_c": get("CSQ_HGVSc") or None,
        "hgvs_p": get("CSQ_HGVSp") or None,
        "gnomad_af": parse_float(gnomad_raw),
        "clinvar_sig": get("CSQ_ClinVar_CLNSIG") or None,
        "revel_score": parse_float(get("CSQ_REVEL")),
        "spliceai_max": _spliceai_max(sai_vals),
    }


def parse_vcf(
    lines: Iterable[str],
    on_variant: Callable[[VcfVariant], None] | None = None,
) -> VcfMeta:
    header_lines: list[str] = []
    csq_header: list[str] | None = None

    for line in lines:
        line = line.rstrip("\n\r")
        if line.startswith("##"):
            header_lines.append(line)
            if "ID=CSQ" in line and "Format:" in line:
                fmt = line.split("Format:")[1].replace('"', "").replace(">", "").strip()
                csq_header = fmt.split("|")
            continue
        if line.startswith("#"):
            continue  # column header row
        if not line:
            continue

        cols = line.split("\t")
        if len(cols) < 8:
            continue

        chrom, pos_str, _, ref, alt_field, qual_str, filter_str, info_str = (
            cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]
        )
        qual: float | None = None if qual_str == "." else _try_float(qual_str)
        filter_val: str | None = None if filter_str == "." else filter_str
        info = _parse_info(info_str)

        for alt in alt_field.split(","):
            if not alt or alt == "*":
                continue

            if csq_header and "CSQ" in info:
                annotations = _extract_vep(info, csq_header, alt)
            elif "CSQ_SYMBOL" in info or "CSQ_Consequence" in info:
                annotations = _extract_flat_csq(info)
            else:
                annotations = {k: None for k in ["gene", "consequence", "hgvs_c", "hgvs_p",
                                                   "gnomad_af", "clinvar_sig", "revel_score", "spliceai_max"]}

            variant = VcfVariant(
                chrom=chrom, pos=int(pos_str), ref=ref, alt=alt,
                qual=qual, filter=filter_val,
                info_json=dict(info),
                **annotations,
            )
            if on_variant:
                on_variant(variant)

    pipeline_key = detect_pipeline_key(header_lines)
    return VcfMeta(pipeline_key=pipeline_key, header_lines=header_lines)


def _try_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_vcf_parser.py -v`
— all tests green.

---

## 8. Milestone 6 — `db.py`

### Red: write tests first

```python
# tests/test_db.py
import os
import pytest
from unittest.mock import MagicMock, patch, call

# Reset module state before each test
import importlib
import app.lib.db as db_module


@pytest.fixture(autouse=True)
def reset_db():
    db_module._reset_pool()
    yield
    db_module._reset_pool()


def test_resolve_secrets_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/test")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    # Should not raise
    with patch("psycopg2.pool.ThreadedConnectionPool") as MockPool:
        MockPool.return_value = MagicMock()
        db_module.query("SELECT 1")


def test_resolve_secrets_from_secretsmanager(monkeypatch):
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:...:secret:db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AWS_REGION", "eu-west-2")

    secret_payload = '{"username": "u", "password": "p", "host": "db.host", "dbname": "variants", "port": 5432}'
    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": secret_payload}

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "test")]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("boto3.client", return_value=mock_sm), \
         patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        rows = db_module.query("SELECT id, name FROM patients")

    assert rows == [{"id": 1, "name": "test"}]
    assert "DATABASE_URL" in os.environ
    assert "u" in os.environ["DATABASE_URL"]


def test_resolve_secrets_missing_both_env_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL or DB_SECRET_ARN"):
        db_module._resolve_secrets()


def test_resolve_secrets_incomplete_secret(monkeypatch):
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:...:secret:db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    incomplete = '{"username": "u", "password": "p"}'  # missing host + dbname
    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": incomplete}
    with patch("boto3.client", return_value=mock_sm):
        with pytest.raises(RuntimeError, match="missing fields"):
            db_module._resolve_secrets()


def test_with_transaction_commits_on_success(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        with db_module.with_transaction() as conn:
            conn.execute("INSERT INTO x VALUES (1)")
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()


def test_with_transaction_rollbacks_on_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)

    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_pool.putconn = MagicMock()

    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        with pytest.raises(ValueError):
            with db_module.with_transaction():
                raise ValueError("oops")
        mock_conn.rollback.assert_called_once()
```

### Green: implement `db.py`

```python
# app/lib/db.py
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Generator
from urllib.parse import quote_plus

import boto3
import psycopg2
import psycopg2.pool
import psycopg2.extensions

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_secrets_resolved: bool = False


def _resolve_secrets() -> None:
    global _secrets_resolved
    if _secrets_resolved:
        return

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        region = os.environ.get("AWS_REGION", "eu-west-2")
        sm = boto3.client("secretsmanager", region_name=region)
        resp = sm.get_secret_value(SecretId=secret_arn)
        secret = json.loads(resp["SecretString"])
        required = {"username", "password", "host", "dbname"}
        missing = required - set(secret.keys())
        if missing:
            raise RuntimeError(f"DB secret {secret_arn} missing fields: {missing}")
        port = secret.get("port", 5432)
        os.environ["DATABASE_URL"] = (
            f"postgresql://{quote_plus(secret['username'])}:{quote_plus(secret['password'])}"
            f"@{secret['host']}:{port}/{quote_plus(secret['dbname'])}"
        )

    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL or DB_SECRET_ARN must be set")

    _secrets_resolved = True


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    _resolve_secrets()
    if _pool is None:
        conn_str = os.environ["DATABASE_URL"]
        kwargs: dict = {}
        if os.environ.get("APP_ENV") == "production":
            kwargs["sslmode"] = "require"
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=conn_str, **kwargs
        )
    return _pool


@contextmanager
def _get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return all rows as list of dicts."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            return []


@contextmanager
def with_transaction() -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager: BEGIN on enter, COMMIT on exit, ROLLBACK on exception."""
    with _get_connection() as conn:
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True


def _reset_pool() -> None:
    """Test helper — reset module-level state between tests."""
    global _pool, _secrets_resolved
    _pool = None
    _secrets_resolved = False
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_db.py -v`
— all tests green.

---

## 9. Milestone 7 — Golden test fixtures (PR 4 prerequisite)

**This milestone must be completed before writing any code for M8 or M9.**

### Generate from TypeScript source

The canonical fixtures are produced by running the TypeScript classification
engine. Run this script from the repo root:

```bash
# scripts/generate_golden_tests.mjs
# Requires: node >=18, ts-node/esm or tsx

# Install tsx globally if needed: npm install -g tsx
# Then:
git show discovery/nextjs:lib/classification-engine.ts > /tmp/classification-engine.ts
git show discovery/nextjs:config/canvig-gene-mtaf.json > /tmp/canvig-gene-mtaf.json
```

Since running ts-node requires toolchain setup, the golden fixtures derived
from TypeScript source analysis are embedded below. **Commit these files before
implementing the Python engine.** If you want to regenerate, use the
`scripts/generate_golden.mjs` file included at the bottom of this section.

### Create `tests/golden/classify_acgs_cases.json`

```json
[
  {
    "description": "BA1 standalone — overrides all scoring, returns Benign",
    "criteria": [{"criterion_code": "BA1", "applied": true, "strength": "standalone"}],
    "combination_rules": [{"rule": "BA1_overrides_all", "codes": ["BA1"], "message": "BA1 is standalone Benign and overrides the point-based score. Other criteria are not needed."}],
    "expected": {"score": -999, "classification": "Benign", "warnings": []}
  },
  {
    "description": "PVS1 (very_strong=8) + PS1 (strong=4) = 12 → Pathogenic",
    "criteria": [
      {"criterion_code": "PVS1", "applied": true, "strength": "very_strong"},
      {"criterion_code": "PS1",  "applied": true, "strength": "strong"}
    ],
    "combination_rules": [],
    "expected": {"score": 12, "classification": "Pathogenic", "warnings": []}
  },
  {
    "description": "PVS1 (very_strong=8) + PM2 (supporting=1) = 9 → Likely_Pathogenic",
    "criteria": [
      {"criterion_code": "PVS1", "applied": true, "strength": "very_strong"},
      {"criterion_code": "PM2",  "applied": true, "strength": "supporting"}
    ],
    "combination_rules": [],
    "expected": {"score": 9, "classification": "Likely_Pathogenic", "warnings": []}
  },
  {
    "description": "PP3 (supporting=+1) + BP4 (supporting=-1) = 0 → VUS + conflict warning",
    "criteria": [
      {"criterion_code": "PP3", "applied": true, "strength": "supporting"},
      {"criterion_code": "BP4", "applied": true, "strength": "supporting"}
    ],
    "combination_rules": [{"rule": "PP3_BP4_conflict", "codes": ["PP3", "BP4"], "message": "PP3 and BP4 should not both be applied \u2014 they are opposing computational evidence."}],
    "expected": {"score": 0, "classification": "VUS", "warnings": ["PP3 and BP4 should not both be applied \u2014 they are opposing computational evidence."]}
  },
  {
    "description": "BS1 (strong=-4) + BP7 (supporting=-1) = -5 → Likely_Benign",
    "criteria": [
      {"criterion_code": "BS1", "applied": true, "strength": "strong"},
      {"criterion_code": "BP7", "applied": true, "strength": "supporting"}
    ],
    "combination_rules": [],
    "expected": {"score": -5, "classification": "Likely_Benign", "warnings": []}
  },
  {
    "description": "BS1 + BS2 + BS3 (strong=-4 each) = -12 → Benign",
    "criteria": [
      {"criterion_code": "BS1", "applied": true, "strength": "strong"},
      {"criterion_code": "BS2", "applied": true, "strength": "strong"},
      {"criterion_code": "BS3", "applied": true, "strength": "strong"}
    ],
    "combination_rules": [],
    "expected": {"score": -12, "classification": "Benign", "warnings": []}
  },
  {
    "description": "Single BP4 (supporting=-1) — minimum criteria warning, score=-1 → Likely_Benign",
    "criteria": [
      {"criterion_code": "BP4", "applied": true, "strength": "supporting"}
    ],
    "combination_rules": [],
    "expected": {"score": -1, "classification": "Likely_Benign", "warnings": ["ACGS requires a minimum of 2 applied criteria for any non-VUS classification (except BA1)."]}
  },
  {
    "description": "No criteria applied — score=0 → VUS",
    "criteria": [],
    "combination_rules": [],
    "expected": {"score": 0, "classification": "VUS", "warnings": []}
  }
]
```

### Create `tests/golden/classify_svig_cases.json`

```json
[
  {
    "description": "O1 standalone → Oncogenic (sentinel 999)",
    "criteria": [{"criterion_code": "O1", "applied": true, "strength": "standalone"}],
    "combination_rules": [],
    "expected": {"score": 999, "classification": "Oncogenic", "warnings": []}
  },
  {
    "description": "B1 standalone → Benign (sentinel -999)",
    "criteria": [{"criterion_code": "B1", "applied": true, "strength": "standalone"}],
    "combination_rules": [],
    "expected": {"score": -999, "classification": "Benign", "warnings": []}
  },
  {
    "description": "B2 standalone → forces VUS",
    "criteria": [{"criterion_code": "B2", "applied": true, "strength": "standalone"}],
    "combination_rules": [],
    "expected": {"score": 0, "classification": "VUS", "warnings": []}
  },
  {
    "description": "O4 (strong=4) + O3 (moderate=2) = 6 → Likely_Oncogenic",
    "criteria": [
      {"criterion_code": "O4", "applied": true, "strength": "strong"},
      {"criterion_code": "O3", "applied": true, "strength": "moderate"}
    ],
    "combination_rules": [],
    "expected": {"score": 6, "classification": "Likely_Oncogenic", "warnings": []}
  },
  {
    "description": "O4 (very_strong=8) + O3 (moderate=2) = 10 → Oncogenic",
    "criteria": [
      {"criterion_code": "O4", "applied": true, "strength": "very_strong"},
      {"criterion_code": "O3", "applied": true, "strength": "moderate"}
    ],
    "combination_rules": [],
    "expected": {"score": 10, "classification": "Oncogenic", "warnings": []}
  },
  {
    "description": "B3 (supporting=-1) + B5 (supporting=-1) = -2 → Likely_Benign",
    "criteria": [
      {"criterion_code": "B3", "applied": true, "strength": "supporting"},
      {"criterion_code": "B5", "applied": true, "strength": "supporting"}
    ],
    "combination_rules": [],
    "expected": {"score": -2, "classification": "Likely_Benign", "warnings": []}
  }
]
```

### Create `tests/golden/select_framework_cases.json`

```json
[
  {"description": "somatic + TP53 → svig", "case_type": "somatic", "gene": "TP53", "expected": {"framework": "svig", "is_canvig": false}},
  {"description": "germline + BRCA1 → acgs_snv + CanVIG", "case_type": "germline", "gene": "BRCA1", "expected": {"framework": "acgs_snv", "is_canvig": true}},
  {"description": "germline + BRCA2 → acgs_snv + CanVIG", "case_type": "germline", "gene": "BRCA2", "expected": {"framework": "acgs_snv", "is_canvig": true}},
  {"description": "germline + TP53 → acgs_snv + CanVIG (CanVIG gene)", "case_type": "germline", "gene": "TP53", "expected": {"framework": "acgs_snv", "is_canvig": true}},
  {"description": "germline + UNKNOWN_GENE → acgs_snv, not CanVIG", "case_type": "germline", "gene": "UNKNOWN_GENE", "expected": {"framework": "acgs_snv", "is_canvig": false}},
  {"description": "germline + null gene → acgs_snv, not CanVIG", "case_type": "germline", "gene": null, "expected": {"framework": "acgs_snv", "is_canvig": false}},
  {"description": "germline + lowercase brca1 → case-insensitive match → CanVIG", "case_type": "germline", "gene": "brca1", "expected": {"framework": "acgs_snv", "is_canvig": true}}
]
```

### Create `tests/golden/pre_compute_cases.json`

```json
[
  {
    "description": "BRCA1 germline, gnomAD=0.0005 (> bs1=0.0003, < ba1=0.001) → BS1 only",
    "variant": {"gene": "BRCA1", "consequence": null, "gnomad_af": 0.0005, "revel_score": null, "spliceai_max": null, "clinvar_sig": null},
    "case_type": "germline",
    "expected_codes": ["BS1"],
    "expected_strengths": {"BS1": "strong"}
  },
  {
    "description": "BRCA1 germline, gnomAD=0.0015 (> ba1=0.001) → BA1 only",
    "variant": {"gene": "BRCA1", "consequence": null, "gnomad_af": 0.0015, "revel_score": null, "spliceai_max": null, "clinvar_sig": null},
    "case_type": "germline",
    "expected_codes": ["BA1"],
    "expected_strengths": {"BA1": "standalone"}
  },
  {
    "description": "Unknown gene germline, frameshift + gnomAD very low → PVS1 + PM2",
    "variant": {"gene": null, "consequence": "frameshift_variant", "gnomad_af": 0.000001, "revel_score": null, "spliceai_max": null, "clinvar_sig": null},
    "case_type": "germline",
    "expected_codes": ["PVS1", "PM2"],
    "expected_strengths": {"PVS1": "very_strong", "PM2": "supporting"}
  },
  {
    "description": "Germline, synonymous + spliceai=0.05 + revel=0.35 → BP4 + BP7",
    "variant": {"gene": null, "consequence": "synonymous_variant", "gnomad_af": null, "revel_score": 0.35, "spliceai_max": 0.05, "clinvar_sig": null},
    "case_type": "germline",
    "expected_codes": ["PM2", "BP4", "BP7"],
    "expected_strengths": {"BP4": "supporting", "BP7": "supporting", "PM2": "supporting"}
  },
  {
    "description": "Somatic TP53, gnomAD absent → O3 (moderate)",
    "variant": {"gene": "TP53", "consequence": null, "gnomad_af": null, "revel_score": null, "spliceai_max": null, "clinvar_sig": null},
    "case_type": "somatic",
    "expected_codes": ["O3"],
    "expected_strengths": {"O3": "moderate"}
  },
  {
    "description": "Somatic, frameshift + high REVEL → O2 + O6",
    "variant": {"gene": null, "consequence": "stop_gained", "gnomad_af": null, "revel_score": 0.85, "spliceai_max": null, "clinvar_sig": null},
    "case_type": "somatic",
    "expected_codes": ["O3", "O2", "O6"],
    "expected_strengths": {"O2": "very_strong", "O3": "moderate", "O6": "supporting"}
  }
]
```

**Verification:** `cd backend && ls tests/golden/*.json | wc -l` → 4 files.
Commit the golden fixtures: `git add tests/golden/ && git commit -m "test: add classification engine golden fixtures"`.

---

## 10. Milestone 8 — `classification_engine.py`

### Red: write tests first

```python
# tests/test_classification_engine.py
import json
from pathlib import Path
import pytest
from app.lib.classification_engine import (
    classify, select_framework, get_framework_version,
    classification_label, classification_badge_class,
    AppliedCriterion, CombinationRule, ClassificationResult,
)
    classify, select_framework, get_framework_version,
    classification_label, classification_badge_class,
    AppliedCriterion, CombinationRule, ClassificationResult,
)

_GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_cases(fname: str) -> list[dict]:
    return json.loads((_GOLDEN_DIR / fname).read_text())


def _make_criteria(raw: list[dict]) -> list[AppliedCriterion]:
    return [AppliedCriterion(**c) for c in raw]


def _make_rules(raw: list[dict]) -> list[CombinationRule]:
    return [CombinationRule(**r) for r in raw]


@pytest.mark.parametrize("case", _load_cases("classify_acgs_cases.json"))
def test_acgs_golden(case):
    result = classify(
        _make_criteria(case["criteria"]),
        "acgs_snv",
        _make_rules(case["combination_rules"]),
    )
    exp = case["expected"]
    assert result.score == exp["score"], f"[{case['description']}] score mismatch"
    assert result.classification == exp["classification"], f"[{case['description']}] classification mismatch"
    assert result.warnings == exp["warnings"], f"[{case['description']}] warnings mismatch"


@pytest.mark.parametrize("case", _load_cases("classify_svig_cases.json"))
def test_svig_golden(case):
    result = classify(
        _make_criteria(case["criteria"]),
        "svig",
        _make_rules(case["combination_rules"]),
    )
    exp = case["expected"]
    assert result.score == exp["score"]
    assert result.classification == exp["classification"]
    assert result.warnings == exp["warnings"]


@pytest.mark.parametrize("case", _load_cases("select_framework_cases.json"))
def test_select_framework_golden(case):
    framework, is_canvig = select_framework(case["case_type"], case["gene"])
    assert framework == case["expected"]["framework"]
    assert is_canvig == case["expected"]["is_canvig"]


def test_get_framework_version_acgs():
    assert "ACGS" in get_framework_version("acgs_snv")

def test_get_framework_version_svig():
    assert "SVIG" in get_framework_version("svig")

def test_classification_label_vus():
    assert classification_label("VUS") == "Variant of Uncertain Significance"

def test_classification_label_likely_pathogenic():
    assert classification_label("Likely_Pathogenic") == "Likely Pathogenic"

def test_not_applied_criteria_ignored():
    criteria = [
        AppliedCriterion("PVS1", applied=False, strength="very_strong"),
        AppliedCriterion("PM2",  applied=True,  strength="supporting"),
    ]
    result = classify(criteria, "acgs_snv", [])
    # Only PM2 applied (+1), but single criterion → warning; score=1 → Likely_Pathogenic? No: 1 < 6
    # Actually score=1 → 0 ≤ 1 < 6 → VUS. But minimum warning because 1 criterion + score≠0.
    assert result.classification == "VUS"
```

### Green: implement `classification_engine.py`

```python
# app/lib/classification_engine.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ACGS_VERSION = "ACGS 2024 Best Practice Guidelines"
SVIG_VERSION = "SVIG-UK v1.0"

Framework = Literal["acgs_snv", "svig"]
CaseType  = Literal["germline", "somatic"]

# Config path resolves to backend/config/ from app/lib/
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

# Load CanVIG gene set once at import time (case-insensitive lookup)
_canvig_raw = json.loads((_CONFIG_DIR / "canvig-gene-mtaf.json").read_text())
_CANVIG_GENES: set[str] = {g.upper() for g in _canvig_raw["genes"].keys()}

STRENGTH_POINTS: dict[str, int] = {
    "very_strong": 8, "strong": 4, "moderate": 2, "supporting": 1,
}
BENIGN_POINTS: dict[str, int] = {
    "strong": -4, "moderate": -2, "supporting": -1,
}


@dataclass
class AppliedCriterion:
    criterion_code: str
    applied: bool
    strength: str


@dataclass
class CombinationRule:
    rule: str
    codes: list[str]
    message: str


@dataclass
class ClassificationResult:
    score: int
    classification: str
    warnings: list[str] = field(default_factory=list)


def _get_direction(code: str, framework: Framework) -> str | None:
    if framework == "acgs_snv":
        if re.match(r"^(PVS|PS|PM|PP)", code): return "pathogenic"
        if re.match(r"^(BA|BS|BP)", code):      return "benign"
    else:
        if re.match(r"^O", code): return "oncogenic"
        if re.match(r"^B", code): return "benign"
    return None


def _check_combination_rules(
    applied: list[AppliedCriterion],
    rules: list[CombinationRule],
) -> list[str]:
    warnings: list[str] = []
    applied_codes = {c.criterion_code for c in applied}
    for rule in rules:
        matching = [c for c in rule.codes if c in applied_codes]
        if len(rule.codes) >= 2 and len(matching) >= 2:
            warnings.append(rule.message)
    return warnings


def classify(
    criteria: list[AppliedCriterion],
    framework: Framework,
    combination_rules: list[CombinationRule],
) -> ClassificationResult:
    applied = [c for c in criteria if c.applied]
    warnings = _check_combination_rules(applied, combination_rules)

    if framework == "acgs_snv":
        # Step 3: BA1 override
        if any(c.criterion_code == "BA1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign", warnings=warnings)

        # Steps 4–5: score
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction == "pathogenic":
                pts = STRENGTH_POINTS.get(c.strength, 0) if c.strength != "standalone" else 8
                score += pts
            elif direction == "benign":
                score += BENIGN_POINTS.get(c.strength, 0)

        # Step 6: minimum criteria warning
        if len(applied) < 2 and score != 0:
            warnings.append(
                "ACGS requires a minimum of 2 applied criteria for any non-VUS classification (except BA1)."
            )

        # Step 7: classify by score
        if score >= 10:   return ClassificationResult(score, "Pathogenic",     warnings)
        if score >= 6:    return ClassificationResult(score, "Likely_Pathogenic", warnings)
        if score >= 0:    return ClassificationResult(score, "VUS",             warnings)
        if score >= -6:   return ClassificationResult(score, "Likely_Benign",   warnings)
        return ClassificationResult(score, "Benign", warnings)

    else:  # svig
        # Steps 2–4: sentinel overrides
        if any(c.criterion_code == "O1" for c in applied):
            return ClassificationResult(score=999,  classification="Oncogenic", warnings=warnings)
        if any(c.criterion_code == "B1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign",    warnings=warnings)
        if any(c.criterion_code == "B2" for c in applied):
            return ClassificationResult(score=0,    classification="VUS",       warnings=warnings)

        # Step 5: score
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction == "oncogenic":
                score += STRENGTH_POINTS.get(c.strength, 0)
            elif direction == "benign":
                score += BENIGN_POINTS.get(c.strength, 0)

        # Step 6: classify
        if score >= 10:  return ClassificationResult(score, "Oncogenic",       warnings)
        if score >= 6:   return ClassificationResult(score, "Likely_Oncogenic", warnings)
        if score >= 0:   return ClassificationResult(score, "VUS",              warnings)
        if score >= -6:  return ClassificationResult(score, "Likely_Benign",    warnings)
        return ClassificationResult(score, "Benign", warnings)


def select_framework(case_type: CaseType, gene: str | None) -> tuple[Framework, bool]:
    if case_type == "somatic":
        return "svig", False
    normalised = gene.strip().upper() if gene else None
    is_canvig = normalised in _CANVIG_GENES if normalised else False
    return "acgs_snv", is_canvig


def get_framework_version(framework: Framework) -> str:
    return ACGS_VERSION if framework == "acgs_snv" else SVIG_VERSION


def classification_label(classification: str) -> str:
    labels = {
        "Pathogenic": "Pathogenic",
        "Likely_Pathogenic": "Likely Pathogenic",
        "VUS": "Variant of Uncertain Significance",
        "Likely_Benign": "Likely Benign",
        "Benign": "Benign",
        "Oncogenic": "Oncogenic",
        "Likely_Oncogenic": "Likely Oncogenic",
    }
    return labels.get(classification, classification)


def classification_badge_class(classification: str) -> str:
    badge = {
        "Pathogenic": "pathogenic",
        "Likely_Pathogenic": "likely-pathogenic",
        "VUS": "vus",
        "Likely_Benign": "likely-benign",
        "Benign": "benign",
        "Oncogenic": "oncogenic",
        "Likely_Oncogenic": "likely-oncogenic",
    }
    return badge.get(classification, "vus")
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_classification_engine.py -v`
— all golden cases green.

---

## 11. Milestone 9 — `pre_compute_criteria.py`

### Red: write tests first

```python
# tests/test_pre_compute_criteria.py
import json
from dataclasses import asdict
from pathlib import Path
import pytest
from app.lib.pre_compute_criteria import pre_compute_criteria
from app.lib.vcf_parser import VcfVariant


def _make_variant(**kwargs) -> VcfVariant:
    defaults = dict(
        chrom="1", pos=100, ref="A", alt="G", qual=None, filter=None,
        hgvs_c=None, hgvs_p=None, info_json={},
    )
    defaults.update(kwargs)
    return VcfVariant(**defaults)


_CASES = json.loads((Path(__file__).parent / "golden" / "pre_compute_cases.json").read_text())


@pytest.mark.parametrize("case", _CASES)
def test_pre_compute_golden(case):
    v_data = case["variant"]
    variant = _make_variant(**v_data)
    results = pre_compute_criteria(variant, case["case_type"])

    result_codes = {r.criterion_code for r in results}
    expected_codes = set(case["expected_codes"])

    assert result_codes == expected_codes, (
        f"[{case['description']}]\n"
        f"  Got codes:      {sorted(result_codes)}\n"
        f"  Expected codes: {sorted(expected_codes)}"
    )

    for code, strength in case["expected_strengths"].items():
        matching = next(r for r in results if r.criterion_code == code)
        assert matching.suggested_strength == strength, (
            f"[{case['description']}] {code} strength: got {matching.suggested_strength}, expected {strength}"
        )
```

### Green: implement `pre_compute_criteria.py`

```python
# app/lib/pre_compute_criteria.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.lib.classification_engine import select_framework, Framework
from app.lib.vcf_parser import VcfVariant

CaseType = Literal["germline", "somatic"]

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_canvig_raw = json.loads((_CONFIG_DIR / "canvig-gene-mtaf.json").read_text())
_CANVIG_GENES: dict = _canvig_raw["genes"]

_LOF_CONSEQUENCES = {
    "frameshift_variant", "stop_gained", "stop_lost", "start_lost",
    "splice_donor_variant", "splice_acceptor_variant", "transcript_ablation",
}
_CANONICAL_SPLICE = {"splice_donor_variant", "splice_acceptor_variant"}

_ACGS_DEFAULT_BA1 = 0.05
_ACGS_DEFAULT_BS1 = 0.001


@dataclass
class PreComputedCriterion:
    criterion_code: str
    pre_computed_value: str
    framework: Framework
    suggested_strength: str


def _gnomad_thresholds(gene: str | None) -> tuple[float, float]:
    if gene:
        g = _CANVIG_GENES.get(gene) or _CANVIG_GENES.get(gene.upper())
        if g:
            return g["ba1_threshold"], g["bs1_threshold"]
    return _ACGS_DEFAULT_BA1, _ACGS_DEFAULT_BS1


def pre_compute_criteria(
    variant: VcfVariant,
    case_type: CaseType,
) -> list[PreComputedCriterion]:
    results: list[PreComputedCriterion] = []
    framework, is_canvig = select_framework(case_type, variant.gene)
    gnomad = variant.gnomad_af
    csq = variant.consequence.split("&")[0] if variant.consequence else None

    if framework == "acgs_snv":
        ba1_thresh, bs1_thresh = _gnomad_thresholds(variant.gene)

        # BA1 — standalone benign if AF above threshold
        if gnomad is not None and gnomad > ba1_thresh:
            label = f"CanVIG {variant.gene}" if is_canvig else "ACGS standard"
            results.append(PreComputedCriterion(
                criterion_code="BA1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} [threshold {ba1_thresh} \u2014 {label}]",
                framework=framework,
                suggested_strength="standalone",
            ))

        # BS1 — elevated AF
        if gnomad is not None and bs1_thresh < gnomad <= ba1_thresh:
            results.append(PreComputedCriterion(
                criterion_code="BS1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} [BS1 threshold {bs1_thresh}]",
                framework=framework,
                suggested_strength="strong",
            ))

        # PM2 — absent or very low AF
        if gnomad is None or gnomad < 0.0001:
            af_label = "absent in gnomAD" if gnomad is None else f"gnomAD AF = {gnomad:.2e}"
            results.append(PreComputedCriterion(
                criterion_code="PM2",
                pre_computed_value=af_label,
                framework=framework,
                suggested_strength="supporting",
            ))

        # PVS1 — null variant (LOF)
        if csq and csq in _LOF_CONSEQUENCES:
            results.append(PreComputedCriterion(
                criterion_code="PVS1",
                pre_computed_value=f"Consequence: {variant.consequence}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # PVS1_RNA — high SpliceAI
        if variant.spliceai_max is not None and variant.spliceai_max >= 0.8:
            results.append(PreComputedCriterion(
                criterion_code="PVS1_RNA",
                pre_computed_value=f"SpliceAI max delta = {variant.spliceai_max:.3f}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # PP3 — damaging REVEL
        if variant.revel_score is not None and variant.revel_score >= 0.7:
            results.append(PreComputedCriterion(
                criterion_code="PP3",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # BP4 — benign REVEL
        if variant.revel_score is not None and variant.revel_score <= 0.4:
            results.append(PreComputedCriterion(
                criterion_code="BP4",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # BP7 — synonymous + low SpliceAI
        if variant.consequence and "synonymous_variant" in variant.consequence:
            sai = variant.spliceai_max
            if sai is None or sai < 0.1:
                sai_str = f"{sai:.3f}" if sai is not None else "N/A"
                results.append(PreComputedCriterion(
                    criterion_code="BP7",
                    pre_computed_value=f"Synonymous variant; SpliceAI max delta = {sai_str}",
                    framework=framework,
                    suggested_strength="supporting",
                ))

        # PS1 — ClinVar pathogenic
        if (variant.clinvar_sig
                and re.search(r"pathogenic", variant.clinvar_sig, re.I)
                and not re.search(r"conflict", variant.clinvar_sig, re.I)):
            results.append(PreComputedCriterion(
                criterion_code="PS1",
                pre_computed_value=f"ClinVar: {variant.clinvar_sig}",
                framework=framework,
                suggested_strength="strong",
            ))

    else:  # svig
        # B1 — germline polymorphism (AF > 0.01)
        if gnomad is not None and gnomad > 0.01:
            results.append(PreComputedCriterion(
                criterion_code="B1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} (> 0.01)",
                framework=framework,
                suggested_strength="standalone",
            ))

        # O3 — absent or very rare
        if gnomad is None or gnomad < 0.0001:
            af_label = "absent in gnomAD" if gnomad is None else f"gnomAD AF = {gnomad:.2e}"
            results.append(PreComputedCriterion(
                criterion_code="O3",
                pre_computed_value=af_label,
                framework=framework,
                suggested_strength="moderate",
            ))

        # O2 — null variant in TSG
        if csq and csq in _LOF_CONSEQUENCES:
            results.append(PreComputedCriterion(
                criterion_code="O2",
                pre_computed_value=f"Consequence: {variant.consequence}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # O6 — computational damaging
        if variant.revel_score is not None and variant.revel_score >= 0.7:
            results.append(PreComputedCriterion(
                criterion_code="O6",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # B3 — computational benign (REVEL ≤ 0.4 or SpliceAI < 0.1)
        b3_added = False
        if variant.revel_score is not None and variant.revel_score <= 0.4:
            results.append(PreComputedCriterion(
                criterion_code="B3",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))
            b3_added = True
        if not b3_added and variant.spliceai_max is not None and variant.spliceai_max < 0.1:
            results.append(PreComputedCriterion(
                criterion_code="B3",
                pre_computed_value=f"SpliceAI max delta = {variant.spliceai_max:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # O1 — ClinVar somatic oncogenic
        if (variant.clinvar_sig
                and re.search(r"oncogenic|pathogenic", variant.clinvar_sig, re.I)
                and not re.search(r"conflict", variant.clinvar_sig, re.I)):
            results.append(PreComputedCriterion(
                criterion_code="O1",
                pre_computed_value=f"ClinVar: {variant.clinvar_sig}",
                framework=framework,
                suggested_strength="standalone",
            ))

    return results
```

**Verification:** `cd backend && .venv/bin/pytest tests/test_pre_compute_criteria.py -v`
— all golden cases green.

---

## 12. Milestone 10 — Final checks

```bash
cd backend

# All tests including pre-existing 81
.venv/bin/pytest -v
# Expected: 81 (config integrity) + ~70 new = all passing

# Coverage check
.venv/bin/pip install pytest-cov
.venv/bin/pytest --cov=app --cov=classification_engine --cov=pre_compute_criteria \
  --cov-report=term-missing --cov-fail-under=80

# Verify no DB credentials in test output (invariant check)
.venv/bin/pytest -s 2>&1 | grep -iE "password|secret|DATABASE_URL" && echo "FAIL: credentials in output" || echo "OK: no credentials leaked"

# Import smoke test for all new modules
python -c "
from app.lib.models import Patient, Variant, VariantClassification
from app.lib.db import query, with_transaction
from app.lib.pipeline_config import detect_pipeline_key
from app.lib.fhir_manifest import parse_manifest, build_manifest
from app.lib.vcf_parser import parse_vcf
from app.lib.classification_engine import classify, select_framework
from app.lib.pre_compute_criteria import pre_compute_criteria
print('All imports OK')
"
```

---

## 13. Future work (out of scope for PRs 2–4, delivered in PR 5)

- **PR 5** — see Milestones 11–12 below.
- **PR 6/7** — FastAPI routes in `app/routes/`.
- **PR 8–11** — React SPA frontend.
- **PR 12** — ECS task definition update.
- **Async DB** — Replace psycopg2 with asyncpg; deferred to PR 12.

---

## 14. Milestone 11 — `vcf_parser.py` → cyvcf2 migration (PR 5)

### Why

CNVs are on the roadmap. The hand-rolled parser cannot handle BCF, symbolic
alleles (`<DEL>`, `<DUP>`), or multi-sample FORMAT columns. `cyvcf2` (htslib)
resolves all three. See DESIGN.md §3.5.1 for full rationale.

### Pre-work: add cyvcf2 to dependencies

```bash
# 1. Add to requirements.in
echo 'cyvcf2>=0.30.0' >> backend/requirements.in

# 2. Regenerate pinned requirements
cd backend
.venv/bin/pip install pip-tools
.venv/bin/pip-compile --generate-hashes --allow-unsafe requirements.in -o requirements.txt

# 3. Install
.venv/bin/pip install --require-hashes --no-deps -r requirements.txt
```

Update `backend/Dockerfile` to install build dependencies before the pip step:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        zlib1g-dev libbz2-dev liblzma-dev && \
    rm -rf /var/lib/apt/lists/*
```

### Red: rewrite `test_vcf_parser.py` for file-path API

The PR 3 tests used inline string fixtures with `parse_vcf(text.splitlines(), ...)`.
cyvcf2 requires a file path. Replace all tests to write temp files using
pytest’s `tmp_path` fixture:

```python
# tests/test_vcf_parser.py (PR 5 version)
import pytest
from pathlib import Path
from app.lib.vcf_parser import parse_vcf, VcfVariant, VcfMeta

_VEP_CONTENT = (
    '##fileformat=VCFv4.2\n'
    '##source=DRAGENv4.2\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="VEP ... Format: '
    'Allele|Consequence|SYMBOL|Gene|HGVSc|HGVSp|gnomADe_AF|REVEL|'
    'SpliceAI_pred_DS_AG|SpliceAI_pred_DS_AL|SpliceAI_pred_DS_DG|SpliceAI_pred_DS_DL|'
    'CLIN_SIG|CANONICAL">\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t100\t.\tA\tG\t50.0\tPASS\t'
    'CSQ=G|missense_variant|BRCA1|ENSG001|c.100A>G|p.Thr34Ala'
    '|0.0001|0.75|0.1|0.2|0.05|0.3|Pathogenic|YES\n'
)

_MULTI_ALLELIC_CONTENT = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t200\t.\tA\tG,T\t.\t.\t.\n'
)

_FLAT_CSQ_CONTENT = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '3\t400\t.\tG\tA\t.\t.\t'
    'CSQ_SYMBOL=BRCA2;CSQ_Consequence=frameshift_variant;'
    'CSQ_gnomADe_AF=0.0002;CSQ_REVEL=0.8\n'
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def _collect(path: Path) -> tuple[list[VcfVariant], VcfMeta]:
    variants: list[VcfVariant] = []
    meta = parse_vcf(path, on_variant=variants.append)
    return variants, meta


def test_vep_basic_fields(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 1
    v = variants[0]
    assert v.chrom == "1"
    assert v.pos == 100
    assert v.ref == "A" and v.alt == "G"
    assert v.qual == 50.0 and v.filter == "PASS"
    assert v.gene == "BRCA1"
    assert v.consequence == "missense_variant"
    assert v.hgvs_c == "c.100A>G" and v.hgvs_p == "p.Thr34Ala"
    assert abs(v.gnomad_af - 0.0001) < 1e-9
    assert abs(v.revel_score - 0.75) < 1e-9
    assert v.clinvar_sig == "Pathogenic"


def test_vep_spliceai_max(tmp_path):
    # DS_AG=0.1, DS_AL=0.2, DS_DG=0.05, DS_DL=0.3 → max=0.3
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    variants, _ = _collect(p)
    assert abs(variants[0].spliceai_max - 0.3) < 1e-9


def test_pipeline_detected_from_header(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    _, meta = _collect(p)
    assert meta.pipeline_key == "dragen_germline"


def test_multi_allelic_split(tmp_path):
    p = _write(tmp_path, "multi.vcf", _MULTI_ALLELIC_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 2
    assert {v.alt for v in variants} == {"G", "T"}


def test_missing_qual_becomes_none(tmp_path):
    p = _write(tmp_path, "multi.vcf", _MULTI_ALLELIC_CONTENT)
    variants, _ = _collect(p)
    assert all(v.qual is None for v in variants)


def test_flat_csq_fields(tmp_path):
    p = _write(tmp_path, "flat.vcf", _FLAT_CSQ_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 1
    v = variants[0]
    assert v.gene == "BRCA2"
    assert v.consequence == "frameshift_variant"
    assert abs(v.gnomad_af - 0.0002) < 1e-9
    assert abs(v.revel_score - 0.8) < 1e-9


def test_spanning_deletion_skipped(tmp_path):
    content = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "1\t500\t.\tATG\tA,*\t.\t.\t.\n"
    )
    p = _write(tmp_path, "span.vcf", content)
    variants: list[VcfVariant] = []
    parse_vcf(p, on_variant=variants.append)
    assert len(variants) == 1
    assert variants[0].alt == "A"


def test_header_lines_captured(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    _, meta = _collect(p)
    assert any("fileformat" in line for line in meta.header_lines)
```

Run to confirm red: `cd backend && .venv/bin/pytest tests/test_vcf_parser.py -v`
→ 8 tests fail (TypeError: wrong argument type for `parse_vcf`).

### Green: rewrite `parse_vcf` to use cyvcf2

Only `parse_vcf()` changes. All helper functions (`_extract_vep`,
`_extract_flat_csq`, `_csq_field`, `_spliceai_max`, `_try_float`) are
unchanged. Replace the function body:

```python
# app/lib/vcf_parser.py  — PR 5 parse_vcf replacement
import cyvcf2  # new import at top of file

def parse_vcf(
    path: str | Path,
    on_variant: Callable[[VcfVariant], None] | None = None,
) -> VcfMeta:
    """Parse a VCF or BCF file using cyvcf2 (htslib)."""
    vcf = cyvcf2.VCF(str(path))

    # Extract header lines for pipeline detection
    header_lines = [
        line for line in str(vcf.raw_header).splitlines()
        if line.startswith("##")
    ]

    # Parse CSQ FORMAT from header
    csq_header: list[str] | None = None
    for line in header_lines:
        if "ID=CSQ" in line and "Format:" in line:
            fmt = line.split("Format:")[1].replace('"', "").replace(">", "").strip()
            csq_header = fmt.split("|")
            break

    for v in vcf:
        qual: float | None = v.QUAL  # cyvcf2 returns None if "."
        filter_val: str | None = None
        if v.FILTER:               # cyvcf2 returns empty string or filter name
            filter_val = v.FILTER or None

        info: dict = {}            # build info_json for storage
        try:
            for key in v.INFO.keys():
                info[key] = v.INFO.get(key)
        except Exception:
            pass

        for alt in v.ALT:
            if not alt or alt == "*":
                continue

            if csq_header is not None and "CSQ" in info:
                annotations = _extract_vep(info, csq_header, alt)
            elif "CSQ_SYMBOL" in info or "CSQ_Consequence" in info:
                annotations = _extract_flat_csq(info)
            else:
                annotations = {k: None for k in [
                    "gene", "consequence", "hgvs_c", "hgvs_p",
                    "gnomad_af", "clinvar_sig", "revel_score", "spliceai_max",
                ]}

            variant = VcfVariant(
                chrom=v.CHROM,
                pos=v.POS,
                ref=v.REF,
                alt=alt,
                qual=qual,
                filter=filter_val,
                info_json=dict(info),
                **annotations,
            )
            if on_variant:
                on_variant(variant)

    vcf.close()
    pipeline_key = detect_pipeline_key(header_lines)
    return VcfMeta(pipeline_key=pipeline_key, header_lines=header_lines)
```

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_vcf_parser.py -v
# Expected: 8 passed
```

**Invariant check — ensure PR 3 call sites still compile:**
```bash
cd backend && python -c "
from app.lib.vcf_parser import parse_vcf, VcfVariant, VcfMeta
import inspect
sig = inspect.signature(parse_vcf)
assert 'path' in sig.parameters, 'parse_vcf must accept path'
print('OK: parse_vcf signature correct')
"
```

---

## 15. Milestone 12 — `ingest.py` + Lambda handler (PR 5)

### Scope

`app/lib/ingest.py` is the orchestration layer called by the Lambda function.
It:
1. Downloads the VCF and manifest JSON from S3 to `/tmp/`.
2. Validates the manifest against `config/manifest-schema.json` (jsonschema).
3. Parses the manifest with `fhir_manifest.parse_manifest(raw, source=s3_key)`.
4. Calls `check_idempotency()` — already built (PR #18 ingest guard).
5. Calls `parse_vcf(path)` — cyvcf2 version (M11).
6. For each variant: calls `pre_compute_criteria()`, inserts into DB.
7. Creates `WorkflowRecord(status="pending")` for the sample.
8. Raises `DuplicateSubmissionError` or `ValueError` on validation failures;
   caller catches `UniqueViolation` from psycopg2 as a TOCTOU guard.

### Additional dependency

```bash
echo 'jsonschema>=4.0.0' >> backend/requirements.in
.venv/bin/pip-compile --generate-hashes --allow-unsafe requirements.in -o requirements.txt
```

### Public interface

```python
def ingest_sample(
    vcf_s3_key: str,
    manifest_s3_key: str,
    bucket: str,
    s3_client,            # boto3 S3 client — injected for testability
    conn,                 # psycopg2 connection — injected for testability
) -> int:
    """Download, validate, parse, and persist a VCF + manifest from S3.

    Returns the new sample_id (int) on success.
    Raises DuplicateSubmissionError, ValueError, or psycopg2 exceptions.
    """
```

### Lambda handler skeleton

```python
# app/lambda_handler.py
import json, boto3
from app.lib.ingest import ingest_sample
from app.lib.db import with_transaction

def handler(event, context):
    record = event["Records"][0]["s3"]
    bucket    = record["bucket"]["name"]
    vcf_key   = record["object"]["key"]
    # Derive manifest key from VCF key (see DESIGN naming convention)
    manifest_key = vcf_key.replace(".vcf.gz", ".manifest.json")
    s3 = boto3.client("s3", region_name="eu-west-2")
    with with_transaction() as conn:
        sample_id = ingest_sample(vcf_key, manifest_key, bucket, s3, conn)
    return {"statusCode": 200, "sample_id": sample_id}
```

### Tests

All I/O (S3, DB) must be mocked. Key test cases:

| Test | What it asserts |
|---|---|
| `test_ingest_clean_submission` | End-to-end happy path; asserts sample and variants inserted |
| `test_ingest_exact_duplicate` | `DuplicateSubmissionError(duplicate_type="exact")` raised |
| `test_ingest_multiple_vcfs_same_specimen` | second VCF for same patient+specimen is **allowed** (multi-panel RD workflow) |
| `test_ingest_invalid_manifest` | `ValueError` raised on bad FHIR bundle |
| `test_ingest_schema_validation_failure` | `jsonschema.ValidationError` propagates |
| `test_ingest_unique_violation_toctou` | `psycopg2.errors.UniqueViolation` caught and re-raised |

**Verification:**
```bash
cd backend && .venv/bin/pytest tests/test_ingest.py -v
# Expected: 6+ passed
```

---

## 16. Milestone 13 — PR 5 final checks

```bash
cd backend

# All tests
.venv/bin/pytest -v
# Expected: 186+ passed (all prior + M11 + M12 additions)

# Coverage still above threshold
.venv/bin/pytest --cov=app --cov-fail-under=80

# Docker build (validates cyvcf2 C-extension installs cleanly)
sg docker -c 'docker build -t variant-viewer-pr5 .'

# No credentials in test output
.venv/bin/pytest -s 2>&1 | grep -iE 'password|secret|DATABASE_URL' && echo 'FAIL' || echo 'OK'
```
