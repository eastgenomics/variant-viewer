import json
from pathlib import Path
import pytest
from app.lib.pre_compute_criteria import pre_compute_criteria
from app.lib.vcf_parser import VcfVariant


def _make_variant(**kwargs) -> VcfVariant:
    defaults = dict(
        chrom="1", pos=100, ref="A", alt="G", qual=None, filter=None,
        hgvs_c=None, hgvs_p=None, info_json={},
    )
    defaults.update(kwargs)
    return VcfVariant(**defaults)


_CASES = json.loads((Path(__file__).parent / "golden" / "pre_compute_cases.json").read_text())


@pytest.mark.parametrize("case", _CASES)
def test_pre_compute_golden(case):
    v_data = case["variant"]
    variant = _make_variant(**v_data)
    results = pre_compute_criteria(variant, case["case_type"])

    result_codes = {r.criterion_code for r in results}
    expected_codes = set(case["expected_codes"])

    assert result_codes == expected_codes, (
        f"[{case['description']}]\n"
        f"  Got codes:      {sorted(result_codes)}\n"
        f"  Expected codes: {sorted(expected_codes)}"
    )

    for code, strength in case["expected_strengths"].items():
        matching = next(r for r in results if r.criterion_code == code)
        assert matching.suggested_strength == strength, (
            f"[{case['description']}] {code} strength: got {matching.suggested_strength}, expected {strength}"
        )
