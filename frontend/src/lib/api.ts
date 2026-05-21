/**
 * Typed API client for the variant-viewer FastAPI backend.
 * All data operations go through these functions — no direct DB or S3 access.
 */

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PatientSummary {
  id: number;
  lab_number: string;
  name: string | null;
  // dob removed — dropped by migration 004 (UK GDPR data-minimisation)
  sample_count: number;
  latest_sample_id: number | null;
  latest_sample_name: string | null;
  latest_workflow_status: string | null;
  latest_ingested_at: string | null;
  pipeline_key: string | null;
}

export interface SampleSummary {
  id: number;
  name: string;
  vcf_filename: string | null;
  case_type: string;
  pipeline_key: string | null;
  ingested_at: string | null;
  workflow_status: string | null;
}

export interface PatientDetailResponse {
  id: number;
  lab_number: string;
  name: string | null;
  created_at: string | null;
  // dob removed — dropped by migration 004 (UK GDPR data-minimisation)
  samples: SampleSummary[];
}

export interface SampleDetail {
  id: number;
  name: string;
  s3_key: string;
  case_type: string;
  pipeline_key: string | null;
  tissue: string | null;
  sequencing_date: string | null;
  ingested_at: string | null;
  patient: { id: number; lab_number: string; name: string | null }; // PatientRef — slim, no aggregates
  workflow_status: string;
  variant_count: number;
}

export interface VariantRow {
  id: number;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  clinvar_sig: string | null;
  gnomad_af: number | null;
  revel_score: number | null;
  spliceai_max: number | null;
  classification: string | null;
  score: number | null;
  framework: string | null;
  locked_at: string | null;
}

export interface CriterionDetail {
  id: number;
  criterion_code: string;
  applied: boolean;
  strength: string;
  notes: string | null;
  evidence_links: string[];
  pre_computed: boolean;
  pre_computed_value: string | null;
}

export interface ClassificationDetail {
  id: number;
  framework: string;
  framework_version: string;
  score: number | null;
  classification: string | null;
  locked_at: string | null;
  locked_by: string | null;
  criteria: CriterionDetail[];
}

export interface VariantDetailResponse {
  id: number;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene: string | null;
  consequence: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  gnomad_af: number | null;
  revel_score: number | null;
  spliceai_max: number | null;
  clinvar_sig: string | null;
  info_json: Record<string, unknown>;
  case_type: string;
  active_classification: ClassificationDetail | null;
}

export interface VariantListResponse {
  items: VariantRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface PipelineFilters {
  gnomad_af_max: number | null;
  consequences: string;
  clinvar_exclude: string;
}

export interface VariantFilterParams extends Partial<PipelineFilters> {
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  gene?: string;
  limit?: number;
  offset?: number;
}

export type WorkflowStatus = "pending" | "reviewing" | "reported" | "archived";

export interface ClassifyPayload {
  framework: string;
  criteria: Array<{
    criterion_code: string;
    applied: boolean;
    strength: string;
    notes?: string;
    evidence_links?: string[];
  }>;
}

export interface ClassifyPersistPayload extends ClassifyPayload {
  user_id: string;
  locked_by: string | null;
}

export interface ClassifyPersistResponse {
  classification_id: number;
  score: number;
  classification: string;
  warnings: string[];
}

export interface UploadUrlParams {
  vcf_filename: string;
  run_date?: string;  // YYYY-MM-DD; defaults to today on backend
}

export interface UploadUrlResponse {
  vcf_url: string;
  manifest_url: string;
  vcf_key: string;
  manifest_key: string;
  expires_in: number;
}

export interface IngestParams {
  vcf_s3_key: string;
  user_id: string;
}

export interface IngestResponse {
  sample_id: number;
  message?: string; // present in /api/ingest-direct response; absent from /api/ingest
}

export interface ClassifyResponse {
  score: number;
  classification: string;
  warnings: string[];
}

export interface CriteriaConfigResponse {
  version: string;
  framework: string;
  criteria: unknown[];
  combination_rules: unknown[];
  thresholds: Record<string, number>;
}

// ─── HTTP client ──────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

/** Returns headers including X-API-Key when configured. Use for direct fetch() calls. */
export function authHeaders(): Record<string, string> {
  // Read at call time (not module load) so vi.stubEnv works in tests
  const key = import.meta.env.VITE_API_KEY as string | undefined;
  if (!key) return {};
  return { "X-API-Key": key };
}

function headers(): HeadersInit {
  return { "Content-Type": "application/json", ...authHeaders() };
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, { ...init, headers: { ...headers(), ...init?.headers } });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(resp.status, detail);
  }
  // 204 No Content or empty body — nothing to parse
  if (resp.status === 204 || resp.headers?.get?.("content-length") === "0") {
    return undefined as unknown as T;
  }
  return resp.json() as Promise<T>;
}

