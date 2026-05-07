from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import psycopg2.extensions

from app.lib.classification_engine import get_framework_version, select_framework
from app.lib.fhir_manifest import parse_manifest
from app.lib.pre_compute_criteria import pre_compute_criteria
from app.lib.vcf_parser import VcfVariant, parse_vcf

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "manifest-schema.json"
_MANIFEST_SCHEMA: dict = json.loads(_SCHEMA_PATH.read_text())


class DuplicateSubmissionError(Exception):
    """Raised when a VCF submission would duplicate an existing ingest record.

    Attributes:
        duplicate_type: "exact"  — same s3_key already in samples table.
                        "near"   — same lab_number + sample_name, different VCF.
        existing_sample_id: primary key of the conflicting samples row.
    """

    def __init__(
        self,
        message: str,
        existing_sample_id: int,
        duplicate_type: str,
    ) -> None:
        super().__init__(message)
        self.existing_sample_id = existing_sample_id
        self.duplicate_type = duplicate_type


def check_idempotency(
    s3_key: str,
    lab_number: str,
    sample_name: str,
    conn: psycopg2.extensions.connection,
) -> None:
    """Verify that a proposed ingest is not a duplicate of an existing record.

    Checks in order:

    1. **Exact duplicate** — a Sample with this ``s3_key`` already exists.
       The ``samples.s3_key`` column has a UNIQUE constraint, so the DB would
       raise ``UniqueViolation`` anyway; this check surfaces a richer error
       message before any INSERT is attempted.

    2. **Near-duplicate** — a Sample with the same ``lab_number`` and
       ``sample_name`` (but a *different* VCF) was already ingested.  This
       catches reprocessed or re-uploaded cases where the operator may not
       realise a previous ingest exists.  The existing record must be
       explicitly superseded (out of scope here) before a new ingest proceeds.

    Raises:
        DuplicateSubmissionError: if either check finds a matching record.

    Note:
        This check has a TOCTOU race window. Two concurrent ingests of the
        same file can both pass this check before either INSERT runs; one will
        then receive ``psycopg2.errors.UniqueViolation`` from the DB.
        Callers must also catch ``UniqueViolation`` and treat it as equivalent
        to ``DuplicateSubmissionError(duplicate_type="exact")``.
    """
    with conn.cursor() as cur:
        # --- 1. Exact duplicate: same s3_key ---
        cur.execute(
            "SELECT id FROM samples WHERE s3_key = %s",
            (s3_key,),
        )
        row = cur.fetchone()
        if row:
            raise DuplicateSubmissionError(
                f"VCF already ingested: s3_key={s3_key!r} exists as "
                f"sample id={row[0]}. Each VCF file may only be ingested once.",
                existing_sample_id=row[0],
                duplicate_type="exact",
            )

        # --- 2. Near-duplicate: same patient + sample, different VCF ---
        cur.execute(
            """
            SELECT s.id, s.s3_key
              FROM samples s
              JOIN patients p ON s.patient_id = p.id
             WHERE p.lab_number = %s
               AND s.name = %s
            """,
            (lab_number, sample_name),
        )
        row = cur.fetchone()
        if row:
            raise DuplicateSubmissionError(
                f"A VCF for lab_number={lab_number!r}, sample={sample_name!r} "
                f"was already ingested as sample id={row[0]} "
                f"(s3_key={row[1]!r}). To reprocess this case, the existing "
                f"record must be explicitly superseded before a new ingest.",
                existing_sample_id=row[0],
                duplicate_type="near",
            )


