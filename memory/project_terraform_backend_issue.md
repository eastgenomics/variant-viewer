---
name: Terraform backend — resolved
description: Tfstate bucket is in account 749929395031, not 471112938470. Use AWS_PROFILE=vv-admin for all Terraform commands.
type: project
---

**Resolved 2026-04-08.** The S3 backend 403 was caused by using the wrong AWS account.

- Tfstate bucket `genomics-variant-viewer-tfstate` is in account **749929395031**
- All infrastructure should be deployed to 749929395031
- Account 471112938470 is a separate account in the org (used for other purposes)
- AWS CLI profile for this account: `vv-admin` (AdministratorAccess via SSO)

**How to apply:** Always use `AWS_PROFILE=vv-admin` for Terraform and infrastructure commands in this project.
