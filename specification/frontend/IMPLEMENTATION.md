# IMPLEMENTATION — variant-viewer frontend SPA (PRs 8–11)

## 0. Prerequisites

```bash
# Node.js ≥ 20 and npm must be installed
node --version   # ≥ 20
npm --version

# The FastAPI backend must be running on :8000 for manual smoke-testing
# (tests use mocks; backend not required for test runs)

# Confirm starting file tree
ls frontend/
# Expected: Dockerfile  package.json  public/  src/
ls frontend/src/
# Expected: components/  lib/  pages/  (all empty .gitkeep files)
```

---

## 1. Backend pre-requisite milestones (before any frontend work)

These backend changes must be committed to `main` before starting M19.
All are small, targeted extensions to existing routes.

| M | Module | Change | Tests |
|---|---|---|---|
| M_pre1 | `routes/patients.py` | Extend `PatientSummary` + `list_patients` SQL with `sample_count`, `latest_sample_id`, `latest_sample_name`, `latest_workflow_status`, `latest_ingested_at`, `pipeline_key` aggregate subqueries. **Note: `dob` is NOT added — it was removed by migration 004 (UK GDPR data-minimisation).** `PatientDetailResponse extends PatientSummary` so it inherits all aggregate fields. | Extend `test_routes_read.py`: assert `sample_count`/`latest_*` fields present in list response; assert `dob` NOT in response |
| M_pre2 | `routes/samples.py` | Add `sort_by`, `sort_dir`, `gnomad_af_max`, `consequences`, `clinvar_exclude`, `gene` query params to `list_sample_variants`; apply as WHERE/ORDER BY clauses | Add filter tests to `test_routes_read.py` |
| M_pre3 | `routes/samples.py` | Extend `VariantSummary` with `hgvs_c`, `hgvs_p`, `clinvar_sig` from `variants` table | Assert new fields in variant list response |
| M_pre4 | `routes/patients.py` | Add `DELETE /api/patients/{id}` (cascade delete samples/variants/classifications, audit log, 404 if not found) | `test_routes_write.py`: 204 on delete, 404 on re-delete |
| M_pre5 | `routes/samples.py` | Add `DELETE /api/samples/{id}` (cascade delete variants/classifications, audit log, 204 on success; high-risk warning for `reported`/`archived` handled client-side only — no server-side block) | `test_routes_write.py`: 204 on delete, 404 on re-delete |
| M_pre6 | `routes/classification.py` | Make `locked_by: str \| None` in `ClassificationSubmitRequest`; when `None`, skip setting `locked_at`/`locked_by` in INSERT | Assert draft save (locked_by=null) stores NULL in DB; confirm save stores user_id |
| M_pre7 | `routes/patients.py` | Add `vcf_filename` to `SampleSummary` in `PatientDetailResponse` | Assert field present in patient detail response |
| M_pre8 | `routes/ingest.py` | Add `POST /api/ingest-direct` accepting `multipart/form-data` (`vcf` file + patient/specimen fields); parses VCF locally and writes patient/sample/variant/classification-shell rows directly to the DB (no S3 required); mirrors `ingest_sample()` logic without the S3 download step | `test_routes_write.py`: 200 with sample_id; 400 on non-.vcf file (tests not yet written) |

---

## 2. Milestone plan

| M | PR | Module(s) | Red tests | Green when |
|---|---|---|---|---|
| M_pre1–8 | 8 | Backend extensions (see above) | See above | All pre-req tests green |
| M19 | 8 | Scaffold: `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/index.css`, `src/config/pipelines.json` | — | `npm run build` succeeds; `npm test` runs (0 tests) |
| M20 | 8 | `src/lib/display-utils.ts` | `display-utils.test.ts` | All display util tests green |
| M21 | 8 | `src/lib/classification-engine.ts` | `classification-engine.test.ts` (golden cases) | All 4 golden cases pass |
| M22 | 8 | `src/lib/api.ts` | `api.test.ts` | All typed fetch wrapper tests green |
| M23 | 9 | Shared components: `Navbar`, `WorkflowBadge`, `ClassificationBadge`, `PatientHeader`, `PatientListTable` (+ `DeletePatientButton`) | `PatientListTable.test.tsx`, `PatientHeader.test.tsx`, `WorkflowBadge.test.tsx`, `ClassificationBadge.test.tsx` | All component render tests green |
| M24 | 9 | `SpecimenCard`, `WorkflowControl`, `DeleteSampleButton`, `VariantTable` | `SpecimenCard.test.tsx`, `WorkflowControl.test.tsx`, `VariantTable.test.tsx` | All specimen/variant component tests green |
| M25 | 10 | `CriterionRow`, `ClassificationPanel` | `CriterionRow.test.tsx`, `ClassificationPanel.test.tsx` | Classification panel tests green |
| M26 | 11 | `UploadForm`, pages (`PatientsPage`, `PatientDetailPage`, `ClassificationPage`, `UploadPage`) | `UploadForm.test.tsx` | All tests green; `npm run build` clean; `tsc --noEmit` clean |

