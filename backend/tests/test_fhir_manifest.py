import pytest
from app.lib.fhir_manifest import (
    parse_manifest, build_manifest,
    ManifestPatient, ManifestSpecimen, ManifestTask, ParsedManifest,
)

_EXAMPLE = {
    "resourceType": "Bundle", "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient",
            "identifier": [{"system": "https://fhir.example-lab.org/Id/lab-number", "value": "LAB-2024-00123"}]}},
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
    patient = ManifestPatient(lab_number="LAB-999", name="Test User")
    specimen = ManifestSpecimen(sample_name="S001", case_type="germline", tissue=None, sequencing_date=None)
    task = ManifestTask(pipeline_key="dragen_germline", pipeline_version="4.2", run_id="R1", vcf_filename=None)
    bundle = build_manifest(patient, specimen, task)
    m = parse_manifest(bundle)
    assert m.patient.lab_number == "LAB-999"
    assert m.specimen.case_type == "germline"
    assert m.task.pipeline_key == "dragen_germline"


def test_missing_sample_identifier_raises():
    no_id = {**_EXAMPLE, "entry": [
        _EXAMPLE["entry"][0],
        {"resource": {"resourceType": "Specimen", "identifier": [],
            "extension": [{"url": "https://example.org/fhir/StructureDefinition/case-type",
                           "valueCode": "germline"}]}},
        _EXAMPLE["entry"][2],
    ]}
    with pytest.raises(ValueError, match="missing sample identifier"):
        parse_manifest(no_id)


def test_parse_manifest_source_prefix_in_errors():
    with pytest.raises(ValueError, match=r"\[sample\.vcf\.gz\]"):
        parse_manifest({"resourceType": "Bundle", "type": "wrong"}, source="sample.vcf.gz")
