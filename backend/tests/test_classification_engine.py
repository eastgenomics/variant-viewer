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


def test_classification_label_vus():
    assert classification_label("VUS") == "Variant of Uncertain Significance"


def test_classification_label_likely_pathogenic():
    assert classification_label("Likely_Pathogenic") == "Likely Pathogenic"


def test_not_applied_criteria_ignored():
    criteria = [
        AppliedCriterion("PVS1", applied=False, strength="very_strong"),
        AppliedCriterion("PM2",  applied=True,  strength="supporting"),
    ]
    result = classify(criteria, "acgs_snv", [])
    # Only PM2 applied (+1), single criterion → minimum warning; score=1 → VUS (0 ≤ 1 < 6)
    assert result.classification == "VUS"


def test_classification_badge_class_all_known_values():
    """Every canonical classification string must map to a non-empty CSS class."""
    known = [
        "Pathogenic", "Likely_Pathogenic", "VUS",
        "Likely_Benign", "Benign", "Oncogenic", "Likely_Oncogenic",
    ]
    for cls in known:
        badge = classification_badge_class(cls)
        assert badge, f"badge class is empty for {cls!r}"
        assert badge != "vus" or cls == "VUS", (
            f"{cls!r} should not fall back to the 'vus' default"
        )


def test_classification_badge_class_unknown_falls_back_to_vus():
    assert classification_badge_class("SomeFutureClass") == "vus"