---

## 3. Milestone 19 — Scaffold (PR 8)

### Green: project scaffold

Update `frontend/package.json` to add missing test and type dependencies:

```json
{
  "name": "frontend",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "@tanstack/react-table": "^8.20.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/user-event": "^14.5.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0",
    "jsdom": "^25.0.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

`frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
  },
});
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Variant Viewer</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

`frontend/src/App.tsx`:

```tsx
import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import PatientsPage from "./pages/PatientsPage";
import PatientDetailPage from "./pages/PatientDetailPage";
import ClassificationPage from "./pages/ClassificationPage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <div>
      <Navbar />
      <main className="px-6 py-6 max-w-screen-2xl mx-auto">
        <Routes>
          <Route path="/" element={<PatientsPage />} />
          <Route path="/patients/:id" element={<PatientDetailPage />} />
          <Route
            path="/patients/:patientId/variants/:variantId"
            element={<ClassificationPage />}
          />
          <Route path="/upload" element={<UploadPage />} />
        </Routes>
      </main>
    </div>
  );
}
```

`frontend/src/index.css` — copy the Tailwind component layer verbatim from
`discovery/nextjs:app/globals.css` (badge-* and btn-* classes).

`frontend/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
```

`frontend/src/tests/setup.ts`:

```typescript
import "@testing-library/jest-dom";
```

`frontend/src/config/pipelines.json`:

```json
{
  "pipelines": {
    "dragen_germline": {
      "label": "DRAGEN Germline",
      "default_filters": {
        "gnomad_af_max": 0.01,
        "consequences": "stop_gained,frameshift_variant,splice_acceptor_variant,splice_donor_variant,missense_variant",
        "clinvar_exclude": "Benign,Likely_benign"
      }
    },
    "dragen_somatic": {
      "label": "DRAGEN Somatic",
      "default_filters": {
        "gnomad_af_max": 0.001,
        "consequences": "",
        "clinvar_exclude": ""
      }
    }
  }
}
```

Placeholder stub files (create empty exports for all pages/components so
`tsc` and `vite build` pass before they are implemented):

```bash
# Create stub files for components (default export — replaced in later milestones)
for f in \
  src/components/Navbar.tsx \
  src/components/WorkflowBadge.tsx \
  src/components/ClassificationBadge.tsx \
  src/components/PatientHeader.tsx \
  src/components/PatientListTable.tsx \
  src/components/SpecimenCard.tsx \
  src/components/VariantTable.tsx \
  src/components/WorkflowControl.tsx \
  src/components/ClassificationPanel.tsx \
  src/components/CriterionRow.tsx \
  src/components/UploadForm.tsx \
  src/pages/PatientsPage.tsx \
  src/pages/PatientDetailPage.tsx \
  src/pages/ClassificationPage.tsx \
  src/pages/UploadPage.tsx; do
  echo "export default function _Stub() { return null as unknown as JSX.Element; }" > frontend/$f
done
# Create stub files for lib modules (named exports — must not use default-export stub)
for f in \
  src/lib/api.ts \
  src/lib/classification-engine.ts \
  src/lib/display-utils.ts \
  src/lib/pipeline-config.ts; do
  echo "// stub" > frontend/$f
done
```

**Verification:** `cd frontend && npm ci && npm run build && npm test`
— build succeeds; 0 tests run (no test files yet).

---

## 4. Milestone 20 — `display-utils.ts` (PR 8)

### Red: write `src/tests/display-utils.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import {
  formatYearOfBirth,
  formatGnomadAf,
  formatRevel,
  formatSpliceAi,
  gnomadAfClass,
  revelClass,
  spliceAiClass,
} from "../lib/display-utils";

describe("formatYearOfBirth", () => {
  it("extracts 4-digit year from ISO date", () => {
    expect(formatYearOfBirth("1990-05-14")).toBe("1990");
  });
  it("returns em-dash for null", () => {
    expect(formatYearOfBirth(null)).toBe("—");
  });
  it("returns em-dash for undefined", () => {
    expect(formatYearOfBirth(undefined)).toBe("—");
  });
  it("handles year-only string", () => {
    expect(formatYearOfBirth("1990")).toBe("1990");
  });
});

describe("formatGnomadAf", () => {
  it("uses exponential notation below 0.0001", () => {
    expect(formatGnomadAf(0.00001)).toBe("1.00e-5");
  });
  it("uses 4 decimal places at or above 0.0001", () => {
    expect(formatGnomadAf(0.0123)).toBe("0.0123");
  });
  it("returns 'absent' for null", () => {
    expect(formatGnomadAf(null)).toBe("absent");
  });
});

