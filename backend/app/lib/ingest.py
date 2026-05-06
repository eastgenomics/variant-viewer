from __future__ import annotations

import psycopg2.extensions


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
