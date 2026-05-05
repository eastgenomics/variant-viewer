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
