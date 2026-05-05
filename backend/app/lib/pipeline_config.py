from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# Resolve config path relative to this file — works from any cwd
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pipelines.yaml"


@dataclass
class PipelineFilters:
    gnomad_af_max: float
    consequences: list[str]
    clinvar_exclude: list[str]


@dataclass
class PipelineConfig:
    label: str
    header_pattern: str
    default_filters: PipelineFilters


_cache: dict[str, PipelineConfig] | None = None


def _load() -> dict[str, PipelineConfig]:
    global _cache
    if _cache is not None:
        return _cache
    raw = yaml.safe_load(_CONFIG_PATH.read_text())
    _cache = {}
    for key, val in raw["pipelines"].items():
        df = val["default_filters"]
        _cache[key] = PipelineConfig(
            label=val["label"],
            header_pattern=val.get("header_pattern", ""),
            default_filters=PipelineFilters(
                gnomad_af_max=df["gnomad_af_max"],
                consequences=df.get("consequences", []),
                clinvar_exclude=df.get("clinvar_exclude", []),
            ),
        )
    return _cache


def get_pipeline_config(key: str) -> PipelineConfig | None:
    return _load().get(key)


def get_pipeline_keys() -> list[str]:
    return list(_load().keys())


def get_default_filters(pipeline_key: str) -> PipelineFilters:
    cfg = get_pipeline_config(pipeline_key)
    if cfg:
        return cfg.default_filters
    return PipelineFilters(
        gnomad_af_max=0.01,
        consequences=[
            "missense_variant", "frameshift_variant", "stop_gained",
            "splice_donor_variant", "splice_acceptor_variant",
        ],
        clinvar_exclude=["Benign", "Likely_benign"],
    )


def detect_pipeline_key(header_lines: list[str]) -> str | None:
    source = " ".join(
        line for line in header_lines
        if line.startswith("##source") or line.startswith("##pipeline")
    ).lower()
    for key, cfg in _load().items():
        pattern = cfg.header_pattern.lower()
        if pattern and pattern in source:
            return key
    return None
