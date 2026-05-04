# Memory Index

- [User profile](user_profile.md) — jwahn, AWS SSO with bedrock + admin roles, multi-PC workflow
- [Stack overview](project_stack.md) — Next.js 15 + ECS Fargate + RDS + Lambda, eu-west-2, devv.genomics-resources.uk
- [DNS & Terraform](project_dns_terraform.md) — Cross-account DNS delegation, Terraform backend, provider gotchas
- [ECS deployment](project_ecs_deployment.md) — Health checks, HOSTNAME binding, Docker builds, ECS Exec, Next.js force-dynamic
- [Database](project_database.md) — RDS via Secrets Manager, SSL config, lib/db.ts, migration workflow
- [Lambda & S3 ingest](project_lambda_s3.md) — VCF ingest pipeline, flat CSQ_* support, manifest naming, bulk upload script
- [Case identifier rework](project_case_identifiers.md) — MRN primary, Specimen rename, no NHS/name, YOB — merged to main (#10)
- [Terraform backend — resolved](project_terraform_backend_issue.md) — Infra is in account 749929395031, use AWS_PROFILE=vv-admin
- [No AI attribution](feedback_no_ai_attribution.md) — Never add "Generated with Claude Code" or similar to any output
- [Rename cleanup](project_rename_cleanup.md) — Orphaned SG deleted; subnet group kept under old name (Terraform-managed)
- [Credit 2026-04-10](credit_2026-04-10.md) — Contribution matrix for Terraform fix, rename, VCF parser, deployment session
- [Python migration assessment](project_python_migration_assessment.md) — Feasibility/effort assessment for converting to FastAPI; Option A (FastAPI + React SPA) recommended; published to Confluence
- [Confluence format preference](feedback_confluence_format.md) — Use markdown format for Confluence pages; no page properties macros or ADF
- [Credit 2026-04-25](credit_2026-04-25.md) — Contribution matrix for Python migration assessment session
- [ECS debugging](project_debug_techniques.md) — DB queries via ECS Exec, connectivity checks, silent homepage empty state
- [Common commands](reference_commands.md) — ECR push, Terraform, ECS redeploy, ECS Exec, migrations, session-manager-plugin install, local seed workflow
- [GMS concordance](project_gms_concordance.md) — gms_concordance INTEGER[] column, GmsConcordance SVG component, migration 004, seed rules (prototype branch)
