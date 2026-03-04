import { Readable } from "stream";
import { createInterface } from "readline";

export interface VcfVariant {
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  qual: number | null;
  filter: string | null;
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  gnomad_af: number | null;
  clinvar_sig: string | null;
  revel_score: number | null;
  spliceai_max: number | null;
  info_json: Record<string, unknown>;
}

export interface VcfMeta {
  pipeline_key: string | null;
  header_lines: string[];
}

/** Parse the INFO field into a key→value map */
function parseInfo(infoStr: string): Record<string, string | boolean> {
  if (!infoStr || infoStr === ".") return {};
  const result: Record<string, string | boolean> = {};
  for (const token of infoStr.split(";")) {
    const eq = token.indexOf("=");
    if (eq === -1) {
      result[token] = true;
    } else {
      result[token.slice(0, eq)] = token.slice(eq + 1);
    }
  }
  return result;
}

/** Extract VEP CSQ annotations from INFO map for a specific ALT allele */
function extractVepAnnotations(
  info: Record<string, string | boolean>,
  csqHeader: string[] | null,
  altAllele: string
): {
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  gnomad_af: number | null;
  clinvar_sig: string | null;
  revel_score: number | null;
  spliceai_max: number | null;
} {
  const empty = {
    gene: null,
    consequence: null,
    hgvs_c: null,
    hgvs_p: null,
    gnomad_af: null,
    clinvar_sig: null,
    revel_score: null,
    spliceai_max: null,
  };

  if (csqHeader && info["CSQ"]) {
    const csqValue = info["CSQ"] as string;
    // VEP may have multiple transcripts and alleles — filter by this ALT first
    const entries = csqValue.split(",");
    const alleleIdx = csqHeader.indexOf("Allele");

    // Filter to entries matching this ALT allele (if Allele field exists)
    const alleleMatched =
      alleleIdx >= 0
        ? entries.filter((e) => e.split("|")[alleleIdx] === altAllele)
        : entries;

    // Use allele-matched pool, or fall back to all entries if no match
    const pool = alleleMatched.length > 0 ? alleleMatched : entries;

    // Prefer canonical transcript (CANONICAL=YES)
    const canonIdx = csqHeader.indexOf("CANONICAL");
    const preferred =
      canonIdx >= 0
        ? pool.find((e) => e.split("|")[canonIdx] === "YES") ?? pool[0]
        : pool[0];

    const fields = preferred.split("|");
    const get = (name: string): string => {
      const i = csqHeader.indexOf(name);
      return i >= 0 ? (fields[i] ?? "") : "";
    };

    const gnomadRaw =
      get("gnomADe_AF") ||
      get("gnomAD_AF") ||
      get("gnomADg_AF") ||
      get("MAX_AF");
    const revelRaw = get("REVEL") || get("REVEL_score");

    // SpliceAI: max of DS_AG, DS_AL, DS_DG, DS_DL
    const saiScores = [
      parseFloat(get("SpliceAI_pred_DS_AG")),
      parseFloat(get("SpliceAI_pred_DS_AL")),
      parseFloat(get("SpliceAI_pred_DS_DG")),
      parseFloat(get("SpliceAI_pred_DS_DL")),
    ].filter((v) => !isNaN(v));
    const spliceaiMax = saiScores.length > 0 ? Math.max(...saiScores) : null;

    return {
      gene: get("SYMBOL") || get("Gene") || null,
      consequence: get("Consequence") || null,
      hgvs_c: get("HGVSc") || null,
      hgvs_p: get("HGVSp") || null,
      gnomad_af: gnomadRaw ? parseFloat(gnomadRaw) : null,
      clinvar_sig: get("CLIN_SIG") || get("ClinVar_CLNSIG") || null,
      revel_score: revelRaw ? parseFloat(revelRaw) : null,
      spliceai_max: spliceaiMax,
    };
  }

  // SnpEff ANN field fallback
  if (info["ANN"]) {
    const annValue = info["ANN"] as string;
    const first = annValue.split(",")[0].split("|");
    // ANN format: Allele|Annotation|Impact|Gene_Name|Gene_ID|...
    return {
      ...empty,
      gene: first[3] ?? null,
      consequence: first[1] ?? null,
    };
  }

  return empty;
}

/** Detect pipeline from VCF meta-header lines */
function detectPipeline(headerLines: string[]): string | null {
  const sourceLines = headerLines
    .filter((l) => l.startsWith("##source") || l.startsWith("##pipeline"))
    .join(" ")
    .toLowerCase();
  if (sourceLines.includes("dragen")) return "dragen_germline";
  if (sourceLines.includes("haplotypecaller")) return "gatk_haplotypecaller";
  if (sourceLines.includes("mutect2")) return "mutect2";
  if (sourceLines.includes("strelka")) return "strelka2";
  return null;
}

/** Parse VCF from a Node.js Readable stream.
 *  Calls onVariant for each parsed variant row.
 *  Returns VcfMeta after the stream ends.
 */
export async function parseVcf(
  stream: Readable,
  onVariant: (v: VcfVariant) => Promise<void>
): Promise<VcfMeta> {
  const rl = createInterface({ input: stream, crlfDelay: Infinity });

  const headerLines: string[] = [];
  let csqHeader: string[] | null = null;
  let lineNum = 0;

  for await (const line of rl) {
    lineNum++;
    if (line.startsWith("##")) {
      headerLines.push(line);
      // Parse VEP CSQ format header: ##INFO=<ID=CSQ,...,Format: A|B|C>
      if (line.includes("ID=CSQ") && line.includes("Format:")) {
        const fmt = line.split("Format:")[1]?.replace(/[">]/g, "").trim();
        if (fmt) csqHeader = fmt.split("|");
      }
      continue;
    }
    if (line.startsWith("#CHROM")) continue; // column header

    const cols = line.split("\t");
    if (cols.length < 8) continue;

    const [chrom, posStr, , ref, altField, qualStr, filterStr, infoStr] = cols;
    const qual = qualStr === "." ? null : parseFloat(qualStr);
    const filter = filterStr === "." ? null : filterStr;
    const info = parseInfo(infoStr);

    // Handle multi-allelic: split ALT on comma
    const alts = altField.split(",");
    for (const alt of alts) {
      if (!alt || alt === "*") continue; // skip spanning deletions

      const annotations = extractVepAnnotations(info, csqHeader, alt);
      const variant: VcfVariant = {
        chrom,
        pos: parseInt(posStr, 10),
        ref,
        alt,
        qual,
        filter,
        ...annotations,
        info_json: info as Record<string, unknown>,
      };
      await onVariant(variant);
    }
  }

  const pipeline_key = detectPipeline(headerLines);
  return { pipeline_key, header_lines: headerLines };
}
