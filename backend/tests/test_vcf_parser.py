from app.lib.vcf_parser import parse_vcf, VcfVariant, VcfMeta

_VEP_HEADER = (
    '##fileformat=VCFv4.2\n'
    '##source=DRAGENv4.2\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="VEP ... Format: Allele|Consequence|SYMBOL|Gene|HGVSc|HGVSp|gnomADe_AF|REVEL|SpliceAI_pred_DS_AG|SpliceAI_pred_DS_AL|SpliceAI_pred_DS_DG|SpliceAI_pred_DS_DL|CLIN_SIG|CANONICAL">\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t100\t.\tA\tG\t50.0\tPASS\tCSQ=G|missense_variant|BRCA1|ENSG001|c.100A>G|p.Thr34Ala|0.0001|0.75|0.1|0.2|0.05|0.3|Pathogenic|YES\n'
)

_MULTI_ALLELIC = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '1\t200\t.\tA\tG,T\t.\t.\t.\n'
)

_FLAT_CSQ = (
    '##fileformat=VCFv4.2\n'
    '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'
    '3\t400\t.\tG\tA\t.\t.\tCSQ_SYMBOL=BRCA2;CSQ_Consequence=frameshift_variant;CSQ_gnomADe_AF=0.0002;CSQ_REVEL=0.8\n'
)


def _collect(vcf_text: str) -> tuple[list[VcfVariant], VcfMeta]:
    variants: list[VcfVariant] = []
    meta = parse_vcf(vcf_text.splitlines(), on_variant=variants.append)
    return variants, meta


def test_vep_basic_fields():
    variants, meta = _collect(_VEP_HEADER)
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


def test_vep_spliceai_max():
    # DS_AG=0.1, DS_AL=0.2, DS_DG=0.05, DS_DL=0.3 → max=0.3
    variants, _ = _collect(_VEP_HEADER)
    assert abs(variants[0].spliceai_max - 0.3) < 1e-9


def test_pipeline_detected_from_header():
    _, meta = _collect(_VEP_HEADER)
    assert meta.pipeline_key == "dragen_germline"


def test_multi_allelic_split():
    variants, _ = _collect(_MULTI_ALLELIC)
    assert len(variants) == 2
    assert {v.alt for v in variants} == {"G", "T"}


def test_missing_qual_becomes_none():
    variants, _ = _collect(_MULTI_ALLELIC)
    assert all(v.qual is None for v in variants)


def test_flat_csq_fields():
    variants, _ = _collect(_FLAT_CSQ)
    assert len(variants) == 1
    v = variants[0]
    assert v.gene == "BRCA2"
    assert v.consequence == "frameshift_variant"
    assert abs(v.gnomad_af - 0.0002) < 1e-9
    assert abs(v.revel_score - 0.8) < 1e-9


def test_spanning_deletion_skipped():
    lines = [
        "##fileformat=VCFv4.2",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        "1\t500\t.\tATG\tA,*\t.\t.\t.",
    ]
    variants: list[VcfVariant] = []
    parse_vcf(lines, on_variant=variants.append)
    assert len(variants) == 1
    assert variants[0].alt == "A"


def test_header_lines_captured():
    _, meta = _collect(_VEP_HEADER)
    assert any("fileformat" in l for l in meta.header_lines)
