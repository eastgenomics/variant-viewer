"""
Tests for config file integrity.

These tests verify that the JSON/YAML classification configuration files
were retained correctly during the scaffold refactor. They check structural
completeness, not logic — the classification engine tests in PR 4 will
provide golden-output coverage.
"""
import json
import pathlib
import pytest
import yaml

CONFIG = pathlib.Path(__file__).parent.parent / "config"

ACGS_SNV_CRITERIA_CODES = [
    "PVS1", "PVS1_RNA",
    "PS1", "PS2", "PS3", "PS4",
    "PM1", "PM2", "PM3", "PM4", "PM5", "PM6",
    "PP1", "PP2", "PP3", "PP4",
    "BA1",
    "BS1", "BS2", "BS3", "BS4",
    "BP1", "BP2", "BP3", "BP4", "BP5", "BP7", "BP7_RNA",
]

SVIG_CRITERIA_CODES = [
    "O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9", "O10", "O11",
    "B1", "B2", "B3", "B4", "B5", "B6", "B7",
]

CRITERION_REQUIRED_KEYS = {
    "code", "label", "category", "direction",
    "default_strength", "permitted_strengths", "adjustable",
    "description", "pre_computable",
}

CANVIG_EXPECTED_GENES = ["BRCA1", "BRCA2", "MLH1", "MSH2", "MSH6"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(filename):
    return json.loads((CONFIG / filename).read_text())

def load_yaml(filename):
    return yaml.safe_load((CONFIG / filename).read_text())


# ── File presence ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "acgs-snv-criteria.json",
    "svig-criteria.json",
    "canvig-gene-mtaf.json",
    "manifest-schema.json",
    "pipelines.yaml",
])
def test_config_file_exists(filename):
    assert (CONFIG / filename).exists(), f"{filename} missing from backend/config/"


# ── ACGS SNV criteria ──────────────────────────────────────────────────────────

class TestAcgsSnvCriteria:
    def setup_method(self):
        self.data = load_json("acgs-snv-criteria.json")

    def test_top_level_keys(self):
        for key in ("version", "framework", "criteria", "combination_rules", "thresholds"):
            assert key in self.data

    def test_framework_identifier(self):
        assert self.data["framework"] == "acgs_snv"

    def test_criteria_count(self):
        assert len(self.data["criteria"]) == 28

    def test_all_criterion_codes_present(self):
        codes = {c["code"] for c in self.data["criteria"]}
        for code in ACGS_SNV_CRITERIA_CODES:
            assert code in codes, f"Missing criterion code: {code}"

    def test_no_extra_criterion_codes(self):
        codes = {c["code"] for c in self.data["criteria"]}
        assert codes == set(ACGS_SNV_CRITERIA_CODES)

    @pytest.mark.parametrize("code", ACGS_SNV_CRITERIA_CODES)
    def test_criterion_has_required_keys(self, code):
        criterion = next(c for c in self.data["criteria"] if c["code"] == code)
        missing = CRITERION_REQUIRED_KEYS - criterion.keys()
        assert not missing, f"{code} missing keys: {missing}"

    def test_thresholds_pathogenic(self):
        t = self.data["thresholds"]
        assert t["pathogenic"] == 10
        assert t["benign"] == -7

    def test_thresholds_vus_range(self):
        t = self.data["thresholds"]
        assert t["vus_min"] == 0
        assert t["vus_max"] == 5

    def test_direction_values_valid(self):
        valid = {"pathogenic", "benign"}
        for c in self.data["criteria"]:
            assert c["direction"] in valid, \
                f"{c['code']} has invalid direction: {c['direction']}"


# ── SVIG criteria ──────────────────────────────────────────────────────────────

class TestSvigCriteria:
    def setup_method(self):
        self.data = load_json("svig-criteria.json")

    def test_top_level_keys(self):
        for key in ("version", "framework", "criteria", "combination_rules", "thresholds"):
            assert key in self.data

    def test_framework_identifier(self):
        assert self.data["framework"] == "svig"

    def test_criteria_count(self):
        assert len(self.data["criteria"]) == 18

    def test_all_criterion_codes_present(self):
        codes = {c["code"] for c in self.data["criteria"]}
        for code in SVIG_CRITERIA_CODES:
            assert code in codes, f"Missing criterion code: {code}"

    def test_no_extra_criterion_codes(self):
        codes = {c["code"] for c in self.data["criteria"]}
        assert codes == set(SVIG_CRITERIA_CODES)

    @pytest.mark.parametrize("code", SVIG_CRITERIA_CODES)
    def test_criterion_has_required_keys(self, code):
        criterion = next(c for c in self.data["criteria"] if c["code"] == code)
        missing = CRITERION_REQUIRED_KEYS - criterion.keys()
        assert not missing, f"{code} missing keys: {missing}"

    def test_thresholds_oncogenic(self):
        t = self.data["thresholds"]
        assert t["oncogenic"] == 10
        assert t["benign"] == -7

    def test_direction_values_valid(self):
        valid = {"oncogenic", "benign"}
        for c in self.data["criteria"]:
            assert c["direction"] in valid, \
                f"{c['code']} has invalid direction: {c['direction']}"


# ── CANVIg gene list ───────────────────────────────────────────────────────────

class TestCanvigGeneMtaf:
    def setup_method(self):
        self.data = load_json("canvig-gene-mtaf.json")

    def test_genes_key_present(self):
        assert "genes" in self.data

    def test_gene_count(self):
        assert len(self.data["genes"]) == 33

    @pytest.mark.parametrize("gene", CANVIG_EXPECTED_GENES)
    def test_expected_gene_present(self, gene):
        assert gene in self.data["genes"], f"{gene} missing from CANVIg gene list"

    def test_gene_entries_non_empty(self):
        for gene, value in self.data["genes"].items():
            assert value is not None, f"{gene} has null entry"


# ── Manifest schema ────────────────────────────────────────────────────────────

class TestManifestSchema:
    def setup_method(self):
        self.data = load_json("manifest-schema.json")

    def test_is_json_schema(self):
        assert "$schema" in self.data or "type" in self.data

    def test_has_properties(self):
        assert "properties" in self.data

    def test_has_required_fields(self):
        assert "required" in self.data
        assert len(self.data["required"]) > 0


# ── Pipelines YAML ─────────────────────────────────────────────────────────────

class TestPipelinesYaml:
    def setup_method(self):
        self.data = load_yaml("pipelines.yaml")

    def test_top_level_key(self):
        assert "pipelines" in self.data

    def test_pipelines_non_empty(self):
        assert len(self.data["pipelines"]) > 0

    def test_dragen_germline_present(self):
        assert "dragen_germline" in self.data["pipelines"]

    def test_each_pipeline_has_label(self):
        for name, pipeline in self.data["pipelines"].items():
            assert "label" in pipeline, f"Pipeline '{name}' missing label"
