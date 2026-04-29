---
name: User profile
description: Developer building a clinical genomics variant viewer, uses AWS SSO with multiple roles across org accounts
type: user
---

- Username: jwahn (GitHub: woook)
- AWS org with multiple accounts:
  - **749929395031** — genomics variant viewer infrastructure (profile: `vv-admin`, AdministratorAccess)
  - **471112938470** — separate account, has `bedrock-claude-code-access` SSO role (profile: `claude-code`)
- Uses AWS IAM Identity Center (SSO) across the org
- Works across multiple PCs (requested branch+push so work could continue elsewhere)
