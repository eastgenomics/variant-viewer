from app.lib.pipeline_config import (
    get_pipeline_config, get_pipeline_keys, get_default_filters, detect_pipeline_key,
)


def test_all_pipelines_loaded():
    keys = get_pipeline_keys()
    assert "dragen_germline" in keys
    assert "dragen_somatic" in keys
    assert "gatk_haplotypecaller" in keys
    assert "mutect2" in keys
    assert "strelka2" in keys
    assert "unknown" in keys


def test_pipeline_config_label():
    cfg = get_pipeline_config("dragen_germline")
    assert cfg is not None
    assert cfg.label == "DRAGEN Germline v3"


def test_pipeline_config_missing_key():
    assert get_pipeline_config("nonexistent") is None


def test_default_filters_gnomad():
    f = get_default_filters("dragen_germline")
    assert f.gnomad_af_max == 0.01
    assert "missense_variant" in f.consequences


def test_default_filters_fallback():
    f = get_default_filters("nonexistent")
    assert f.gnomad_af_max == 0.01


def test_detect_dragen():
    headers = ["##fileformat=VCFv4.2", "##source=DRAGENv4.2"]
    assert detect_pipeline_key(headers) == "dragen_germline"


def test_detect_haplotypecaller():
    assert detect_pipeline_key(["##source=HaplotypeCallerv4.5"]) == "gatk_haplotypecaller"


def test_detect_mutect2():
    assert detect_pipeline_key(["##source=Mutect2 v4.4"]) == "mutect2"


def test_detect_strelka():
    assert detect_pipeline_key(["##source=strelka-2.9.10"]) == "strelka2"


def test_detect_unknown_headers():
    assert detect_pipeline_key(["##fileformat=VCFv4.2"]) is None


def test_detect_case_insensitive():
    assert detect_pipeline_key(["##source=DRAGEN pipeline"]) == "dragen_germline"
