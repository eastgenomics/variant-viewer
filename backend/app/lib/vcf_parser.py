"""VCF / BCF parser backed by cyvcf2 (htslib).

Parses a VCF or BCF file, extracts per-variant annotation from VEP CSQ
or flat ``CSQ_*`` INFO fields, detects the originating sequencing
pipeline from ``##source`` / ``##pipeline`` header lines, and invokes an
optional callback for each parsed variant.

Primary entry point
-------------------
parse_vcf(path, on_variant)
    Parse *path* and call *on_variant* for each emitted ``VcfVariant``.
    Returns a ``VcfMeta`` containing the detected pipeline key and raw
    header lines.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

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
    lines: Iterable[str],
    on_variant: Callable[[VcfVariant], None] | None = None,
) -> VcfMeta:
    """Parse a VCF stream and emit one ``VcfVariant`` per ALT allele.

    Args:
        lines: Iterable of raw VCF text lines (with or without newlines).
        on_variant: Optional callback invoked for each parsed variant.
            If omitted the variants are silently consumed; callers that
            want to collect them should pass ``variants.append``.

    Returns:
        A ``VcfMeta`` containing the detected pipeline key (or ``None``
        if the header does not match any known pattern) and all
        ``##``-prefixed header lines.
    """
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

        chrom      = cols[0]
        pos_str    = cols[1]
        ref        = cols[3]
        alt_field  = cols[4]
        qual_str   = cols[5]
        filter_str = cols[6]
        info_str   = cols[7]

        try:
            pos = int(pos_str)
        except ValueError:
            logger.warning("vcf_parser: skipping line with non-integer POS %r", pos_str)
            continue

        qual: float | None       = None if qual_str == "." else _try_float(qual_str)
        filter_val: str | None   = None if filter_str == "." else filter_str
        info = _parse_info(info_str)

        for alt in alt_field.split(","):
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
                chrom=chrom,
                pos=pos,
                ref=ref,
                alt=alt,
                qual=qual,
                filter=filter_val,
                info_json=dict(info),
                **annotations,
            )
            if on_variant:
                on_variant(variant)

    pipeline_key = detect_pipeline_key(header_lines)
    return VcfMeta(pipeline_key=pipeline_key, header_lines=header_lines)
