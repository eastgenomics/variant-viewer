import { readFileSync } from "fs";
import { join } from "path";
import yaml from "js-yaml";

export interface PipelineFilters {
  gnomad_af_max: number;
  consequences: string[];
  clinvar_exclude: string[];
}

export interface PipelineConfig {
  label: string;
  header_pattern: string;
  default_filters: PipelineFilters;
}

export interface PipelinesConfig {
  pipelines: Record<string, PipelineConfig>;
}

let _config: PipelinesConfig | null = null;

export function getPipelinesConfig(): PipelinesConfig {
  if (!_config) {
    const filePath = join(process.cwd(), "config", "pipelines.yaml");
    const raw = readFileSync(filePath, "utf-8");
    _config = yaml.load(raw) as PipelinesConfig;
  }
  return _config;
}

export function getPipelineConfig(key: string): PipelineConfig | null {
  const config = getPipelinesConfig();
  return config.pipelines[key] ?? null;
}

export function getPipelineKeys(): string[] {
  return Object.keys(getPipelinesConfig().pipelines);
}

/** Detect pipeline key from VCF header lines using pattern matching */
export function detectPipelineKey(headerLines: string[]): string | null {
  const source = headerLines
    .filter((l) => l.startsWith("##source") || l.startsWith("##pipeline"))
    .join(" ")
    .toLowerCase();
  const config = getPipelinesConfig();
  for (const [key, pipeline] of Object.entries(config.pipelines)) {
    if (
      pipeline.header_pattern &&
      source.includes(pipeline.header_pattern.toLowerCase())
    ) {
      return key;
    }
  }
  return null;
}

export function getDefaultFilters(pipelineKey: string): PipelineFilters {
  const pipeline = getPipelineConfig(pipelineKey);
  return (
    pipeline?.default_filters ?? {
      gnomad_af_max: 0.01,
      consequences: [
        "missense_variant",
        "frameshift_variant",
        "stop_gained",
        "splice_donor_variant",
        "splice_acceptor_variant",
      ],
      clinvar_exclude: ["Benign", "Likely_benign"],
    }
  );
}