describe("formatRevel", () => {
  it("formats to 3 decimal places", () => {
    expect(formatRevel(0.75)).toBe("0.750");
  });
  it("returns em-dash for null", () => {
    expect(formatRevel(null)).toBe("—");
  });
});

describe("formatSpliceAi", () => {
  it("formats to 3 decimal places", () => {
    expect(formatSpliceAi(0.8)).toBe("0.800");
  });
  it("returns em-dash for null", () => {
    expect(formatSpliceAi(null)).toBe("—");
  });
});

describe("gnomadAfClass", () => {
  it("returns amber class above 0.01", () => {
    expect(gnomadAfClass(0.05)).toBe("text-amber-600");
  });
  it("returns gray class at or below 0.01", () => {
    expect(gnomadAfClass(0.01)).toBe("text-gray-700");
  });
  it("returns gray class for null", () => {
    expect(gnomadAfClass(null)).toBe("text-gray-700");
  });
});

describe("revelClass", () => {
  it("returns red for score >= 0.7", () => {
    expect(revelClass(0.7)).toBe("text-red-600");
  });
  it("returns green for score <= 0.4", () => {
    expect(revelClass(0.4)).toBe("text-green-700");
  });
  it("returns gray for mid-range", () => {
    expect(revelClass(0.55)).toBe("text-gray-700");
  });
  it("returns gray for null", () => {
    expect(revelClass(null)).toBe("text-gray-700");
  });
});

describe("spliceAiClass", () => {
  it("returns orange for score >= 0.5", () => {
    expect(spliceAiClass(0.5)).toBe("text-orange-600");
  });
  it("returns gray below 0.5", () => {
    expect(spliceAiClass(0.3)).toBe("text-gray-700");
  });
  it("returns gray for null", () => {
    expect(spliceAiClass(null)).toBe("text-gray-700");
  });
});
```

### Green: implement `src/lib/display-utils.ts`

```typescript
export function formatYearOfBirth(dob: string | null | undefined): string {
  if (!dob) return "\u2014";
  const match = dob.match(/^(\d{4})(?:-|$)/);
  return match ? match[1] : "\u2014";
}

export function formatGnomadAf(af: number | null): string {
  if (af == null) return "absent";
  return af < 0.0001 ? af.toExponential(2) : af.toFixed(4);
}

export function formatRevel(v: number | null): string {
  return v == null ? "\u2014" : v.toFixed(3);
}

export function formatSpliceAi(v: number | null): string {
  return v == null ? "\u2014" : v.toFixed(3);
}

export function gnomadAfClass(af: number | null): string {
  return af != null && af > 0.01 ? "text-amber-600" : "text-gray-700";
}

export function revelClass(v: number | null): string {
  if (v == null) return "text-gray-700";
  if (v >= 0.7) return "text-red-600";
  if (v <= 0.4) return "text-green-700";
  return "text-gray-700";
}

export function spliceAiClass(v: number | null): string {
  return v != null && v >= 0.5 ? "text-orange-600" : "text-gray-700";
}
```

**Verification:** `cd frontend && npm test -- display-utils` — all tests green.

---

## 5. Milestone 21 — `classification-engine.ts` (PR 8)

### Red: write `src/tests/classification-engine.test.ts`

Four golden cases matching the Python backend golden fixtures:

```typescript
import { describe, it, expect } from "vitest";
import { classify, selectFramework } from "../lib/classification-engine";
import acgsCriteria from "../config/acgs-snv-criteria.json";
import svigCriteria from "../config/svig-criteria.json";

const acgsRules = acgsCriteria.combination_rules as {
  rule: string; codes: string[]; message: string
}[];
const svigRules = svigCriteria.combination_rules as {
  rule: string; codes: string[]; message: string
}[];

