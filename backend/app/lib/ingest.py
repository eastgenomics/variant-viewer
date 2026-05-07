from __future__ import annotations

import psycopg2.extensions


class DuplicateSubmissionError(Exception):
    """Raised when a VCF submission would duplicate an existing ingest record.

    Attributes:
        duplicate_type: always ``"exact"`` — the same ``s3_key`` is already
            present in the ``samples`` table.  Multiple VCFs for the same
            patient + specimen are permitted (e.g. different gene panels); only
            re-uploading the identical VCF file is rejected.
        existing_sample_id: primary key of the conflicting ``samples`` row,
            or ``-1`` when the conflict was detected via a DB
            ``UniqueViolation`` (TOCTOU race) and the row ID is unavailable.
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
    """Verify that a proposed ingest is not a re-upload of an existing VCF.

    Checks for an **exact duplicate**: a ``samples`` row whose ``s3_key``
    matches the proposed key.  The ``samples.s3_key`` column has a UNIQUE
    constraint, so the DB would raise ``UniqueViolation`` regardless; this
    check surfaces a richer error message before any INSERT is attempted.

    Multiple VCFs for the same patient and specimen (e.g. different gene
    panels) are explicitly *allowed* — the ``samples`` table intentionally has
    no unique constraint on ``(patient_id, name)``.

    Args:
        s3_key:      S3 object key of the VCF being ingested.
        lab_number:  Patient lab number (unused in the check; kept in the
                     signature so callers don't need to change when context
                     is logged in future).
        sample_name: Specimen name (unused in the check; same reason).
        conn:        Active psycopg2 connection.

    Raises:
        DuplicateSubmissionError: if a ``samples`` row with this ``s3_key``
            already exists.

    Note:
        This check has a TOCTOU race window.  Two concurrent ingests of the
        same file can both pass before either INSERT runs; the loser receives
        ``psycopg2.errors.UniqueViolation`` from the DB.  Callers must catch
        ``UniqueViolation`` and treat it as
        ``DuplicateSubmissionError(duplicate_type="exact")``.
    """
    with conn.cursor() as cur:
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
