---
name: DNS delegation and Terraform gotchas
description: Cross-account DNS setup, Terraform backend config, and provider-specific pitfalls discovered during deployment
type: project
originSessionId: 8256cc3d-ebf1-485b-b123-491e9f90eb74
---
## DNS

- Parent zone `genomics-resources.uk` is in a DIFFERENT AWS account.
- Solution: create `aws_route53_zone.app` for the subdomain in this account, then manually add NS delegation records in the other account.
- Output `subdomain_name_servers` gives the NS values to copy across.
- ACM cert validation can take 20-30 min after NS delegation propagates.

### Negative DNS cache (NXDOMAIN caching)

- SOA minimum TTL controls how long resolvers cache NXDOMAIN responses.
- Default was 86400s (24h) — if the domain is briefly unreachable (e.g. ALB destroyed before new one is ready), resolvers cache NXDOMAIN for 24h.
- **Fix applied 2026-04-09:** SOA minimum TTL lowered to 60s so resolvers retry within a minute.
- Root cause: `EvaluateTargetHealth = true` on the Route 53 alias causes Route 53 to return NXDOMAIN when the ALB target is invalid/unhealthy — even briefly during a rename.
- **Before any infra change that touches the ALB or Route 53 record:** consider setting `EvaluateTargetHealth = false` temporarily, or ensure the new ALB is ready before the old one is destroyed.

## Terraform

- Backend: S3 bucket `genomics-variant-viewer-tfstate` in account **749929395031**, DynamoDB table `genomics-variant-viewer-tflock`. Use `AWS_PROFILE=vv-admin`.
- S3 lifecycle rules require an explicit `filter {}` block (AWS provider v5.100+).
- EC2 security group descriptions must be ASCII-only (no em dashes).
- Lambda: `AWS_REGION` is a reserved env var — do NOT set it in Lambda environments.
- ACM cert validation can take 20-30 min after NS delegation propagates.
- Lambda ECR image must exist before `terraform apply` can create the Lambda function.
- RDS subnet groups are immutable — cannot rename within the same VPC. Current subnet group kept as `genomics-variant-viewer-rds-subnet-group` (hardcoded in `rds.tf`).
- Renaming `app_name` causes mass destroy/recreate — ALB, ECS, ECR, SGs, SQS, Secrets Manager all replaced. Plan carefully.

**Why:** Hard-won lessons from first deployment and the variant-viewer rename. Each gotcha caused a failed apply, broken service, or DNS outage.

**How to apply:** Check these before any Terraform changes. Cross-account DNS and the negative cache issue are the most common sources of confusion.
