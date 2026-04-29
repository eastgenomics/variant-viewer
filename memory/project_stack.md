---
name: Stack and deployment overview
description: Core technology stack, domain, region, and high-level architecture for the variant viewer
type: project
---

Next.js 15 App Router + TypeScript app deployed on AWS ECS Fargate.

**App name:** `variant-viewer` (Terraform `var.app_name`)
**Stack:** ECS + ALB + RDS PostgreSQL + Lambda (VCF ingest) + S3 + ECR + Secrets Manager.
**Domain:** devv.genomics-resources.uk (subdomain delegated to a separate Hosted Zone).
**Region:** eu-west-2.
**Account:** 749929395031.

**AWS profiles:**
- `vv-admin` — AdministratorAccess, for Terraform and infra changes
- `vv-dev` — variant-viewer-developer permission set, for day-to-day deployment (ECR push, ECS deploy, Lambda update, ECS Exec, logs, S3, secrets read)

**Why:** Clinical genomics variant classification tool — needs secure, auditable infrastructure in a UK region.

**How to apply:** Use `vv-dev` for deployments, `vv-admin` only for Terraform. All AWS commands target eu-west-2.