describe("ACGS SNV classification", () => {
  it("PVS1 + PM2 → Likely_Pathogenic (score 9)", () => {
    const result = classify(
      [
        { criterion_code: "PVS1", applied: true, strength: "very_strong" },
        { criterion_code: "PM2",  applied: true, strength: "supporting" },
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(9);
    expect(result.classification).toBe("Likely_Pathogenic");
    expect(result.warnings).toHaveLength(0);
  });

  it("No criteria → VUS (score 0)", () => {
    const result = classify([], "acgs_snv", acgsRules);
    expect(result.score).toBe(0);
    expect(result.classification).toBe("VUS");
  });

  it("BS1 + BS2 → Benign (score -8)", () => {
    const result = classify(
      [
        { criterion_code: "BS1", applied: true, strength: "strong" },
        { criterion_code: "BS2", applied: true, strength: "strong" },
      ],
      "acgs_snv",
      acgsRules
    );
    expect(result.score).toBe(-8);
    expect(result.classification).toBe("Benign");
  });
});

describe("SVIG classification", () => {
  it("O2 very_strong alone → Likely_Oncogenic (score 8)", () => {
    const result = classify(
      [{ criterion_code: "O2", applied: true, strength: "very_strong" }],
      "svig",
      svigRules
    );
    expect(result.score).toBe(8);
    expect(result.classification).toBe("Likely_Oncogenic");
  });
});

describe("selectFramework", () => {
  it("selects acgs_snv for germline", () => {
    expect(selectFramework("germline", "BRCA1").framework).toBe("acgs_snv");
  });
  it("selects svig for somatic", () => {
    expect(selectFramework("somatic", "TP53").framework).toBe("svig");
  });
});
```

### Green: implement `src/lib/classification-engine.ts`

Port directly from `discovery/nextjs:lib/classification-engine.ts`. Key points:

```typescript
export type Framework = "acgs_snv" | "svig";
export type Strength =
  | "very_strong"
  | "strong"
  | "moderate"
  | "supporting"
  | "standalone";

const BENIGN_POINTS: Record<Strength, number> = {
  standalone: -Infinity, // BA1 handled as override
  strong: -4,
  moderate: -2,
  supporting: -1,
  // pathogenic strengths not applicable here but Record requires them
  very_strong: 0,
};

const THRESHOLDS_ACGS = [
  { min: 10,   label: "Pathogenic" },
  { min: 6,    label: "Likely_Pathogenic" },
  { min: 0,    label: "VUS" },
  { min: -5,   label: "Likely_Benign" },
  { min: -Infinity, label: "Benign" },
];

// SVIG thresholds differ — see svig-criteria.json for exact values
// Port thresholds exactly from discovery/nextjs:lib/classification-engine.ts

export interface AppliedCriterion {
  criterion_code: string;
  applied: boolean;
  strength: Strength;
}

export interface ClassifyResult {
  score: number;
  classification: string;
  warnings: string[];
}

export function classify(
  criteria: AppliedCriterion[],
  framework: Framework,
  combinationRules: { rule: string; codes: string[]; message: string }[]
): ClassifyResult {
  // 1. Filter applied
  // 2. Sum weights
  // 3. Apply combination rules
  // 4. Apply thresholds
  // 5. Collect warnings
  // Full implementation: port from discovery/nextjs:lib/classification-engine.ts
  ...
}

export function selectFramework(
  caseType: "germline" | "somatic",
  _gene: string | null
): { framework: Framework } {
  return { framework: caseType === "germline" ? "acgs_snv" : "svig" };
}

export function classificationLabel(cls: string | null): string { ... }
export function classificationBadgeClass(cls: string | null): string { ... }
```

Copy the JSON config files from the backend:

```bash
cp backend/config/acgs-snv-criteria.json frontend/src/config/
cp backend/config/svig-criteria.json frontend/src/config/
```

**Verification:** `cd frontend && npm test -- classification-engine` — all 4 golden cases green.

---

## 6. Milestone 22 — `api.ts` (PR 8)

### Red: write `src/tests/api.test.ts`

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { listPatients, getPatient, ApiError, updateWorkflow } from "../lib/api";

beforeEach(() => { vi.restoreAllMocks(); });

describe("listPatients", () => {
  it("calls GET /api/patients and returns data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ patients: [], total: 0 }),
    }));
    const result = await listPatients();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/patients"),
      expect.any(Object)
    );
    expect(result.total).toBe(0);
  });

  it("throws ApiError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Unauthorised" }),
    }));
    await expect(listPatients()).rejects.toThrow(ApiError);
    await expect(listPatients()).rejects.toMatchObject({ status: 401 });
  });
});

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const e = new ApiError(404, "not found");
    expect(e).toBeInstanceOf(Error);
    expect(e.status).toBe(404);
    expect(e.detail).toBe("not found");
  });
});

describe("updateWorkflow", () => {
  it("calls PUT /api/workflow/{sampleId}", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sample_id: 10, status: "reviewing" }),
    }));
    await updateWorkflow(10, "reviewing", "analyst-1");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/workflow/10"),
      expect.objectContaining({ method: "PUT" })
    );
  });
});
```

### Green: implement `src/lib/api.ts`

```typescript
export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

function headers(): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, { ...init, headers: { ...headers(), ...init?.headers } });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(resp.status, detail);
  }
  return resp.json() as Promise<T>;
}

// --- Patient endpoints ---
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

// --- Sample endpoints ---
export async function deleteSample(id: number): Promise<void> {
  await request(`/api/samples/${id}`, { method: "DELETE" });
}

// --- Variant endpoints ---
export async function listVariants(
  sampleId: number,
  params?: VariantFilterParams
): Promise<VariantListResponse> {
  const q = new URLSearchParams({ sample_id: String(sampleId) });
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

// --- Upload / ingest ---
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

// --- Workflow ---
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

// --- Classification ---
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

// --- Config ---
export async function getCriteriaConfig(framework: string): Promise<CriteriaConfigResponse> {
  return request(`/api/config/criteria/${framework}`);
}
```

Add all TypeScript interface types (from DESIGN.md §4) to
`src/lib/api.ts` or a co-located `src/lib/types.ts`.

**Verification:** `cd frontend && npm test -- api.test` — all tests green.

---

## 7. Milestone 23 — Shared components (PR 9)

### Red: write component render tests

`src/tests/PatientHeader.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PatientHeader from "../components/PatientHeader";

const patient = { id: 1, lab_number: "LAB-2026-001", name: "Jane Smith", created_at: null, samples: [] };

describe("PatientHeader", () => {
  it("displays lab_number", () => {
    render(<PatientHeader patient={patient} />);
    expect(screen.getByText("LAB-2026-001")).toBeInTheDocument();
  });

  it("does not display patient name", () => {
    render(<PatientHeader patient={patient} />);
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });
});
```

`src/tests/WorkflowBadge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import WorkflowBadge from "../components/WorkflowBadge";

describe("WorkflowBadge", () => {
  it.each([
    ["pending",   "Pending",   "badge-pending"],
    ["reviewing", "Reviewing", "badge-reviewing"],
    ["reported",  "Reported",  "badge-reported"],
    ["archived",  "Archived",  "badge-archived"],
  ])("renders %s with correct label and class", (status, label, cls) => {
    render(<WorkflowBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toHaveClass(cls);
  });

  it("falls back gracefully for unknown status", () => {
    render(<WorkflowBadge status="unknown" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});
```

`src/tests/ClassificationBadge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ClassificationBadge from "../components/ClassificationBadge";

describe("ClassificationBadge", () => {
  it.each([
    ["Pathogenic",       "Pathogenic",       "badge-pathogenic"],
    ["Likely_Pathogenic","Likely Pathogenic", "badge-likely-pathogenic"],
    ["VUS",              "VUS",               "badge-vus"],
    ["Likely_Benign",    "Likely Benign",     "badge-likely-benign"],
    ["Benign",           "Benign",            "badge-benign"],
  ])("renders %s correctly", (cls, label, cssClass) => {
    render(<ClassificationBadge classification={cls} />);
    expect(screen.getByText(label)).toHaveClass(cssClass);
  });

  it("renders em-dash for null", () => {
    render(<ClassificationBadge classification={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
```

`src/tests/PatientListTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import PatientListTable from "../components/PatientListTable";
import type { PatientSummary } from "../lib/api";

vi.mock("../lib/api", () => ({ deletePatient: vi.fn() }));

const patient: PatientSummary = {
  id: 1,
  lab_number: "LAB-2026-001",
  // dob removed — migration 004
  name: null,
  sample_count: 2,
  latest_sample_id: 10,
  latest_sample_name: "SPECIMEN_A",
  latest_workflow_status: "pending",
  latest_ingested_at: "2026-04-01T12:00:00Z",
  pipeline_key: "dragen_germline",
};

function renderTable() {
  return render(
    <MemoryRouter>
      <PatientListTable patients={[patient]} onDelete={vi.fn()} />
    </MemoryRouter>
  );
}

describe("PatientListTable", () => {
  it("shows MRN column header", () => {
    renderTable();
    expect(screen.getByRole("columnheader", { name: /mrn/i })).toBeInTheDocument();
  });

  it("displays lab_number as primary identifier", () => {
    renderTable();
    expect(screen.getByText("LAB-2026-001")).toBeInTheDocument();
  });

  it("does not show NHS number column or value", () => {
    renderTable();
    expect(screen.queryByRole("columnheader", { name: /nhs/i })).not.toBeInTheDocument();
  });

  it("does not show patient name", () => {
    renderTable();
    expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument();
  });

  it("renders WorkflowBadge for latest status", () => {
    renderTable();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders View → link", () => {
    renderTable();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute(
      "href",
      "/patients/1"
    );
  });
});
```

### Green: implement shared components

Implement verbatim from `discovery/nextjs` equivalents, replacing:
- `next/link` → `<Link>` from `react-router-dom`
- `useRouter()` → `useNavigate()` from `react-router-dom`
- `router.push(url)` → `navigate(url)`
- `router.refresh()` → `navigate(0)` (React Router force reload)
- All direct DB calls removed (data comes via props from pages)

Components to implement: `Navbar`, `WorkflowBadge`, `ClassificationBadge`,
`PatientHeader`, `PatientListTable` (includes inline `DeletePatientButton`
logic or as a sibling file).

**Verification:** `cd frontend && npm test -- WorkflowBadge ClassificationBadge PatientListTable PatientHeader` — all green.

---

## 8. Milestone 24 — Specimen and variant components (PR 9)

### Red: write `src/tests/SpecimenCard.test.tsx` and `WorkflowControl.test.tsx`

`src/tests/WorkflowControl.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import WorkflowControl from "../components/WorkflowControl";
import * as api from "../lib/api";

vi.mock("../lib/api");

describe("WorkflowControl", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders transition buttons for pending status", () => {
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    expect(screen.getByRole("button", { name: /reviewing/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /archived/i })).toBeInTheDocument();
  });

  it("renders no buttons for archived status (terminal)", () => {
    render(<WorkflowControl sampleId={1} currentStatus="archived" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls updateWorkflow and updates status on success", async () => {
    vi.mocked(api.updateWorkflow).mockResolvedValue({
      sample_id: 1,
      status: "reviewing",
    });
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    fireEvent.click(screen.getByRole("button", { name: /reviewing/i }));
    await waitFor(() =>
      expect(api.updateWorkflow).toHaveBeenCalledWith(1, "reviewing", expect.any(String))
    );
  });

  it("shows error message on API failure", async () => {
    vi.mocked(api.updateWorkflow).mockRejectedValue(
      new api.ApiError(409, "Concurrent modification")
    );
    render(<WorkflowControl sampleId={1} currentStatus="pending" />);
    fireEvent.click(screen.getByRole("button", { name: /reviewing/i }));
    await waitFor(() =>
      expect(screen.getByText(/concurrent modification/i)).toBeInTheDocument()
    );
  });
});
```

`src/tests/SpecimenCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import SpecimenCard from "../components/SpecimenCard";
import type { SampleDetail } from "../lib/api";

vi.mock("../lib/api");

const specimen: SampleDetail = {
  id: 5,
  name: "SPEC_001",
  vcf_filename: "sample.vcf.gz",
  s3_key: "runs/2026-01-01/sample.vcf.gz",
  pipeline_key: "dragen_germline",
  case_type: "germline",
  tissue: "blood",
  sequencing_date: "2026-01-01",
  ingested_at: "2026-01-02T10:00:00Z",
  workflow_status: "pending",
  workflow_updated_at: null,
  variant_count: 42,
};

describe("SpecimenCard", () => {
  it("renders specimen name", () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    expect(screen.getByText("SPEC_001")).toBeInTheDocument();
  });

  it("renders variant count", () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    expect(screen.getByText(/42 variants/i)).toBeInTheDocument();
  });

  it("renders case type badge", () => {
    render(
      <MemoryRouter>
        <SpecimenCard specimen={specimen} patientId={1} />
      </MemoryRouter>
    );
    expect(screen.getByText(/germline/i)).toBeInTheDocument();
  });
});
```

### Green: implement `SpecimenCard`, `WorkflowControl`, `DeleteSampleButton`, `VariantTable`

Port from `discovery/nextjs` equivalents. `VariantTable` uses:
- `import { useReactTable, ... } from "@tanstack/react-table"` (same as Next.js reference)
- `fetch("/api/samples/${sampleId}/variants?${params}")` directly, reads `json.items` (not `json.rows`)

`src/tests/VariantTable.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import VariantTable from "../components/VariantTable";

beforeEach(() => { vi.restoreAllMocks(); });

describe("VariantTable", () => {
  it("renders loading state then rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{
          id: 1, chrom: "17", pos: 43094077, ref: "A", alt: "T",
          gene: "BRCA1", consequence: "missense_variant",
          hgvs_c: "c.5096G>A", hgvs_p: "p.Arg1699Gln",
          gnomad_af: 0.000012, clinvar_sig: null,
          revel_score: 0.892, spliceai_max: 0.01,
          classification: null, score: null, framework: null, locked_at: null,
        }],
        total: 1, limit: 50, offset: 0,
      }),
    }));
    render(
      <MemoryRouter>
        <VariantTable
          sampleId={10}
          patientId={1}
          defaultFilters={{ gnomad_af_max: 0.01, consequences: "", clinvar_exclude: "" }}
          pipelineKey="dragen_germline"
        />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText("BRCA1")).toBeInTheDocument());
  });

  it("shows empty state when no variants match", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    }));
    render(
      <MemoryRouter>
        <VariantTable
          sampleId={10}
          patientId={1}
          defaultFilters={{ gnomad_af_max: 0.01, consequences: "", clinvar_exclude: "" }}
          pipelineKey={null}
        />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/no variants match/i)).toBeInTheDocument()
    );
  });
});
```

**Verification:** `cd frontend && npm test -- SpecimenCard WorkflowControl VariantTable` — all green.

---

## 9. Milestone 25 — Classification components (PR 10)

### Red: write `src/tests/ClassificationPanel.test.tsx`

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ClassificationPanel from "../components/ClassificationPanel";
import * as api from "../lib/api";

vi.mock("../lib/api");

const baseProps = {
  variantId: 100,
  caseType: "germline" as const,
  gene: "BRCA1",
  initialClassification: null,
  initialCriteria: [],
};

describe("ClassificationPanel", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows score of 0 and VUS with no criteria applied", () => {
    render(<ClassificationPanel {...baseProps} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("VUS")).toBeInTheDocument();
  });

  it("shows framework selector (unlocked initially)", () => {
    render(<ClassificationPanel {...baseProps} />);
    const selector = screen.getByRole("combobox");
    expect(selector).not.toBeDisabled();
  });

  it("renders Save draft and Confirm buttons", () => {
    render(<ClassificationPanel {...baseProps} />);
    expect(screen.getByRole("button", { name: /save draft/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
  });

  it("calls putClassification on Confirm", async () => {
    vi.mocked(api.putClassification).mockResolvedValue({
      score: 0,
      classification: "VUS",
      classification_id: 1,
    });
    render(<ClassificationPanel {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() =>
      expect(api.putClassification).toHaveBeenCalledWith(
        100,
        expect.objectContaining({ locked_by: expect.any(String) })
      )
    );
  });

  it("shows Reset button when locked", () => {
    render(
      <ClassificationPanel
        {...baseProps}
        initialClassification={{
          id: 1,
          framework: "acgs_snv",
          framework_version: "ACGS 2024",
          score: 9,
          classification: "Likely_Pathogenic",
          locked_at: "2026-05-01T10:00:00Z",
          locked_by: "analyst-1",
        }}
        initialCriteria={[]}
      />
    );
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save draft/i })).not.toBeInTheDocument();
  });

  it("calls resetClassification on confirmed reset", async () => {
    vi.mocked(api.resetClassification).mockResolvedValue({
      new_classification_id: 2,
    });
    render(
      <ClassificationPanel
        {...baseProps}
        initialClassification={{
          id: 1,
          framework: "acgs_snv",
          framework_version: "ACGS 2024",
          score: 0,
          classification: "VUS",
          locked_at: "2026-05-01T10:00:00Z",
          locked_by: "analyst-1",
        }}
        initialCriteria={[]}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    fireEvent.click(await screen.findByRole("button", { name: /yes, reset/i }));
    await waitFor(() =>
      expect(api.resetClassification).toHaveBeenCalledWith(100, 1, expect.any(String))
    );
  });
});
```

### Green: implement `CriterionRow` and `ClassificationPanel`

Port from `discovery/nextjs:app/patients/[id]/variants/[variantId]/ClassificationPanel.tsx`
and inline `CriterionRow` or extract to `src/components/CriterionRow.tsx`.

Port from `discovery/nextjs:app/patients/[id]/variants/[variantId]/ClassificationPanel.tsx`
and inline `CriterionRow` or extract to `src/components/CriterionRow.tsx`.

Add `src/tests/CriterionRow.test.tsx` (required for Invariant 3):

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import CriterionRow from "../components/CriterionRow";

const def = {
  code: "PVS1",
  description: "Null variant",
  category: "population",
  direction: "pathogenic",
  default_strength: "very_strong",
  adjustable: false,
  permitted_strengths: ["very_strong"],
};

const crit = {
  criterion_code: "PVS1",
  applied: true,
  strength: "very_strong" as const,
  notes: "",
  evidence_links: [],
  pre_computed: false,
  pre_computed_value: null,
};

describe("CriterionRow", () => {
  it("renders criterion code and description", () => {
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={vi.fn()} />);
    expect(screen.getByText("PVS1")).toBeInTheDocument();
  });

  it("rejects javascript: evidence links (Invariant 3)", () => {
    const onChange = vi.fn();
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={onChange} />);
    // Expand notes/links panel
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "javascript:alert(1)" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    // onChange must not have been called with the malicious link
    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ evidence_links: expect.arrayContaining(["javascript:alert(1)"]) })
    );
  });

  it("accepts https: evidence links", () => {
    const onChange = vi.fn();
    render(<CriterionRow def={def} crit={crit} locked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add notes/i }));
    const input = screen.getByPlaceholderText(/https/i);
    fireEvent.change(input, { target: { value: "https://www.ncbi.nlm.nih.gov/snp/rs12345" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        evidence_links: ["https://www.ncbi.nlm.nih.gov/snp/rs12345"],
      })
    );
  });

  it("disables all inputs when locked", () => {
    render(<CriterionRow def={def} crit={crit} locked={true} onChange={vi.fn()} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});
```

Changes from reference:
- Replace `fetch("/api/classification", ...)` calls with `api.putClassification()` and `api.resetClassification()`.
- Replace `import acgsCriteria from "@/config/acgs-snv-criteria.json"` with
  `import acgsCriteria from "../config/acgs-snv-criteria.json"`.
- `user_id` from `import.meta.env.VITE_USER_ID ?? "analyst"`.

**Verification:** `cd frontend && npm test -- ClassificationPanel CriterionRow` — all tests green.

---

## 10. Milestone 26 — Upload form, pages, full build (PR 11)

### Red: write `src/tests/UploadForm.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import UploadForm from "../components/UploadForm";

const pipelineOptions = [{ key: "dragen_germline", label: "DRAGEN Germline" }];

describe("UploadForm", () => {
  it('shows "Specimen" section heading', () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText("Specimen")).toBeInTheDocument();
  });

  it('shows "Specimen name" label', () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText("Specimen name")).toBeInTheDocument();
  });

  it("does not show NHS number field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.queryByText(/nhs number/i)).not.toBeInTheDocument();
  });

  it("does not show patient name field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.queryByText(/patient name/i)).not.toBeInTheDocument();
  });

  it("shows lab record number as required field", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByText(/lab record number/i)).toBeInTheDocument();
  });

  it("shows Upload VCF submit button", () => {
    render(<MemoryRouter><UploadForm pipelineOptions={pipelineOptions} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /upload vcf/i })).toBeInTheDocument();
  });
});
```

### Green: implement `UploadForm` and all pages

**`UploadForm`** — port from `discovery/nextjs:app/upload/UploadForm.tsx`.
Changes:
- Replace `process.env.NODE_ENV` with `import.meta.env.VITE_APP_ENV`.
- Replace `fetch("/api/ingest-upload", ...)` dev path with `fetch("/api/ingest-direct", ...)` (requires M_pre8 — `POST /api/ingest-direct` accepts `multipart/form-data` with the VCF file and patient/specimen fields).
- Replace `fetch("/api/upload-url", ...)` prod path with `api.getUploadUrl(...)`.

**Pages** — thin wrappers that:
- Call `useState` + `useEffect` to fetch data on mount.
- Pass data as props to child components.
- Show inline error banners on failure.
- Use React Router `useParams()` for route parameters.
- Use `<Navigate to="/" />` for 404 cases.

Example `PatientsPage`:

```tsx
import { useState, useEffect } from "react";
import { listPatients, ApiError, type PatientSummary } from "../lib/api";
import PatientListTable from "../components/PatientListTable";
import { Link } from "react-router-dom";

