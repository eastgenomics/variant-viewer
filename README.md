# variant-viewer

Genomic variant review and classification web app.

## Architecture

**Option A: FastAPI backend + React SPA frontend**

```
backend/    Python/FastAPI — API routes, business logic, Lambda handler
frontend/   React SPA (Vite + React Router) — UI components
migrations/ PostgreSQL schema migrations
terraform/  AWS infrastructure (ECS Fargate, RDS, S3, Lambda)
```

## Discovery branches

| Branch | Description |
|---|---|
| `discovery/nextjs` | Original Next.js 15 + TypeScript implementation |
| `discovery/gms-concordance` | GMS concordance prototype |

Original release tagged at `v0.1-discovery-nextjs`.

## Development

```bash
docker-compose up
```

## Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```