// ─── Patient endpoints ────────────────────────────────────────────────────────

export async function listPatients(params?: {
  search?: string; limit?: number; offset?: number;
}): Promise<{ items: PatientSummary[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  return request(`/api/patients?${q}`);
}

export async function getPatient(id: number): Promise<PatientDetailResponse> {
  return request(`/api/patients/${id}`);
}

export async function deletePatient(id: number): Promise<void> {
  await request(`/api/patients/${id}`, { method: "DELETE" });
}

// ─── Sample endpoints ─────────────────────────────────────────────────────────

export async function getSample(id: number): Promise<SampleDetail> {
  return request(`/api/samples/${id}`);
}

export async function deleteSample(id: number): Promise<void> {
  await request(`/api/samples/${id}`, { method: "DELETE" });
}

// ─── Variant endpoints ────────────────────────────────────────────────────────

export async function listVariants(
  sampleId: number,
  params?: VariantFilterParams
): Promise<VariantListResponse> {
  const q = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== "") q.set(k, String(v));
    });
  }
  return request(`/api/samples/${sampleId}/variants?${q}`);
}

export async function getVariant(id: number): Promise<VariantDetailResponse> {
  return request(`/api/variants/${id}`);
}

// ─── Upload / ingest ──────────────────────────────────────────────────────────

export async function getUploadUrl(params: UploadUrlParams): Promise<UploadUrlResponse> {
  return request("/api/upload-url", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function ingestSample(params: IngestParams): Promise<IngestResponse> {
  return request("/api/ingest", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ─── Workflow ─────────────────────────────────────────────────────────────────

export async function updateWorkflow(
  sampleId: number,
  status: WorkflowStatus,
  userId: string
): Promise<{ sample_id: number; status: string }> {
  return request(`/api/workflow/${sampleId}`, {
    method: "PUT",
    body: JSON.stringify({ status, user_id: userId }),
  });
}

// ─── Classification ───────────────────────────────────────────────────────────

// scoreClassification — reserved for PR 12 real-time preview feature
export async function scoreClassification(
  variantId: number,
  payload: ClassifyPayload
): Promise<ClassifyResponse> {
  return request(`/api/variants/${variantId}/classify`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function putClassification(
  variantId: number,
  payload: ClassifyPersistPayload
): Promise<ClassifyPersistResponse> {
  return request(`/api/variants/${variantId}/classification`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function resetClassification(
  variantId: number,
  classificationId: number,
  userId: string
): Promise<{ new_classification_id: number }> {
  return request(`/api/variants/${variantId}/classification/${classificationId}`, {
    method: "DELETE",
    body: JSON.stringify({ user_id: userId }),
  });
}

// ─── Config ───────────────────────────────────────────────────────────────────

// getCriteriaConfig — reserved for PR 12 (criteria loaded from bundled JSON in PR 8–11)
export async function getCriteriaConfig(framework: string): Promise<CriteriaConfigResponse> {
  return request(`/api/config/criteria/${framework}`);
}
