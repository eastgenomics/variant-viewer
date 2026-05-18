# variant-viewer

Genomic variant review and classification web app.

## Deployed environments

| URL | Description |
|---|---|
| https://dev.vv.genomics-resources.uk | Active development — currently serving the Next.js prototype; will serve the refactored FastAPI + React SPA after PR 12 |
| https://devv.genomics-resources.uk | Legacy alias — same service as above; kept for continuity |

## Architecture

**Option A: FastAPI backend + React SPA frontend** (refactor in progress)

```
backend/       Python/FastAPI — API routes, business logic, Lambda handler
frontend/      React SPA (Vite + React Router) — UI components
migrations/    PostgreSQL schema migrations
terraform/     AWS infrastructure (ECS Fargate, RDS, S3, Lambda)
specification/ Design and build specs for each PR group
```

## Refactor status

| PR | Description | Status |
|---|---|---|
| 1 | Scaffold — wipe + new structure | Merged |
| 2 | Database layer (db.py, models.py) | Merged |
| 3 | VCF parser + FHIR manifest | Merged |
| 4 | Classification engine + pre-compute criteria | Merged |
| 5 | Lambda ingest pipeline + cyvcf2 migration | Merged |
| 6 | Auth middleware + read-only API routes | Merged |
| 7 | Write API routes (classification, workflow, upload) | Pending |
| 8–11 | React SPA frontend | Pending |
| 12 | Infrastructure (Dockerfile, ECS, Lambda runtime) | Pending |

Spec documents for each phase: `specification/` (PRs 2–5) and `specification/api/` (PRs 6–7).

## Discovery branches

| Branch | Description |
|---|---|
| `discovery/nextjs` | Original Next.js 15 + TypeScript prototype — deployed reference during refactor |
| `discovery/gms-concordance` | GMS concordance prototype |

Original release tagged at `v0.1-discovery-nextjs`.

## Development

```bash
docker compose up
```

## Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 3000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```
