import json
from pathlib import Path
import pytest

from app.lib.classification_engine import (
    classify, select_framework, get_framework_version,
    classification_label, classification_badge_class,
    AppliedCriterion, CombinationRule, ClassificationResult,
)

_GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_cases(fname: str) -> list[dict]:
    return json.loads((_GOLDEN_DIR / fname).read_text())


def _make_criteria(raw: list[dict]) -> list[AppliedCriterion]:
    return [AppliedCriterion(**c) for c in raw]


def _make_rules(raw: list[dict]) -> list[CombinationRule]:
    return [CombinationRule(**r) for r in raw]


@pytest.mark.parametrize("case", _load_cases("classify_acgs_cases.json"))
def test_acgs_golden(case):
    result = classify(
        _make_criteria(case["criteria"]),
        "acgs_snv",
        _make_rules(case["combination_rules"]),
    )
    exp = case["expected"]
    assert result.score == exp["score"], f"[{case['description']}] score mismatch"
    assert result.classification == exp["classification"], f"[{case['description']}] classification mismatch"
    assert result.warnings == exp["warnings"], f"[{case['description']}] warnings mismatch"


@pytest.mark.parametrize("case", _load_cases("classify_svig_cases.json"))
def test_svig_golden(case):
    result = classify(
        _make_criteria(case["criteria"]),
        "svig",
        _make_rules(case["combination_rules"]),
    )
    exp = case["expected"]
    assert result.score == exp["score"]
    assert result.classification == exp["classification"]
    assert result.warnings == exp["warnings"]


@pytest.mark.parametrize("case", _load_cases("select_framework_cases.json"))
def test_select_framework_golden(case):
    framework, is_canvig = select_framework(case["case_type"], case["gene"])
    assert framework == case["expected"]["framework"]
    assert is_canvig == case["expected"]["is_canvig"]


def test_get_framework_version_acgs():
    assert "ACGS" in get_framework_version("acgs_snv")


def test_get_framework_version_svig():
    assert "SVIG" in get_framework_version("svig")


@pytest.mark.parametrize("classification,expected_label", [
    ("Pathogenic",        "Pathogenic"),
    ("Likely_Pathogenic", "Likely Pathogenic"),
    ("VUS",               "Variant of Uncertain Significance"),
    ("Likely_Benign",     "Likely Benign"),
    ("Benign",            "Benign"),
    ("Oncogenic",         "Oncogenic"),
    ("Likely_Oncogenic",  "Likely Oncogenic"),
    ("Unknown",           "Unknown"),   # unknown value returns itself
])
def test_classification_label(classification, expected_label):
    assert classification_label(classification) == expected_label


@pytest.mark.parametrize("classification,expected_badge", [
    ("Pathogenic",        "pathogenic"),
    ("Likely_Pathogenic", "likely-pathogenic"),
    ("VUS",               "vus"),
    ("Likely_Benign",     "likely-benign"),
    ("Benign",            "benign"),
    ("Oncogenic",         "oncogenic"),
    ("Likely_Oncogenic",  "likely-oncogenic"),
])
def test_classification_badge_class(classification, expected_badge):
    assert classification_badge_class(classification) == expected_badge

def test_not_applied_criteria_ignored():
    criteria = [
        AppliedCriterion("PVS1", applied=False, strength="very_strong"),
        AppliedCriterion("PM2",  applied=True,  strength="supporting"),
    ]
    result = classify(criteria, "acgs_snv", [])
    # Only PM2 applied (+1); score=1 → VUS. Single criterion on a VUS verdict
    # must NOT fire the minimum-criteria warning (warning is for non-VUS only).
    assert result.classification == "VUS"
    assert result.warnings == []


def test_unknown_criterion_code_raises():
    """A criterion code unrecognised by _get_direction must raise, not score as 0."""
    criteria = [AppliedCriterion("XM2", applied=True, strength="supporting")]  # no known prefix
    with pytest.raises(ValueError, match="Unknown criterion code"):
        classify(criteria, "acgs_snv", [])


def test_unknown_strength_raises():
    """An unrecognised strength string must raise, not silently contribute 0 points."""
    criteria = [AppliedCriterion("PM2", applied=True, strength="ultra_strong")]  # invalid
    with pytest.raises(ValueError, match="Unknown strength"):
        classify(criteria, "acgs_snv", [])


