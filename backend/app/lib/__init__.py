"""Business-logic library modules for the Variant Viewer backend.

Exported modules
----------------
models
    Pydantic entities mirroring the database schema.
db
    psycopg2 connection pool and transaction helpers.
pipeline_config
    Pipeline configuration loader and header-based detection.
fhir_manifest
    FHIR R4 Bundle manifest parser and builder.
vcf_parser
    VCF / BCF parser backed by cyvcf2.
classification_engine
    Tavtigian point-based variant classification (ACGS SNV / SVIG-UK).
pre_compute_criteria
    Rule-based pre-computation of classification criteria from VCF fields.
ingest
    Idempotency guard for VCF ingest submissions.
"""
