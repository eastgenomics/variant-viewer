"""
test_vcf_parser.py — PR 5 (cyvcf2 API)

All tests write real VCF files to tmp_path and call parse_vcf(path, ...).
"""
import pytest
from pathlib import Path
from app.lib.vcf_parser import parse_vcf, VcfVariant, VcfMeta

# ---------------------------------------------------------------------------
# VCF content fixtures
# ---------------------------------------------------------------------------

_VEP_CONTENT = (
    "##fileformat=VCFv4.2\n"
    "##source=DRAGENv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="VEP ... Format: '
    "Allele|Consequence|SYMBOL|Gene|HGVSc|HGVSp|gnomADe_AF|REVEL|"
    "SpliceAI_pred_DS_AG|SpliceAI_pred_DS_AL|SpliceAI_pred_DS_DG|SpliceAI_pred_DS_DL|"
    'CLIN_SIG|CANONICAL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "1\t100\t.\tA\tG\t50.0\tPASS\t"
    "CSQ=G|missense_variant|BRCA1|ENSG001|c.100A>G|p.Thr34Ala"
    "|0.0001|0.75|0.1|0.2|0.05|0.3|Pathogenic|YES\n"
)

_MULTI_ALLELIC_CONTENT = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "1\t200\t.\tA\tG,T\t.\t.\t.\n"
)

_FLAT_CSQ_CONTENT = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "3\t400\t.\tG\tA\t.\t.\t"
    "CSQ_SYMBOL=BRCA2;CSQ_Consequence=frameshift_variant;"
    "CSQ_gnomADe_AF=0.0002;CSQ_REVEL=0.8\n"
)

_SPANNING_DEL_CONTENT = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "1\t500\t.\tATG\tA,*\t.\t.\t.\n"
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def _collect(path: Path) -> tuple[list[VcfVariant], VcfMeta]:
    variants: list[VcfVariant] = []
    meta = parse_vcf(path, on_variant=variants.append)
    return variants, meta


# ---------------------------------------------------------------------------
# VEP CSQ annotation
# ---------------------------------------------------------------------------

def test_vep_basic_fields(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 1
    v = variants[0]
    assert v.chrom == "1"
    assert v.pos == 100
    assert v.ref == "A"
    assert v.alt == "G"
    assert v.qual == 50.0
    assert v.filter == "PASS"
    assert v.gene == "BRCA1"
    assert v.consequence == "missense_variant"
    assert v.hgvs_c == "c.100A>G"
    assert v.hgvs_p == "p.Thr34Ala"
    assert abs(v.gnomad_af - 0.0001) < 1e-9
    assert abs(v.revel_score - 0.75) < 1e-9
    assert v.clinvar_sig == "Pathogenic"


def test_vep_spliceai_max(tmp_path):
    # DS_AG=0.1, DS_AL=0.2, DS_DG=0.05, DS_DL=0.3 → max=0.3
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    variants, _ = _collect(p)
    assert abs(variants[0].spliceai_max - 0.3) < 1e-9


def test_pipeline_detected_from_header(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    _, meta = _collect(p)
    assert meta.pipeline_key == "dragen_germline"


# ---------------------------------------------------------------------------
# Multi-allelic splitting
# ---------------------------------------------------------------------------

def test_multi_allelic_split(tmp_path):
    p = _write(tmp_path, "multi.vcf", _MULTI_ALLELIC_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 2
    assert {v.alt for v in variants} == {"G", "T"}


def test_missing_qual_becomes_none(tmp_path):
    p = _write(tmp_path, "multi.vcf", _MULTI_ALLELIC_CONTENT)
    variants, _ = _collect(p)
    assert all(v.qual is None for v in variants)


# ---------------------------------------------------------------------------
# Flat CSQ_* fields
# ---------------------------------------------------------------------------

def test_flat_csq_fields(tmp_path):
    p = _write(tmp_path, "flat.vcf", _FLAT_CSQ_CONTENT)
    variants, _ = _collect(p)
    assert len(variants) == 1
    v = variants[0]
    assert v.gene == "BRCA2"
    assert v.consequence == "frameshift_variant"
    assert abs(v.gnomad_af - 0.0002) < 1e-9
    assert abs(v.revel_score - 0.8) < 1e-9


# ---------------------------------------------------------------------------
# Spanning deletion skipped
# ---------------------------------------------------------------------------

def test_spanning_deletion_skipped(tmp_path):
    p = _write(tmp_path, "span.vcf", _SPANNING_DEL_CONTENT)
    variants: list[VcfVariant] = []
    parse_vcf(p, on_variant=variants.append)
    assert len(variants) == 1
    assert variants[0].alt == "A"


# ---------------------------------------------------------------------------
# Header lines captured in VcfMeta
# ---------------------------------------------------------------------------

def test_header_lines_captured(tmp_path):
    p = _write(tmp_path, "vep.vcf", _VEP_CONTENT)
    _, meta = _collect(p)
    assert any("fileformat" in line for line in meta.header_lines)
