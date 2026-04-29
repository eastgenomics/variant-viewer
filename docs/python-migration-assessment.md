# Python Migration Assessment: variant-viewer

**Prepared for:** CUH Bioinformatics Team  
**Date:** 2026-04-25  
**Current stack:** Next.js 15 (App Router) + TypeScript, ECS Fargate, RDS PostgreSQL, Lambda, S3  
**Assessment scope:** Feasibility and effort of converting to a Python web framework

---

## 1. What the Application Currently Does

Before evaluating the migration, it is worth understanding how Next.js is being used. Next.js is doing double duty:

- **Backend API server** — nine REST endpoints under `app/api/` handle variant queries, ACGS/SVIG classification CRUD, patient/sample management, VCF ingest orchestration, and S3 pre-signed URL generation.
- **Frontend server + React runtime** — server-rendered and client-rendered React pages that include complex interactive components: a paginated, sortable variant table, a multi-criterion classification panel, and a multi-step upload form.

The business logic layer (`lib/`) is pure functions: a VCF parser, a FHIR-manifest parser, the ACGS SNV / SVIG-UK classification scoring engine, a pre-compute criteria pipeline, and a database connection pool. A separate Lambda function (`lambda/ingest-handler.ts`) re-uses the same ingest logic for asynchronous S3-triggered ingestion.

**Approximate source size (main source files):**

| Area | Lines |
|---|---|
| React frontend components | ~1,600 |
| API routes (9 endpoints) | ~750 |
| Business logic (`lib/`) | ~1,100 |
| Lambda handler | ~90 |
| Tests | ~500 |
| **Total** | **~4,050** |

---

## 2. Migration Architectures

A "Python conversion" is not a single option — there are three meaningfully different architectures, each with a different effort profile.

### Option A — Python API back-end + React front-end (decoupled SPA)

Replace Next.js with a Python framework (FastAPI recommended) for all API endpoints and business logic. The React frontend is decoupled from Next.js, rebuilt as a static single-page application using Vite, and served from S3/CloudFront or as static files from the same container.

- **What changes:** Everything in `app/api/` and `lib/` is rewritten in Python. The React components are re-scaffolded without Next.js primitives (`NextRequest`, `NextResponse`, `next/link`, `next/image`, etc.) but the component logic itself is largely preserved.
- **What stays the same:** All React UI code (VariantTable, ClassificationPanel, UploadForm) is kept and adapted, not rewritten. Tailwind CSS, TanStack Table, and the overall UX are unchanged.
- **Infrastructure changes:** Replace the Next.js Dockerfile with a Python/FastAPI image. Lambda rewritten in Python (boto3, psycopg2). CDN or static serving added for the frontend bundle.

### Option B — Full Python stack with server-rendered templates (HTMX + Jinja2)

Replace both the Next.js backend and the React frontend with a Python framework (FastAPI or Flask) using Jinja2 templates and HTMX for interactivity. No JavaScript framework.

- **What changes:** Everything. All React components are converted to HTML templates with HTMX attributes. Client-side state (sorting, pagination, criterion toggling, classification scoring) is moved server-side or replaced with HTMX partial-page updates.
- **What stays the same:** Database schema, SQL queries, AWS integration patterns.
- **Infrastructure changes:** Same as Option A — simpler in that no separate static asset pipeline is needed.

### Option C — Django full-stack

Use Django with Django REST Framework for the API and Django templates + HTMX (or Django admin) for the UI.

- **What changes:** Same scope as Option B, plus adoption of Django's ORM (replacing raw SQL queries), Django's migration system (replacing the current `scripts/migrate.js`), and Django's auth/session framework.
- **What stays the same:** Database schema could be preserved or mapped to Django models.
- **Infrastructure changes:** Same as Option A.

---

## 3. Effort Assessment by Component

### 3.1 Business Logic (`lib/`) — **Low-to-Medium effort, all options**

This is the most straightforward part of the migration. The TypeScript business logic is a natural fit for Python:

| Module | TS lines | Python equivalent | Notes |
|---|---|---|---|
| `vcf-parser.ts` | 243 | `vcf_parser.py` | Stream-based VCF parsing maps well to Python generators. `pysam` could replace the hand-rolled parser entirely. |
| `classification-engine.ts` | 236 | `classification_engine.py` | Pure functions with no external dependencies. Straightforward line-by-line translation. |
| `pre-compute-criteria.ts` | 242 | `pre_compute_criteria.py` | Pure logic; Python dataclasses map cleanly to the TypeScript interfaces. |
| `fhir-manifest.ts` | 238 | `fhir_manifest.py` | JSON parsing and data extraction; idiomatic in Python. |
| `ingest.ts` | 308 | `ingest.py` | Uses `boto3` (S3), `psycopg2`/`asyncpg` (DB). Excellent Python ecosystem support. |
| `db.ts` | 88 | `db.py` | Connection pooling with `psycopg2` + `psycopg2-pool`, or `SQLAlchemy` with asyncpg. |