export default function PatientsPage() {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPatients()
      .then((r) => setPatients(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.detail : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Cases</h1>
          {!loading && (
            <p className="text-sm text-gray-500 mt-0.5">
              {patients.length} case{patients.length !== 1 ? "s" : ""} in system
            </p>
          )}
        </div>
        <Link to="/upload" className="btn btn-primary">Upload VCF</Link>
      </div>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 mb-6 text-sm text-red-700">
          {error}
        </div>
      )}
      {!loading && patients.length === 0 && !error && (
        <div className="text-center py-16 text-gray-400">
          <p>No cases yet.</p>
        </div>
      )}
      {patients.length > 0 && (
        <PatientListTable
          patients={patients}
          onDelete={(id) => setPatients((p) => p.filter((x) => x.id !== id))}
        />
      )}
    </div>
  );
}
```

**Verification:**

```bash
cd frontend
npm test               # all tests green
tsc --noEmit           # no TypeScript errors
npm run build          # dist/ built without errors
docker build -t vv-frontend .  # Docker image builds
```

---

## 11. Final checks

```bash
cd frontend

# Run all tests
npm test

# TypeScript check
npx tsc --noEmit

# Production build
npm run build

# Verify no PII fields displayed in components
grep -r "nhs_number" src/components/ src/pages/
# Expected: no matches (or comments only)

# Verify API key not logged
grep -r "VITE_API_KEY" src/lib/api.ts
# Expected: only the header assignment — no console.log, no Error message interpolation
```

---

## 12. Future work (PRs not in scope here)

- **PR 12** — ECS task definition update; nginx container config (`/api` proxy_pass);
  CloudFront distribution; E2E tests against deployed stack; OIDC ALB integration.
- **Debounced variant filter** — avoid fetching on every keystroke.
- **Patient list pagination** — add `limit`/`offset` controls to `PatientsPage`.
- **Inline evidence link validation** — replace `alert()` with inline validation message.
