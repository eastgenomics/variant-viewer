# Pre-work: add dev.vv.genomics-resources.uk

> **Status: complete** — applied 2026-05-05. `https://dev.vv.genomics-resources.uk` is live.

## Context

The discovery prototype is deployed and accessible at `devv.genomics-resources.uk`.
It will remain live as a reference throughout the refactor.

The refactored app (FastAPI + React SPA, PRs 2–12) needs a development URL.
Rather than provisioning a second ECS stack, the refactored app will deploy to
the **existing ECS service** — it replaces the Next.js container image when PR 12
lands. The new subdomain is purely a DNS and certificate change.

```
During refactor
───────────────
devv.genomics-resources.uk   →  ALB  →  ECS  (Next.js prototype — reference)
dev.vv.genomics-resources.uk →  ALB  →  ECS  (Next.js prototype — same service)

After PR 12 deploys
────────────────────
devv.genomics-resources.uk   →  ALB  →  ECS  (FastAPI + React SPA)
dev.vv.genomics-resources.uk →  ALB  →  ECS  (FastAPI + React SPA)
```

`devv.genomics-resources.uk` is kept as-is — no DNS changes, no risk of outage.
The prototype is accessible at both names during the refactor and is superseded
at both names when PR 12 deploys. The prototype code and git history are
preserved at tag `v0.1-discovery-nextjs`.

---

## What needs to change

No new ECS service, target group, task definition, listener rules, RDS, ECR, or
VPC resources are required.

| # | Resource | Type | Notes |
|---|---|---|---|
| 1 | Route 53 hosted zone `vv.genomics-resources.uk` | Terraform | New zone in account 749929395031 |
| 2 | NS delegation `vv.genomics-resources.uk` | Manual | Copy NS records into the `genomics-resources.uk` zone in the parent account |
| 3 | ACM certificate `*.vv.genomics-resources.uk` | Terraform | Wildcard covers `dev.`, `prod.`, and any future environments |
| 4 | Route 53 A alias `dev.vv.genomics-resources.uk` → ALB | Terraform | Same ALB, no new target group or listener rules needed |
| 5 | Attach wildcard cert to existing ALB HTTPS listener | Terraform | ALB supports multiple certificates; existing cert and listener unchanged |

---

## Steps

### Step 1 — ~~Terraform: new zone, cert, DNS records, cert attachment~~ ✅

Add to `terraform/dns.tf` and `terraform/alb.tf`:

- `aws_route53_zone.vv` — hosted zone for `vv.genomics-resources.uk`
- `aws_acm_certificate.vv` — wildcard cert `*.vv.genomics-resources.uk`
- `aws_route53_record.cert_validation_vv` — DNS validation record in the new zone
- `aws_acm_certificate_validation.vv`
- `aws_route53_record.dev_vv` — A alias `dev.vv.genomics-resources.uk` → existing ALB
- `aws_lb_listener_certificate.vv` — attach wildcard cert to existing HTTPS listener

Add to `terraform/outputs.tf`:

- `vv_subdomain_name_servers` — NS records to copy into the parent account

Run:

```bash
cd terraform
AWS_PROFILE=vv-admin terraform plan -var-file=terraform.tfvars
AWS_PROFILE=vv-admin terraform apply -var-file=terraform.tfvars
```

### Step 2 — ~~Manual: NS delegation in parent account~~ ✅

After `terraform apply`, copy the four NS record values from the
`vv_subdomain_name_servers` output into the `genomics-resources.uk` hosted zone
in the parent AWS account.

This is the same process used when `devv.genomics-resources.uk` was first set up.

### Step 3 — ~~Wait for ACM validation~~ ✅

Validated in ~4 minutes after NS delegation.

### Step 4 — ~~Smoke test~~ ✅

`https://dev.vv.genomics-resources.uk` returned HTTP 200. `https://devv.genomics-resources.uk` unchanged.

---

## Gotchas

- **`EvaluateTargetHealth`**: the new Route 53 alias record should have
  `evaluate_target_health = true` (consistent with the existing `devv.` record).
  If the ALB is briefly unhealthy, Route 53 returns NXDOMAIN. The SOA minimum
  TTL on the new zone should be set to 60s (matching `devv.`) to avoid
  long-lived NXDOMAIN caching.
- **Existing cert and listener are not touched**: the `aws_lb_listener_certificate`
  resource adds a secondary certificate; it does not replace the primary cert on
  the listener. The existing `devv.` traffic is unaffected.
- **ACM cert must be in the same region as the ALB** (`eu-west-2`). This is
  already the case — no `us-east-1` provider needed (ALB, not CloudFront).

---

## After PR 12

When the refactored app is ready to deploy:

1. Push the FastAPI backend image to ECR (tagged `latest`).
2. Update the ECS task definition environment variables as needed
   (`APP_ENV=production`, remove `NODE_ENV`, etc.).
3. Force a new ECS deployment — both `devv.` and `dev.vv.` immediately serve
   the new app.
4. Decide whether to retire `devv.genomics-resources.uk` (remove Route 53 record
   and hosted zone) or keep it as a permanent alias.

The prototype is not accessible on the web after this point. It remains
runnable locally from the `discovery/nextjs` branch or the `v0.1-discovery-nextjs`
tag.
