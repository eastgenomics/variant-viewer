"""VCF / BCF parser backed by cyvcf2 (htslib).

Parses a VCF or BCF file, extracts per-variant annotation from VEP CSQ
or flat ``CSQ_*`` INFO fields, detects the originating sequencing
pipeline from ``##source`` / ``##pipeline`` header lines, and invokes an
optional callback for each parsed variant.

Note on INFO field extraction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
cyvcf2 ``v.INFO.keys()`` only enumerates fields declared in the VCF
header; it silently omits flat ``CSQ_*`` keys that East Genomics
pipelines emit without header declarations.  This module works around
the limitation by parsing the raw INFO column string directly.

Primary entry point
-------------------
parse_vcf(path, on_variant)
    Parse *path* and call *on_variant* for each emitted ``VcfVariant``.
    Returns a ``VcfMeta`` containing the detected pipeline key and raw
    header lines.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cyvcf2

from app.lib.pipeline_config import detect_pipeline_key

logger = logging.getLogger(__name__)


@dataclass
class VcfVariant:
    """Parsed representation of a single ALT allele from a VCF data line.

    Multi-allelic sites are split so that each ``VcfVariant`` carries
    exactly one ALT allele.  Spanning deletions (``*``) are skipped.
    Annotation fields are populated from VEP CSQ or flat ``CSQ_*`` INFO
    fields; fields absent from the annotation are ``None``.
    """
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
    """Metadata produced after a complete VCF file has been parsed."""

    pipeline_key: str | None
    header_lines: list[str]


def _parse_info(info_str: str) -> dict[str, str | bool]:
    """Parse a VCF INFO column string into a key-value dict.

    Flag fields (no ``=`` sign) map to ``True``.  Returns an empty dict
    for ``"."`` or an empty string.
    """
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


_SPLICE_KEYS = [
    "SpliceAI_pred_DS_AG", "SpliceAI_pred_DS_AL",
    "SpliceAI_pred_DS_DG", "SpliceAI_pred_DS_DL",
]
_FLAT_SPLICE_KEYS = [f"CSQ_{k}" for k in _SPLICE_KEYS]


def _csq_field(entry: str, idx: int) -> str:
    """Safely return a pipe-separated field from a CSQ entry; returns '' if out of range."""
    parts = entry.split("|")
    return parts[idx] if 0 <= idx < len(parts) else ""


def _spliceai_max(scores: list[str]) -> float | None:
    """Return the maximum finite SpliceAI delta score from *scores*, or ``None``.

    Skips empty strings, ``"."`` placeholders, and IEEE 754 NaN values.
    """
    vals = []
    for s in scores:
        if s and s not in (".", ""):
            try:
                v = float(s)
                if v == v:  # NaN != NaN in IEEE 754 — intentionally filters NaN SpliceAI scores
                    vals.append(v)
            except ValueError:
                pass
    return max(vals) if vals else None


def _try_float(s: str) -> float | None:
    """Return *s* parsed as a float, or ``None`` if conversion fails."""
    try:
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def _extract_vep(info: dict, csq_header: list[str], alt: str) -> dict:
    """Extract annotation fields from a VEP CSQ INFO value.

    Selects the most appropriate CSQ entry for *alt*: first filters to
    allele-matching entries, then prefers the canonical transcript
    (``CANONICAL=YES``), falling back to the first entry overall.

    Args:
        info: Parsed INFO dict containing a ``"CSQ"`` key.
        csq_header: Ordered field names from the ``##INFO=<ID=CSQ,...Format:>``
            header line.
        alt: The ALT allele string to match against the ``Allele`` field.

    Returns:
        A dict with keys ``gene``, ``consequence``, ``hgvs_c``,
        ``hgvs_p``, ``gnomad_af``, ``clinvar_sig``, ``revel_score``,
        ``spliceai_max``, all typed as ``float | str | None``.
    """
    empty: dict = {k: None for k in [
        "gene", "consequence", "hgvs_c", "hgvs_p",
        "gnomad_af", "clinvar_sig", "revel_score", "spliceai_max",
    ]}
    csq_str = info.get("CSQ")
    if not isinstance(csq_str, str):
        return empty

    entries = csq_str.split(",")
    allele_idx = csq_header.index("Allele")   if "Allele"    in csq_header else -1
    canon_idx  = csq_header.index("CANONICAL") if "CANONICAL" in csq_header else -1

    matched = [e for e in entries if allele_idx >= 0 and _csq_field(e, allele_idx) == alt]
    pool = matched if matched else entries
    preferred = next(
        (e for e in pool if canon_idx >= 0 and _csq_field(e, canon_idx) == "YES"),
        pool[0],
    )

    flds = preferred.split("|")

    def get(name: str) -> str:
        i = csq_header.index(name) if name in csq_header else -1
        return flds[i] if 0 <= i < len(flds) else ""

    gnomad_raw = get("gnomADe_AF") or get("gnomAD_AF") or get("gnomADg_AF") or get("MAX_AF")
    revel_raw  = get("REVEL") or get("REVEL_score")
    sai_vals   = [get(k) for k in _SPLICE_KEYS]

    return {
        "gene":        get("SYMBOL") or get("Gene") or None,
        "consequence": get("Consequence") or None,
        "hgvs_c":      get("HGVSc") or None,
        "hgvs_p":      get("HGVSp") or None,
        "gnomad_af":   _try_float(gnomad_raw),
        "clinvar_sig": get("CLIN_SIG") or get("ClinVar_CLNSIG") or None,
        "revel_score": _try_float(revel_raw),
        "spliceai_max": _spliceai_max(sai_vals),
    }


def _extract_flat_csq(info: dict) -> dict:
    """Extract annotation fields from East Genomics flat ``CSQ_*`` INFO keys.

    Returns the same dict shape as ``_extract_vep()``.
    """
    def get(name: str) -> str:
        v = info.get(name, "")
        return v if isinstance(v, str) else ""

    gnomad_raw = get("CSQ_gnomADe_AF") or get("CSQ_gnomADg_AF")
    sai_vals   = [get(k) for k in _FLAT_SPLICE_KEYS]

    return {
        "gene":        get("CSQ_SYMBOL") or None,
        "consequence": get("CSQ_Consequence") or None,
        "hgvs_c":      get("CSQ_HGVSc") or None,
        "hgvs_p":      get("CSQ_HGVSp") or None,
        "gnomad_af":   _try_float(gnomad_raw),
        "clinvar_sig": get("CSQ_ClinVar_CLNSIG") or None,
        "revel_score": _try_float(get("CSQ_REVEL")),
        "spliceai_max": _spliceai_max(sai_vals),
    }


def parse_vcf(
    path: str | Path,
    on_variant: Callable[[VcfVariant], None] | None = None,
) -> VcfMeta:
    """Parse a VCF or BCF file using cyvcf2 and emit one variant per ALT allele.

    Uses cyvcf2 (htslib) for file I/O.  INFO fields are extracted from
    the raw VCF line string rather than through ``v.INFO.keys()`` because
    the cyvcf2 API silently omits undeclared INFO keys such as the flat
    ``CSQ_*`` fields produced by East Genomics pipelines.

    Args:
        path: Path to a VCF or BCF file.  BGZF-compressed files and BCF
            are supported natively by htslib.
        on_variant: Optional callback invoked for each parsed variant.
            Callers that want to collect variants should pass
            ``variants.append``.

    Returns:
        A ``VcfMeta`` containing the detected pipeline key (or ``None``
        if the header does not match any known pattern) and all
        ``##``-prefixed header lines.
    """
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

        # Build info dict from raw INFO string (reliable for declared AND
        # undeclared fields such as flat CSQ_* fields from East Genomics pipelines).
        # cyvcf2 v.INFO.keys() only enumerates header-declared keys, so we
        # parse the raw VCF line for complete coverage.
        raw_cols = str(v).rstrip("\n").split("\t")
        filter_raw = raw_cols[6] if len(raw_cols) > 6 else "."
        filter_val: str | None = None if filter_raw in (".", "") else filter_raw
        info_str = raw_cols[7] if len(raw_cols) > 7 else "."
        info: dict[str, Any] = _parse_info(info_str)

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