**The classification engine is a particularly good candidate** — the ACGS SNV and SVIG-UK scoring algorithms are pure numeric logic over JSON-defined rules. Python's scientific computing background (and the team's likely familiarity with similar scoring logic) makes this a natural fit. The JSON config files (`acgs-snv-criteria.json`, `svig-criteria.json`) are framework-agnostic and carry over unchanged.

The VCF parsing module could leverage `pysam` or `cyvcf2`, which are mature bioinformatics Python libraries that may perform better than the hand-rolled Node.js stream parser.

### 3.2 API Routes — **Low effort (FastAPI/Flask), all options**

Nine REST endpoints with clear, well-separated responsibilities. All follow standard CRUD patterns:

| Route | Methods | Complexity |
|---|---|---|
| `/api/variants` | GET | Medium (parameterised SQL filtering, pagination, sorting) |
| `/api/classification` | GET, POST, PATCH, DELETE | High (transaction logic, locking, soft-delete, audit log) |
| `/api/patients` | GET, DELETE | Low |
| `/api/samples` | GET | Low |
| `/api/ingest` | POST | Medium |
| `/api/ingest-upload` | POST | Medium |
| `/api/upload-url` | POST | Low (S3 presigned URL) |
| `/api/workflow` | POST | Low |
| `/api/health` | GET | Trivial |

FastAPI is recommended over Flask for this workload because:
- Async support handles I/O-bound DB and S3 calls efficiently.
- Pydantic models replace the TypeScript interfaces used for request/response validation — a natural fit.
- Automatic OpenAPI documentation is useful for a clinical tool that may need to integrate with other systems.
- Type annotations bring the team's Python closer to the type-safe discipline already established in the TypeScript codebase.

### 3.3 React Frontend — **The critical variable**

This is where the three options diverge significantly.

**Option A (keep React):**  
The React components themselves contain no Next.js-specific logic that cannot be replaced. The main changes are:
- Remove `NextRequest`/`NextResponse` imports (these are API-layer only, not in components).
- Replace `next/link` with standard `<a>` tags or React Router's `<Link>`.
- Replace `next/image` (not used in this codebase) if applicable.
- Replace the Next.js file-based routing with React Router.
- The client components are already marked `"use client"` — they are already decoupled from server-side rendering.

The two most complex components are `VariantTable.tsx` (388 lines, TanStack Table, server-fetched pagination/sorting) and `ClassificationPanel.tsx` (589 lines, complex criterion state management, live scoring). These are **kept as-is in Option A** — only the hosting mechanism changes.

Estimated React adaptation effort: **~3–5 days** for a developer not familiar with Vite/React Router, primarily in scaffolding and routing.

**Option B / C (replace React with templates):**  
The ClassificationPanel is the dominant risk. It manages:
- Per-criterion toggled state (applied/not applied, strength selection).
- Live client-side score recalculation on every toggle (calling `classify()` in-browser).
- Evidence link validation and addition.
- Framework switching (ACGS SNV vs. SVIG).
- Optimistic UI for save/lock/delete.

Faithfully replicating this in HTMX with server-round-trips on every criterion toggle is achievable but would require careful design of partial-update endpoints and would likely result in slightly degraded interactivity compared to the current React-driven live scoring. The VariantTable (sorting, pagination, filtering) translates more naturally to HTMX.

Estimated template rewrite effort: **~4–8 weeks** for a single developer, including testing and QA.

### 3.4 Lambda Ingest Handler — **Low effort**

The Lambda (`lambda/ingest-handler.ts`, 89 lines) is a thin wrapper that calls the shared ingest logic. Python Lambda with `boto3` is the dominant pattern for S3-triggered workflows. The AWS Lambda Python runtime has excellent tooling. The Terraform `lambda.tf` would need updating (runtime `python3.12`, handler path, dependency packaging), but the logic is straightforward.

### 3.5 Infrastructure and Deployment — **Low effort (Option A), Minimal (Options B/C)**

The ECS Fargate, RDS, ALB, S3, Secrets Manager, and VPC infrastructure is Python-agnostic. The only changes required are:

- Replace the Node.js Dockerfile with a Python image (e.g. `python:3.12-slim`).
- Replace the `npm run build` step with `pip install -r requirements.txt`.
- Update the Lambda Terraform resource for Python runtime.
- For Option A: add a static asset serving mechanism (S3/CloudFront, or serve from FastAPI's `StaticFiles`).

The existing Terraform, Docker Compose, SQL migrations, and JSON configuration files are unchanged.

### 3.6 Tests — **Medium effort**

Current tests cover React components (7 test files using Jest + React Testing Library). In Option A, these can be migrated to Vitest + React Testing Library with minimal changes. In Options B/C, the component tests are replaced with Python tests (pytest) for the server-side template logic, and possibly Playwright/Selenium for end-to-end testing of HTMX interactions.

The business logic tests (currently absent but implicitly tested via integration) would benefit from a Python test suite using pytest, which the team is likely already familiar with.

---

## 4. Summary Effort Table

| Component | Option A (FastAPI + React SPA) | Option B (FastAPI + HTMX) | Option C (Django + HTMX) |
|---|---|---|---|
| Business logic (`lib/`) | 1–2 weeks | 1–2 weeks | 1–2 weeks |
| API routes | 1 week | 1 week | 1 week |
| React frontend | 3–5 days (adaptation) | 4–8 weeks (full rewrite) | 4–8 weeks (full rewrite) |
| Lambda handler | 1–2 days | 1–2 days | 1–2 days |
| Infrastructure / Docker | 1–2 days | 1–2 days | 1–2 days |
| Tests | 1 week | 1–2 weeks | 1–2 weeks |
| **Total estimate** | **~4–6 weeks** | **~10–16 weeks** | **~10–16 weeks** |

*Estimates assume a single developer with strong Python skills and working familiarity with the codebase. NHS team working patterns (e.g. part-time capacity, clinical commitments) will extend calendar time accordingly.*

---

## 5. Pros and Cons

### Option A — FastAPI + React SPA

**Pros**
- **Shortest migration path.** React UI components are preserved almost intact — the highest-risk parts of the application (ClassificationPanel, VariantTable) are not touched.
- **Python backend plays to team strengths.** All server-side logic (VCF parsing, classification engine, DB queries, AWS SDK) is in Python, where the team is most productive.
- **Excellent bioinformatics library access.** `pysam`, `cyvcf2`, `pandas`, `hail` and other genomics tools are available in the backend without JavaScript interop workarounds.
- **FastAPI is production-grade.** Used widely in clinical and research genomics APIs; well-documented; async-native for I/O-heavy workloads; automatic OpenAPI spec generation is useful for auditability.
- **Infrastructure is minimally changed.** No ECS redesign required; Terraform changes are small.
- **React ecosystem maturity is retained.** TanStack Table, form libraries, and component ecosystems remain available.

**Cons**
- **Two language runtimes remain.** The team still needs to maintain TypeScript/JavaScript knowledge for the React frontend. This is the main objection to this option.
- **Additional complexity from decoupling.** Splitting a monolithic Next.js app into a Python API and a static React SPA introduces a new build pipeline (Vite), CORS configuration, and separate deployment artefacts.
- **No elimination of JavaScript tooling.** npm, node_modules, and TypeScript compilation remain present, even if reduced in scope.

---

### Option B — FastAPI + HTMX + Jinja2

**Pros**
- **Single language runtime.** Python end-to-end — no JavaScript build tooling, no TypeScript, no npm. The team controls the full stack in the language they know best.
- **Simpler mental model for a Python team.** Server renders HTML; HTMX handles partial updates. No component lifecycle, no virtual DOM, no bundler.
- **Smaller deployment footprint.** No frontend build step; static assets are minimal.
- **Better suited to future NHS system integration.** A traditional server-rendered app is easier to wrap in NHS authentication middleware (e.g. Entra ID, NHS Login) and easier to audit for clinical governance.
- **All bioinformatics tooling available.** Same as Option A.

**Cons**
- **Highest up-front effort.** The ClassificationPanel rewrite is the dominant risk. Live criterion toggling with immediate score feedback is difficult to replicate idiomatically in HTMX without careful endpoint design. This risks either degraded UX or a complex HTMX implementation that is harder to maintain than the React original.
- **HTMX is a less mature ecosystem for complex data UIs.** The variant table (sortable columns, client-side filters, paginated server fetch) is achievable in HTMX but requires more backend endpoints compared to the current client-driven approach.
- **Jinja2 templates are harder to test than React components.** Unit-testing template rendering requires either `pytest-flask`/`httpx` integration tests, or dedicated template testing — more setup than React Testing Library.
- **The team would lose the existing React test suite.** All 7 component test files are discarded.

---

### Option C — Django + HTMX

**Pros**
- **"Batteries included" framework.** Django provides an ORM (eliminating raw SQL), a migration framework (replacing `scripts/migrate.js`), a built-in admin interface (potentially useful for operational oversight of clinical data), session management, and a mature authentication system.
- **Django ORM reduces SQL maintenance burden.** The raw parameterised SQL in the API routes is replaced by querysets that are easier for the team to read, write, and refactor.
- **Django's security defaults are appropriate for a clinical application.** CSRF protection, SQL injection prevention, and `SECRET_KEY` management are baked in.
- **Strong NHS/healthcare precedent.** Django is widely used in NHS digital services.

**Cons**
- **Highest learning curve.** Django introduces significantly more concepts than Flask or FastAPI: ORM, migrations, settings modules, apps, middleware, class-based views. A team new to Django may spend as much time learning Django patterns as writing application code.
- **ORM migration from raw SQL is not free.** The existing SQL queries (particularly the lateral join in `variants` and the transactional classification logic) need careful mapping to Django ORM or `raw()` queries. This is extra work that does not exist in Options A or B.
- **Async support is incomplete.** Django's async support (as of Django 5.x) is usable but not as mature as FastAPI's. The ingest pipeline is inherently I/O-heavy (S3 reads, bulk DB inserts); FastAPI handles this more cleanly.
- **Same frontend risk as Option B.** The HTMX ClassificationPanel rewrite challenge is identical to Option B.

---

## 6. Recommended Path

**Option A (FastAPI + React SPA) is recommended** as the pragmatic first step for this team.

The rationale:

1. **Risk is concentrated in the right place.** The business logic and API routes — the parts where Python expertise is most valuable — are fully migrated. The React UI, which currently works correctly, is preserved.

2. **The frontend is already thin.** The React components in this codebase contain almost no Next.js-specific code. They are standard client-side components that will work unchanged in a Vite/React Router shell. The migration of the frontend is closer to a scaffolding task than a rewrite.

3. **The team's Python skills directly improve the most clinically important code.** The classification engine (ACGS SNV, SVIG-UK scoring), VCF parser, and ingest pipeline are the core of the application's clinical value. Python's bioinformatics ecosystem (`pysam`, `cyvcf2`, `jsonschema`) may genuinely improve these components beyond a like-for-like port.

4. **Option A can evolve into Option B incrementally.** Once the Python backend is in place and stable, individual React components can be replaced with HTMX partials over time — without a big-bang rewrite.

5. **Option A is compatible with NHS governance timelines.** A 4–6 week backend rewrite can be scoped as a single sprint or quarter of work. Options B and C involve a 3–4 month effort that is harder to schedule around clinical service commitments.

---

## 7. What Would Not Change in Any Option

Regardless of which migration path is chosen, the following are stable and require no rework:

- PostgreSQL database schema and SQL migrations.
- AWS infrastructure (ECS Fargate, ALB, RDS, S3, Secrets Manager, VPC). Terraform is unchanged.
- JSON classification framework configuration files (`acgs-snv-criteria.json`, `svig-criteria.json`, `canvig-gene-mtaf.json`).
- FHIR manifest schema (`manifest-schema.json`) and example manifests.
- Docker Compose local development configuration (with a different app container image).
- Domain, DNS, and TLS setup.

---

## 8. Key Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Classification engine produces different results after Python port | Low | Critical | Port unit tests from TypeScript first; generate a golden-set of classification results against known inputs before switching |
| VCF parser mishandles edge cases after rewrite | Medium | High | Retain existing test VCF files; add pysam-based golden-output tests |
| ClassificationPanel UX degrades in HTMX rewrite (Options B/C) | High | Medium | Prototype HTMX criterion toggling before committing to full rewrite |
| Team capacity underestimated (part-time development) | High | Medium | Scope Option A as the initial deliverable; treat frontend decoupling as a separate, bounded task |
| AWS SDK version differences (boto3 vs AWS SDK v3) | Low | Low | boto3 is mature and well-documented; minor API surface differences are well-understood |
| Django ORM queries differ subtly from raw SQL (Option C) | Medium | High | Keep raw SQL for complex queries (`LATERAL JOIN`, transactions); only use ORM for simple CRUD |
