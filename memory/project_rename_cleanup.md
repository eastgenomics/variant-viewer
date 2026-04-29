---
name: Rename cleanup — resolved
description: Orphaned SG from genomics-variant-viewer to variant-viewer rename deleted. Subnet group kept as Terraform-managed under old name.
type: project
originSessionId: 4039298e-55e5-47b1-999d-6c05fb200903
---
**Resolved 2026-04-09.**

- **RDS security group** `sg-0503ab6b49b44a31f` (`genomics-variant-viewer-rds-sg`) — deleted.
- **RDS subnet group** `genomics-variant-viewer-rds-subnet-group` — NOT deleted. Terraform manages it under this name (`aws_db_subnet_group.postgres`). RDS subnet group names are immutable in AWS so it keeps the old name. Terraform state is fully in sync (`No changes`).

`multi_az = false` in terraform.tfvars (RDS is single-AZ, left as-is to avoid disruption).
