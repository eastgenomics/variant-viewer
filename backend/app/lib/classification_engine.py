"""Tavtigian point-based variant classification engine.

Implements the ACGS SNV (germline) and SVIG-UK (somatic) scoring
algorithms.  The engine is a pure function over analyst-applied criteria
and pre-loaded config; it performs no I/O and mutates no state.

Key functions
-------------
classify(criteria, framework, combination_rules)
    Score criteria and return a ``ClassificationResult``.
select_framework(case_type, gene)
    Return the applicable framework and CanVIG membership flag.
classification_label(classification)
    Human-readable display label for a classification string.
"""

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
    """A single classification criterion with its applied state and strength."""

    criterion_code: str
    applied: bool
    strength: str


@dataclass
class CombinationRule:
    """A pairwise conflict rule loaded from the criteria JSON config.

    Triggers a warning when two or more codes from ``codes`` are
    simultaneously applied.
    """

    rule: str
    codes: list[str]
    message: str


@dataclass
class ClassificationResult:
    """Result of scoring a set of applied criteria."""

    score: int
    classification: str
    warnings: list[str] = field(default_factory=list)


def _get_direction(code: str, framework: Framework) -> str | None:
    """Return the scoring direction for *code* within *framework*.

    Returns ``"pathogenic"``, ``"benign"``, or ``"oncogenic"`` based on
    the criterion code prefix, or ``None`` if the code is unrecognised.
    """
    if framework == "acgs_snv":
        if re.match(r"^(PVS|PS|PM|PP)", code):
            return "pathogenic"
        if re.match(r"^(BA|BS|BP)", code):
            return "benign"
    else:
        if re.match(r"^O", code):
            return "oncogenic"
        if re.match(r"^B", code):
            return "benign"
    return None


def _check_combination_rules(
    applied: list[AppliedCriterion],
    rules: list[CombinationRule],
) -> list[str]:
    """Return warning messages for any pairwise criterion conflicts.

    A rule fires when two or more of its ``codes`` appear in *applied*.
    Single-code sentinel rules (BA1, O1, B1, B2) are handled as
    explicit overrides in ``classify()`` and are never passed here.
    """
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
    """Score applied criteria and return a classification result.

    Implements Tavtigian point-based scoring for ACGS SNV (germline) and
    SVIG-UK (somatic) frameworks.  Only criteria with ``applied=True``
    contribute to the score; unapplied (pre-computed suggestion) rows are
    silently ignored.

    Args:
        criteria: All criteria for the variant (applied and unapplied).
        framework: ``"acgs_snv"`` for germline or ``"svig"`` for somatic.
        combination_rules: Pairwise conflict rules loaded from config;
            pass an empty list if no conflict detection is needed.

    Returns:
        A ``ClassificationResult`` with integer score, classification
        label, and any combination-rule or minimum-criteria warnings.

    Raises:
        ValueError: If a criterion code or strength value is not
            recognised for the given framework.
    """
    applied = [c for c in criteria if c.applied]
    warnings = _check_combination_rules(applied, combination_rules)

    if framework == "acgs_snv":
        # Step 3: BA1 standalone override
        if any(c.criterion_code == "BA1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign", warnings=warnings)

        # Steps 4-5: sum points - raise on unknown strength so typos fail loud
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction is None:
                raise ValueError(
                    f"Unknown criterion code {c.criterion_code!r} for framework {framework!r}"
                )
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
        # Steps 2-4: sentinel overrides
        if any(c.criterion_code == "O1" for c in applied):
            return ClassificationResult(score=999,  classification="Oncogenic", warnings=warnings)
        if any(c.criterion_code == "B1" for c in applied):
            return ClassificationResult(score=-999, classification="Benign",    warnings=warnings)
        if any(c.criterion_code == "B2" for c in applied):
            return ClassificationResult(score=0,    classification="VUS",       warnings=warnings)

        # Step 5: sum points - raise on unknown strength so typos fail loud
        score = 0
        for c in applied:
            direction = _get_direction(c.criterion_code, framework)
            if direction is None:
                raise ValueError(
                    f"Unknown criterion code {c.criterion_code!r} for framework {framework!r}"
                )
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
    """Return the appropriate framework and CanVIG membership flag.

    Somatic variants always use SVIG-UK.  Germline variants use ACGS SNV;
    the CanVIG flag is ``True`` when *gene* (case-insensitive) is in the
    CanVIG gene list, triggering gene-specific AF thresholds.

    Args:
        case_type: ``"germline"`` or ``"somatic"``.
        gene: HGNC gene symbol, or ``None`` if not annotated.

    Returns:
        A tuple ``(framework, is_canvig)``.
    """
    if case_type == "somatic":
        return "svig", False
    normalised = gene.strip().upper() if gene else None
    is_canvig = normalised in _CANVIG_GENES if normalised else False
    return "acgs_snv", is_canvig


def get_framework_version(framework: Framework) -> str:
    """Return the version string for *framework*."""
    return ACGS_VERSION if framework == "acgs_snv" else SVIG_VERSION


def classification_label(classification: str) -> str:
    """Return a human-readable display label for a classification string."""
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
    """Return the CSS badge class name for a classification string."""
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
