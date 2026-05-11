"""Pipeline configuration loader and VCF header-based pipeline detection.

Loads ``backend/config/pipelines.yaml`` once at first call and caches
the result for the lifetime of the process.  Exposes helpers for
retrieving per-pipeline filter defaults and detecting the pipeline key
from VCF ``##source`` / ``##pipeline`` header lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# Resolve config path relative to this file so tests work from any cwd
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pipelines.yaml"


@dataclass
class PipelineFilters:
    """Default variant filter thresholds for a sequencing pipeline."""

    gnomad_af_max: float
    consequences: list[str]
    clinvar_exclude: list[str]


@dataclass
class PipelineConfig:
    """Configuration record for a single named sequencing pipeline."""

    label: str
    header_pattern: str
    default_filters: PipelineFilters


_cache: dict[str, PipelineConfig] | None = None


def _load() -> dict[str, PipelineConfig]:
    """Load and cache pipeline config from YAML; return the cache on subsequent calls."""
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
    """Return the ``PipelineConfig`` for *key*, or ``None`` if the key is unknown."""
    return _load().get(key)


def get_pipeline_keys() -> list[str]:
    """Return all known pipeline keys in insertion order."""
    return list(_load().keys())


def get_default_filters(pipeline_key: str) -> PipelineFilters:
    """Return default variant filters for *pipeline_key*.

    Falls back to conservative ACGS-2024 defaults when *pipeline_key* is
    not present in ``pipelines.yaml``.
    """
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
    """Return the pipeline key matching a VCF header, or ``None`` if unrecognised.

    Concatenates all ``##source`` and ``##pipeline`` header lines and
    performs a case-insensitive substring search against each pipeline's
    ``header_pattern``.  Returns the first match in YAML insertion order.

    Note:
        ``dragen_germline`` and ``dragen_somatic`` currently share the
        ``"DRAGEN"`` pattern; ``dragen_germline`` wins by dict order.
        Differentiation is deferred until real VCF ``##source`` strings
        from the lab are confirmed.
    """
    source = " ".join(
        line for line in header_lines
        if line.startswith("##source") or line.startswith("##pipeline")
    ).lower()
    for key, cfg in _load().items():
        pattern = cfg.header_pattern.lower()
        if pattern and pattern in source:
            return key
    return None
