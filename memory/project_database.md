---
name: RDS database, Secrets Manager, and migrations
description: Database connection pattern via Secrets Manager, SSL config, lib/db.ts details, and migration workflow
type: project
---

## Connection Pattern

- ECS task only receives `DB_SECRET_ARN` env var, NOT `DATABASE_URL`.
- `lib/db.ts` resolves the secret via Secrets Manager SDK at runtime and builds the connection string.
- Encode `username`, `password`, **and** `dbname` with `encodeURIComponent()` — special chars in any field break URI parsing.
- Validate all four required secret fields before building the URL for clear errors.

## SSL

- RDS uses AWS CA (self-signed from Node's perspective): set `ssl: { rejectUnauthorized: false }` in Pool config for production.
- This is intentional for RDS in a private VPC — AWS CA not in Node's trust store; bundling it adds overhead with negligible benefit in a private subnet.
- For one-off ECS Exec commands: use `NODE_TLS_REJECT_UNAUTHORIZED=0`.

## Secrets Manager VPC Endpoint

- Verify private DNS is enabled and endpoint SG allows HTTPS from ECS task SG.

## Migrations

- Runner is in `scripts/`; run via ECS Exec on the container.
- Build DATABASE_URL manually from the secret: `aws secretsmanager get-secret-value --secret-id <ARN>`.
- Use `NODE_TLS_REJECT_UNAUTHORIZED=0` for the migration run (RDS self-signed cert).
- Migration files: `migrations/` directory (001_initial, 002_classification, 003_audit).

**Why:** The Secrets Manager indirection and SSL quirks caused multiple connection failures during initial deployment.

**How to apply:** Any DB-related changes must account for the runtime secret resolution pattern in lib/db.ts. Never hardcode DATABASE_URL.
