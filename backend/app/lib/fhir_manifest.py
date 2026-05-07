"""FHIR R4 Bundle manifest parser and builder for VCF sidecar files.

Each VCF upload to the ingest S3 bucket is accompanied by a JSON sidecar
manifest structured as a FHIR R4 Bundle (type: collection) containing
exactly one Patient, one Specimen, and one Task resource.  This module
parses that bundle into a typed ``ParsedManifest`` and can reconstruct a
minimal bundle from typed fields via ``build_manifest()``.

Constants
---------
NHS_LAB_SYSTEM
    Placeholder system URI for Patient lab-number identifiers.  Must be
    replaced with the canonical GLH URI before go-live.
CASE_TYPE_EXT
    Placeholder extension URL for the Specimen case-type extension.
    Must be replaced with the canonical StructureDefinition URL agreed
    with East Genomics / GLH.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# TODO: Replace with the East Genomics canonical lab identifier system URI (agree with GLH)
NHS_LAB_SYSTEM = "https://fhir.example-lab.org/Id/lab-number"
# TODO: Replace with the canonical StructureDefinition URL agreed with East Genomics / GLH
CASE_TYPE_EXT  = "https://example.org/fhir/StructureDefinition/case-type"


@dataclass
class ManifestPatient:
    """Patient fields extracted from the FHIR Patient resource."""

    lab_number: str
    name: str | None


@dataclass
class ManifestSpecimen:
    """Specimen fields extracted from the FHIR Specimen resource."""

    sample_name: str
    case_type: Literal["germline", "somatic"]
    tissue: str | None
    sequencing_date: str | None   # "YYYY-MM-DD"


@dataclass
class ManifestTask:
    """Pipeline task fields extracted from the FHIR Task resource."""

    pipeline_key: str | None
    pipeline_version: str | None
    run_id: str | None
    vcf_filename: str | None


@dataclass
class ParsedManifest:
    """Typed result of parsing a FHIR R4 Bundle sidecar manifest."""

    patient: ManifestPatient
    specimen: ManifestSpecimen
    task: ManifestTask


def _dict_items(value: Any) -> list[dict[str, Any]]:
    """Return value as a filtered list of dicts; silently drops non-dict entries."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _find_resource(bundle: dict, rtype: str) -> dict | None:
    """Return the first FHIR resource of *rtype* from *bundle*, or ``None``.

    Skips any ``entry`` items that are not dicts or whose ``resource``
    value is not a dict, rather than raising on malformed input.
    """
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        r = entry.get("resource")
        if not isinstance(r, dict):
            continue
        if r.get("resourceType") == rtype:
            return r
    return None


def parse_manifest(raw: Any, *, source: str | None = None) -> ParsedManifest:
    """Parse a FHIR R4 Bundle dict into a typed ``ParsedManifest``.

    Args:
        raw: The decoded JSON object (must be a FHIR R4 Bundle of type
            ``"collection"``).
        source: Optional label (e.g. an S3 key) prepended to error
            messages to aid debugging.

    Returns:
        A ``ParsedManifest`` with patient, specimen, and task fields
        populated from the bundle.

    Raises:
        ValueError: If *raw* is not a valid Bundle, or if any required
            identifier / extension is absent or invalid.
    """
    prefix = f"[{source}] " if source else ""
    if not isinstance(raw, dict):
        raise ValueError(f"{prefix}Manifest must be a FHIR R4 Bundle (type: collection)")
    if raw.get("resourceType") != "Bundle" or raw.get("type") != "collection":
        raise ValueError(f"{prefix}Manifest must be a FHIR R4 Bundle (type: collection)")

    patient_res  = _find_resource(raw, "Patient")
    specimen_res = _find_resource(raw, "Specimen")
    task_res     = _find_resource(raw, "Task")

    if not patient_res:
        raise ValueError(f"{prefix}Manifest missing Patient resource")
    if not specimen_res:
        raise ValueError(f"{prefix}Manifest missing Specimen resource")
    if not task_res:
        raise ValueError(f"{prefix}Manifest missing Task resource")

    # Patient — lab number
    identifiers = _dict_items(patient_res.get("identifier"))
    lab_id  = next((i for i in identifiers if i.get("system") == NHS_LAB_SYSTEM), None)
    no_sys  = next((i for i in identifiers if not i.get("system")), None)
    lab_number = (lab_id or no_sys or {}).get("value")
    if not lab_number:
        raise ValueError(f"{prefix}Patient manifest missing lab number identifier")

    # Patient — name
    name_entry = next(iter(_dict_items(patient_res.get("name"))), {})
    given_names: list[str] = name_entry.get("given", [])
    family = name_entry.get("family", "")
    name = " ".join(p for p in [*given_names, family] if p).strip() or None

    # Specimen — case_type
    case_type_ext = next(
        (e for e in _dict_items(specimen_res.get("extension")) if e.get("url") == CASE_TYPE_EXT), None
    )
    if case_type_ext is None:
        raise ValueError(f"{prefix}Specimen manifest missing case-type extension")
    case_type_raw = case_type_ext.get("valueCode")
    if case_type_raw not in ("germline", "somatic"):
        raise ValueError(f"{prefix}Invalid case_type: {case_type_raw!r} (must be 'germline' or 'somatic')")
    case_type: Literal["germline", "somatic"] = case_type_raw

    # Specimen — sample name: fail loud rather than synthesising "unknown"
    sample_name = next(
        (i.get("value") for i in _dict_items(specimen_res.get("identifier")) if i.get("value")),
        None,
    )
    if not sample_name:
        raise ValueError(f"{prefix}Specimen manifest missing sample identifier")
    specimen_type = specimen_res.get("type")
    if not isinstance(specimen_type, dict):
        specimen_type = {}
    coding = next(iter(_dict_items(specimen_type.get("coding"))), {})
    tissue = coding.get("display") or specimen_type.get("text")
    collected = specimen_res.get("collection", {}).get("collectedDateTime", "")
    sequencing_date = collected.split("T")[0] if collected else None

    # Task
    pipeline_key: str | None = (task_res.get("code") or {}).get("text")
    pipeline_version = next(
        (i.get("valueString") for i in _dict_items(task_res.get("input"))
         if i.get("type", {}).get("text") == "pipeline_version"),
        None,
    )
    run_id = next(
        (i.get("value") for i in _dict_items(task_res.get("identifier")) if i.get("value")),
        None,
    )
    vcf_output = next(
        (o.get("valueString") for o in _dict_items(task_res.get("output"))
         if o.get("type", {}).get("text") == "vcf"),
        None,
    )

    return ParsedManifest(
        patient=ManifestPatient(
            lab_number=lab_number,
            name=name,
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
    """Build a minimal FHIR R4 Bundle dict from typed manifest fields.

    The returned bundle passes ``parse_manifest()`` round-trip validation
    but is intentionally minimal — only fields present in the typed
    dataclasses are included.
    """
    patient_resource: dict[str, Any] = {
        "resourceType": "Patient",
        "identifier": [{"system": NHS_LAB_SYSTEM, "value": patient.lab_number}],
    }
    if patient.name:
        parts = patient.name.split(" ")
        family = parts[-1] if parts else ""
        given = parts[:-1] if len(parts) > 1 else []
        patient_resource["name"] = [{"family": family, "given": given}]

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
