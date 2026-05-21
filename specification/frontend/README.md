# variant-viewer frontend — React SPA (PRs 8–11)

A React 18 single-page application for clinical variant review and classification,
served as static assets and communicating exclusively with the FastAPI backend
(PRs 6–7). It is a port of the Next.js 15 prototype on `discovery/nextjs` into
a framework-agnostic Vite + React + TailwindCSS SPA, preserving all screens and
interactions from the reference implementation.

## What this SPA does

1. **Lists patients** — paginated table of all cases with MRN, year of birth,
   specimen count, latest workflow status, and ingest date.
2. **Shows patient detail** — patient header plus one `SpecimenCard` per
   specimen, each containing a filterable, paginated variant table.
3. **Classifies variants** — criterion checkbox panel grouped by evidence
   category; live score/label computed locally; Save draft and Confirm actions
   persist to the backend.
4. **Uploads VCFs** — multi-step form (patient → specimen → pipeline → file)
   that in production calls `POST /api/upload-url` + S3 presigned PUT; in dev
   posts directly to `POST /api/ingest` via `multipart/form-data`.
5. **Manages workflow** — inline `→ reviewing / → reported / → archived` buttons
   on each specimen card; calls `PUT /api/workflow/{sample_id}`.
6. **Deletes patients and specimens** — guarded confirm-in-place UI before
   calling `DELETE /api/patients/{id}` or `DELETE /api/samples/{id}`.

## Status of this document set

These documents are the **complete design and build specification** for PRs 8–11.
A fresh agent session or a human developer should be able to open this directory,
read the files in order, and build the working, tested SPA without needing the
original conversation.

Read in this order:

1. **README.md** (this file) — orientation, layout, quick start, non-goals
2. **DESIGN.md** — component architecture, API contract, state model, styling
   conventions, testing strategy, compliance alignment
3. **IMPLEMENTATION.md** — milestone-by-milestone TDD build plan (M19–M26)
   with full component and test code sketches
4. **REFERENCE.md** — API endpoint catalogue, env vars, CSS class reference,
   pipeline config schema, external dependencies

## Project layout (target)

```
frontend/
├── index.html                     # Vite entry — mounts <div id="root">
├── vite.config.ts                 # Vite + Vitest config: React plugin, /api proxy to backend, jsdom test environment
├── tailwind.config.ts             # Content paths, custom fonts (Inter, JetBrains Mono)
├── postcss.config.ts              # Tailwind + autoprefixer
├── tsconfig.json                  # Strict TS; path alias @ → src/
├── package.json                   # Dependencies (React 18, Vite, Tailwind, TanStack Table, Vitest)
├── src/
│   ├── main.tsx                   # ReactDOM.createRoot; wraps <App> in <BrowserRouter>
│   ├── App.tsx                    # Top-level: <Navbar> + <Routes> (React Router v6)
│   ├── index.css                  # Tailwind directives; .badge-* and .btn-* component classes
│   ├── lib/
│   │   ├── api.ts                 # Typed fetch wrappers for every backend endpoint
│   │   ├── classification-engine.ts  # Port of discovery/nextjs:lib/classification-engine.ts
│   │   ├── display-utils.ts       # formatYearOfBirth; gnomAD/REVEL/SpliceAI formatters
│   │   └── pipeline-config.ts     # Loads pipelines.yaml equivalent from /api/config/criteria
│   ├── components/
│   │   ├── Navbar.tsx             # Top nav: "Variant Viewer" logo, Cases link, Upload VCF link
│   │   ├── WorkflowBadge.tsx      # Coloured badge for pending/reviewing/reported/archived
│   │   ├── ClassificationBadge.tsx # Coloured badge for P/LP/VUS/LB/B/Oncogenic/Likely_Oncogenic
│   │   ├── PatientListTable.tsx   # Table: MRN, YOB, Specimens, Latest specimen, Pipeline, Workflow, Ingested, View →, Delete
│   │   ├── PatientHeader.tsx      # White card: MRN + YOB
│   │   ├── SpecimenCard.tsx       # White card header + <VariantTable>; holds WorkflowControl + DeleteSampleButton
│   │   ├── VariantTable.tsx       # TanStack Table; filter bar; server-side pagination + sorting
│   │   ├── WorkflowControl.tsx    # → reviewing / → reported / → archived buttons; calls PUT /api/workflow/{id}
│   │   ├── ClassificationPanel.tsx # Criteria checkboxes; live score; Save draft / Confirm; Reset
│   │   └── CriterionRow.tsx       # Single criterion: checkbox, strength selector, notes, evidence links
│   └── pages/
│       ├── PatientsPage.tsx       # Route /  — fetches GET /api/patients; renders <PatientListTable>
│       ├── PatientDetailPage.tsx  # Route /patients/:id — fetches patient (samples nested in response); renders <SpecimenCard>s
│       ├── ClassificationPage.tsx # Route /patients/:patientId/variants/:variantId — variant detail + <ClassificationPanel>
│       └── UploadPage.tsx         # Route /upload — renders <UploadForm>
└── src/tests/
    ├── PatientListTable.test.tsx
    ├── PatientHeader.test.tsx
    ├── SpecimenCard.test.tsx
    ├── WorkflowBadge.test.tsx
    ├── ClassificationBadge.test.tsx
    ├── UploadForm.test.tsx
    ├── WorkflowControl.test.tsx
    ├── ClassificationPanel.test.tsx
    ├── display-utils.test.ts
    └── api.test.ts
```

## Quick start (once built)

```bash
# 1. Install dependencies
cd frontend
npm ci

# 2. Configure API proxy (dev only — proxies /api/* to local FastAPI)
#    Already set in vite.config.ts; ensure backend is running on :8000

# 3. Run tests
npm test

# 4. Start dev server (http://localhost:5173)
npm run dev

# 5. Production build
npm run build          # outputs to frontend/dist/
docker build -t vv-frontend .
```

## Target user

Clinical bioinformaticians at East Genomics NHS Trust who review, filter, and
classify germline and somatic variants as part of diagnostic reporting. They
work within a guarded clinical environment and require a clear, responsive
interface that enforces the ACGS SNV and SVIG-UK classification frameworks
without exposing raw database operations.

## Non-goals

- **No server-side rendering** — the SPA is purely static; all data fetching
  happens client-side via the FastAPI REST API.
- **No authentication UI** — the API key is injected at the nginx/ALB layer;
  the SPA does not present a login screen.
- **No real-time updates** — no WebSockets or polling; users refresh manually.
- **No patient PII display** — name and NHS number are stored in the backend
  but the SPA shows only MRN (lab_number) and year of birth, matching the
  reference implementation.
- **No direct database access** — the SPA calls only the FastAPI endpoints
  defined in PRs 6–7; it never connects to PostgreSQL or S3 directly.
- **No offline support** — no service worker or local caching.
- **No mobile-first design** — designed for desktop clinical workstations
  (≥1280 px); responsive enough to be usable but not optimised for mobile.
- **No i18n** — English only.
