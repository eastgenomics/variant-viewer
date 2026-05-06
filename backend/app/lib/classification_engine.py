from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ACGS_VERSION = "ACGS 2024 Best Practice Guidelines"
SVIG_VERSION = "SVIG-UK v1.0"

Framework = Literal["acgs_snv", "svig"]
CaseType  = Literal["germline", "somatic"]

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

# Load CanVIG gene set once at import — case-insensitive lookup via .upper()
_canvig_raw = json.loads((_CONFIG_DIR / "canvig-gene-mtaf.json").read_text())
_CANVIG_GENES: set[str] = {g.upper() for g in _canvig_raw["genes"].keys()}

STRENGTH_POINTS: dict[str, int] = {
    "very_strong": 8,
    "strong":      4,
    "moderate":    2,
    "supporting":  1,
    "standalone":  8,  # BA1/O1/B1/B2 are sentinel overrides and never reach this table;
                       # kept as a fallback if a future standalone criterion uses point scoring.
}
BENIGN_POINTS: dict[str, int] = {
    "strong":     -4,
    "moderate":   -2,
    "supporting": -1,
}


@dataclass
class AppliedCriterion:
    criterion_code: str
    applied: bool
    strength: str


@dataclass
class CombinationRule:
    rule: str
    codes: list[str]
    message: str


@dataclass
class ClassificationResult:
    score: int
    classification: str
    warnings: list[str] = field(default_factory=list)


def _get_direction(code: str, framework: Framework) -> str | None:
    if framework == "acgs_snv":
        if re.match(r"^(PVS|PS|PM|PP)", code): return "pathogenic"
        if re.match(r"^(BA|BS|BP)", code):      return "benign"
    else:
        if re.match(r"^O", code): return "oncogenic"
        if re.match(r"^B", code): return "benign"
    return None


def _check_combination_rules(
    applied: list[AppliedCriterion],
    rules: list[CombinationRule],
) -> list[str]:
    warnings: list[str] = []
    applied_codes = {c.criterion_code for c in applied}
    for rule in rules:
        if len(rule.codes) >= 2 and sum(1 for c in rule.codes if c in applied_codes) >= 2:
            warnings.append(rule.message)
    return warnings


def classify(
    criteria: list[AppliedCriterion],
    framework: Framework,
    combination_rules: list[CombinationRule],
) -> ClassificationResult:
    applied = [c for c in criteria if c.applied]
    warnings = _check_combination_rules(applied, combination_rules)

    if framework == "acgs_snv":
        # Step 3: BA1 standalone override
        if any(c.criterion_code == "BA1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign", warnings=warnings)

        # Steps 4–5: sum points — raise on unknown strength so typos fail loud
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction == "pathogenic":
                if c.strength not in STRENGTH_POINTS:
                    raise ValueError(
                        f"Unknown strength {c.strength!r} for pathogenic criterion {c.criterion_code!r}"
                    )
                score += STRENGTH_POINTS[c.strength]
            elif direction == "benign":
                if c.strength not in BENIGN_POINTS:
                    raise ValueError(
                        f"Unknown strength {c.strength!r} for benign criterion {c.criterion_code!r}"
                    )
                score += BENIGN_POINTS[c.strength]

        # Step 6: classify by score
        if score >= 10:
            classification = "Pathogenic"
        elif score >= 6:
            classification = "Likely_Pathogenic"
        elif score >= 0:
            classification = "VUS"
        elif score >= -6:
            classification = "Likely_Benign"
        else:
            classification = "Benign"

        # Step 7: minimum criteria warning — only meaningful when verdict is non-VUS
        if len(applied) < 2 and classification != "VUS":
            warnings.append(
                "ACGS requires a minimum of 2 applied criteria for any non-VUS classification (except BA1)."
            )

        return ClassificationResult(score, classification, warnings)

    else:  # svig
        # Steps 2–4: sentinel overrides
        if any(c.criterion_code == "O1" for c in applied):
            return ClassificationResult(score=999,  classification="Oncogenic", warnings=warnings)
        if any(c.criterion_code == "B1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign",    warnings=warnings)
        if any(c.criterion_code == "B2" for c in applied):
            return ClassificationResult(score=0,    classification="VUS",       warnings=warnings)

        # Step 5: sum points — raise on unknown strength so typos fail loud
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction == "oncogenic":
                if c.strength not in STRENGTH_POINTS:
                    raise ValueError(
                        f"Unknown strength {c.strength!r} for oncogenic criterion {c.criterion_code!r}"
                    )
                score += STRENGTH_POINTS[c.strength]
            elif direction == "benign":
                if c.strength not in BENIGN_POINTS:
                    raise ValueError(
                        f"Unknown strength {c.strength!r} for benign criterion {c.criterion_code!r}"
                    )
                score += BENIGN_POINTS[c.strength]

        # Step 6: classify
        if score >= 10:
            return ClassificationResult(score, "Oncogenic", warnings)
        if score >= 6:
            return ClassificationResult(score, "Likely_Oncogenic", warnings)
        if score >= 0:
            return ClassificationResult(score, "VUS", warnings)
        if score >= -6:
            return ClassificationResult(score, "Likely_Benign", warnings)
        return ClassificationResult(score, "Benign", warnings)


def select_framework(case_type: CaseType, gene: str | None) -> tuple[Framework, bool]:
    if case_type == "somatic":
        return "svig", False
    normalised = gene.strip().upper() if gene else None
    is_canvig = normalised in _CANVIG_GENES if normalised else False
    return "acgs_snv", is_canvig


def get_framework_version(framework: Framework) -> str:
    return ACGS_VERSION if framework == "acgs_snv" else SVIG_VERSION


def classification_label(classification: str) -> str:
    labels = {
        "Pathogenic":        "Pathogenic",
        "Likely_Pathogenic": "Likely Pathogenic",
        "VUS":               "Variant of Uncertain Significance",
        "Likely_Benign":     "Likely Benign",
        "Benign":            "Benign",
        "Oncogenic":         "Oncogenic",
        "Likely_Oncogenic":  "Likely Oncogenic",
    }
    return labels.get(classification, classification)


def classification_badge_class(classification: str) -> str:
    badge = {
        "Pathogenic":        "pathogenic",
        "Likely_Pathogenic": "likely-pathogenic",
        "VUS":               "vus",
        "Likely_Benign":     "likely-benign",
        "Benign":            "benign",
        "Oncogenic":         "oncogenic",
        "Likely_Oncogenic":  "likely-oncogenic",
    }
    return badge.get(classification, "vus")
