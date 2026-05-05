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
    assert "acgs_snv" in Framework.__args__
    assert "very_strong" in Strength.__args__
    assert "germline" in CaseType.__args__
    assert "pending" in WorkflowStatus.__args__
    assert "Pathogenic" in Classification.__args__
