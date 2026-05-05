from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.lib.classification_engine import select_framework, Framework
from app.lib.vcf_parser import VcfVariant

CaseType = Literal["germline", "somatic"]

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_canvig_raw = json.loads((_CONFIG_DIR / "canvig-gene-mtaf.json").read_text())
_CANVIG_GENES: dict = _canvig_raw["genes"]

_LOF_CONSEQUENCES = {
    "frameshift_variant",
    "stop_gained",
    "stop_lost",
    "start_lost",
    "splice_donor_variant",
    "splice_acceptor_variant",
    "transcript_ablation",
}

_ACGS_DEFAULT_BA1 = 0.05
_ACGS_DEFAULT_BS1 = 0.01


@dataclass
class PreComputedCriterion:
    criterion_code: str
    pre_computed_value: str
    framework: Framework
    suggested_strength: str


def _gnomad_thresholds(gene: str | None) -> tuple[float, float]:
    if gene:
        g = _CANVIG_GENES.get(gene) or _CANVIG_GENES.get(gene.upper())
        if g:
            return g["ba1_threshold"], g["bs1_threshold"]
    return _ACGS_DEFAULT_BA1, _ACGS_DEFAULT_BS1


def pre_compute_criteria(
    variant: VcfVariant,
    case_type: CaseType,
) -> list[PreComputedCriterion]:
    results: list[PreComputedCriterion] = []
    framework, is_canvig = select_framework(case_type, variant.gene)
    gnomad = variant.gnomad_af
    csq = variant.consequence.split("&")[0] if variant.consequence else None

    if framework == "acgs_snv":
        ba1_thresh, bs1_thresh = _gnomad_thresholds(variant.gene)

        # BA1 — standalone benign if AF above threshold
        if gnomad is not None and gnomad > ba1_thresh:
            label = f"CanVIG {variant.gene}" if is_canvig else "ACGS standard"
            results.append(PreComputedCriterion(
                criterion_code="BA1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} [threshold {ba1_thresh} \u2014 {label}]",
                framework=framework,
                suggested_strength="standalone",
            ))

        # BS1 — elevated AF (above bs1 threshold but at or below ba1 threshold)
        if gnomad is not None and bs1_thresh < gnomad <= ba1_thresh:
            results.append(PreComputedCriterion(
                criterion_code="BS1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} [BS1 threshold {bs1_thresh}]",
                framework=framework,
                suggested_strength="strong",
            ))

        # PM2 — absent or very low AF
        if gnomad is None or gnomad < 0.0001:
            af_label = "absent in gnomAD" if gnomad is None else f"gnomAD AF = {gnomad:.2e}"
            results.append(PreComputedCriterion(
                criterion_code="PM2",
                pre_computed_value=af_label,
                framework=framework,
                suggested_strength="supporting",
            ))

        # PVS1 — null variant (LOF consequence)
        if csq and csq in _LOF_CONSEQUENCES:
            results.append(PreComputedCriterion(
                criterion_code="PVS1",
                pre_computed_value=f"Consequence: {variant.consequence}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # PVS1_RNA — high SpliceAI max delta
        if variant.spliceai_max is not None and variant.spliceai_max >= 0.8:
            results.append(PreComputedCriterion(
                criterion_code="PVS1_RNA",
                pre_computed_value=f"SpliceAI max delta = {variant.spliceai_max:.3f}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # PP3 — damaging REVEL
        if variant.revel_score is not None and variant.revel_score >= 0.7:
            results.append(PreComputedCriterion(
                criterion_code="PP3",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # BP4 — benign REVEL
        if variant.revel_score is not None and variant.revel_score <= 0.4:
            results.append(PreComputedCriterion(
                criterion_code="BP4",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # BP7 — synonymous + low SpliceAI
        if variant.consequence and "synonymous_variant" in variant.consequence:
            sai = variant.spliceai_max
            if sai is None or sai < 0.1:
                sai_str = f"{sai:.3f}" if sai is not None else "N/A"
                results.append(PreComputedCriterion(
                    criterion_code="BP7",
                    pre_computed_value=f"Synonymous variant; SpliceAI max delta = {sai_str}",
                    framework=framework,
                    suggested_strength="supporting",
                ))

        # PS1 — ClinVar pathogenic (no conflict)
        if (variant.clinvar_sig
                and re.search(r"pathogenic", variant.clinvar_sig, re.I)
                and not re.search(r"conflict", variant.clinvar_sig, re.I)):
            results.append(PreComputedCriterion(
                criterion_code="PS1",
                pre_computed_value=f"ClinVar: {variant.clinvar_sig}",
                framework=framework,
                suggested_strength="strong",
            ))

    else:  # svig
        # B1 — germline polymorphism (AF > 0.01)
        if gnomad is not None and gnomad > 0.01:
            results.append(PreComputedCriterion(
                criterion_code="B1",
                pre_computed_value=f"gnomAD AF = {gnomad:.2e} (> 0.01)",
                framework=framework,
                suggested_strength="standalone",
            ))

        # O3 — absent or very rare in population
        if gnomad is None or gnomad < 0.0001:
            af_label = "absent in gnomAD" if gnomad is None else f"gnomAD AF = {gnomad:.2e}"
            results.append(PreComputedCriterion(
                criterion_code="O3",
                pre_computed_value=af_label,
                framework=framework,
                suggested_strength="moderate",
            ))

        # O2 — null variant in potential tumour suppressor gene
        if csq and csq in _LOF_CONSEQUENCES:
            results.append(PreComputedCriterion(
                criterion_code="O2",
                pre_computed_value=f"Consequence: {variant.consequence}",
                framework=framework,
                suggested_strength="very_strong",
            ))

        # O6 — computational evidence of oncogenic effect
        if variant.revel_score is not None and variant.revel_score >= 0.7:
            results.append(PreComputedCriterion(
                criterion_code="O6",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # B3 — computational benign evidence (REVEL ≤ 0.4 takes priority over SpliceAI)
        b3_added = False
        if variant.revel_score is not None and variant.revel_score <= 0.4:
            results.append(PreComputedCriterion(
                criterion_code="B3",
                pre_computed_value=f"REVEL score = {variant.revel_score:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))
            b3_added = True
        if not b3_added and variant.spliceai_max is not None and variant.spliceai_max < 0.1:
            results.append(PreComputedCriterion(
                criterion_code="B3",
                pre_computed_value=f"SpliceAI max delta = {variant.spliceai_max:.3f}",
                framework=framework,
                suggested_strength="supporting",
            ))

        # O1 — ClinVar somatic oncogenic or pathogenic (no conflict)
        if (variant.clinvar_sig
                and re.search(r"oncogenic|pathogenic", variant.clinvar_sig, re.I)
                and not re.search(r"conflict", variant.clinvar_sig, re.I)):
            results.append(PreComputedCriterion(
                criterion_code="O1",
                pre_computed_value=f"ClinVar: {variant.clinvar_sig}",
                framework=framework,
                suggested_strength="standalone",
            ))

    return results
