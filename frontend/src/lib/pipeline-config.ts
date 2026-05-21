import pipelinesJson from "../config/pipelines.json";
import type { PipelineFilters } from "./api";

interface PipelineConfig {
  label: string;
  default_filters: PipelineFilters;
}

const pipelines = pipelinesJson.pipelines as Record<string, PipelineConfig>;

export function getPipelineDefaults(pipelineKey: string | null): PipelineFilters {
  const config = pipelineKey ? pipelines[pipelineKey] : null;
  return config?.default_filters ?? {
    gnomad_af_max: 0.01,
    consequences: "",
    clinvar_exclude: "",
  };
}

export function getPipelineOptions(): Array<{ key: string; label: string }> {
  return Object.entries(pipelines).map(([key, cfg]) => ({
    key,
    label: cfg.label,
  }));
}