def ingest_sample(
    vcf_s3_key: str,
    manifest_s3_key: str,
    bucket: str,
    s3_client: Any,
    conn: psycopg2.extensions.connection,
) -> int:
    """Download, validate, parse, and persist a VCF + manifest from S3.

    Returns the new sample_id (int) on success.

    Raises:
        ValueError: key format invalid or FHIR manifest structurally wrong.
        jsonschema.ValidationError: manifest JSON does not match the schema.
        DuplicateSubmissionError: submission would duplicate an existing record.
        psycopg2.OperationalError: DB failure.
    """
    # 1. Validate VCF key format
    if not (vcf_s3_key.endswith(".vcf") or vcf_s3_key.endswith(".vcf.gz")):
        raise ValueError(f"Unsupported VCF key format: {vcf_s3_key!r}")

    # 2-8. Download, validate, parse, and idempotency-check inside an
    # invocation-scoped temp directory - auto-cleaned on exit so warm Lambda
    # containers don't accumulate files and exhaust /tmp storage.
    with tempfile.TemporaryDirectory(prefix="ingest-") as tmp_dir:
        tmp = Path(tmp_dir)
        vcf_path      = tmp / Path(vcf_s3_key).name
        manifest_path = tmp / Path(manifest_s3_key).name

        # 3. Download from S3
        s3_client.download_file(bucket, vcf_s3_key, str(vcf_path))
        s3_client.download_file(bucket, manifest_s3_key, str(manifest_path))

        # 4-6. Load, validate, and parse manifest
        raw = json.loads(manifest_path.read_text())
        jsonschema.validate(raw, _MANIFEST_SCHEMA)   # raises ValidationError on bad manifest
        manifest = parse_manifest(raw)               # raises ValueError on structural errors

        lab_number  = manifest.patient.lab_number
        sample_name = manifest.specimen.sample_name
        case_type   = manifest.specimen.case_type

        # 7. Idempotency check — must run before any INSERT
        check_idempotency(vcf_s3_key, lab_number, sample_name, conn)

        # 8. Parse VCF (cyvcf2) - file access ends here
        variants: list[VcfVariant] = []
        meta = parse_vcf(vcf_path, on_variant=variants.append)
    # TemporaryDirectory cleaned up; variants + meta are plain Python objects

    logger.info(
        "ingest_sample: vcf=%s pipeline=%s variants=%d",
        vcf_s3_key, meta.pipeline_key, len(variants),
    )

    # 9. DB writes (conn is already inside a transaction from caller)
    # Catch UniqueViolation to handle the TOCTOU race documented in
    # check_idempotency(): two concurrent ingests can both pass the pre-check
    # before either INSERT runs; the loser gets UniqueViolation from the DB.
    try:
        with conn.cursor() as cur:
            # 9a. Upsert patient by lab_number
            cur.execute(
                """
                INSERT INTO patients (lab_number, name, dob)
                VALUES (%s, %s, %s)
                ON CONFLICT (lab_number) DO UPDATE
                  SET name = COALESCE(EXCLUDED.name, patients.name),
                      dob  = COALESCE(EXCLUDED.dob,  patients.dob)
                RETURNING id
                """,
                (lab_number, manifest.patient.name, None),
            )
            patient_id: int = cur.fetchone()[0]

            # 9b. Insert sample
            pipeline_key = meta.pipeline_key or manifest.task.pipeline_key
            cur.execute(
                """
                INSERT INTO samples
                  (patient_id, name, vcf_filename, s3_key, pipeline_key,
                   case_type, tissue, sequencing_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    patient_id,
                    sample_name,
                    manifest.task.vcf_filename or Path(vcf_s3_key).name,
                    vcf_s3_key,
                    pipeline_key,
                    case_type,
                    manifest.specimen.tissue,
                    manifest.specimen.sequencing_date,
                ),
            )
            sample_id: int = cur.fetchone()[0]

            # 9c. Insert variants + pre-computed criteria
            for variant in variants:
                cur.execute(
                    """
                    INSERT INTO variants
                      (sample_id, chrom, pos, ref, alt, qual, filter, gene,
                       consequence, hgvs_c, hgvs_p, gnomad_af, clinvar_sig,
                       revel_score, spliceai_max, info_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        sample_id,
                        variant.chrom, variant.pos, variant.ref, variant.alt,
                        variant.qual, variant.filter, variant.gene,
                        variant.consequence, variant.hgvs_c, variant.hgvs_p,
                        variant.gnomad_af, variant.clinvar_sig,
                        variant.revel_score, variant.spliceai_max,
                        json.dumps(variant.info_json),
                    ),
                )
                variant_id: int = cur.fetchone()[0]

                # Create pending classification shell for pre-computed criteria
                framework, _ = select_framework(case_type, variant.gene)
                framework_version = get_framework_version(framework)
                cur.execute(
                    """
                    INSERT INTO variant_classification
                      (variant_id, framework, framework_version)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (variant_id, framework, framework_version),
                )
                classification_id: int = cur.fetchone()[0]

                suggestions = pre_compute_criteria(variant, case_type)
                for suggestion in suggestions:
                    cur.execute(
                        """
                        INSERT INTO classification_criterion
                          (classification_id, criterion_code, applied,
                           strength, pre_computed, pre_computed_value)
                        VALUES (%s, %s, FALSE, %s, TRUE, %s)
                        """,
                        (
                            classification_id,
                            suggestion.criterion_code,
                            suggestion.suggested_strength,
                            suggestion.pre_computed_value,
                        ),
                    )

            # 9d. Insert workflow record
            cur.execute(
                "INSERT INTO workflow (sample_id) VALUES (%s)",
                (sample_id,),
            )

    except psycopg2.errors.UniqueViolation as exc:
        raise DuplicateSubmissionError(
            f"VCF already ingested (concurrent ingest race): s3_key={vcf_s3_key!r}",
            existing_sample_id=-1,
            duplicate_type="exact",
        ) from exc

    return sample_id
