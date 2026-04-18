---
name: Common deployment commands
description: Frequently used commands for ECR push, Terraform, ECS redeploy, ECS Exec, and migrations
type: reference
---

```bash
# ECR login
AWS_PROFILE=vv-dev aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 749929395031.dkr.ecr.eu-west-2.amazonaws.com

# Push app image
sg docker -c 'docker build -t variant-viewer . && docker tag variant-viewer:latest 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest && docker push 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest'

# Push Lambda image
./node_modules/.bin/tsc --project tsconfig.lambda.json
sg docker -c 'docker build -f lambda/Dockerfile -t variant-viewer-lambda . && docker tag variant-viewer-lambda:latest 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer-lambda:latest && docker push 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer-lambda:latest'

# Terraform (admin only)
cd terraform && AWS_PROFILE=vv-admin terraform plan -var-file=terraform.tfvars
cd terraform && AWS_PROFILE=vv-admin terraform apply -var-file=terraform.tfvars

# Force ECS redeploy
AWS_PROFILE=vv-dev aws ecs update-service --cluster variant-viewer --service variant-viewer --force-new-deployment --region eu-west-2

# ECS Exec
TASK=$(AWS_PROFILE=vv-dev aws ecs list-tasks --cluster variant-viewer --region eu-west-2 --query 'taskArns[0]' --output text)
AWS_PROFILE=vv-dev aws ecs execute-command --cluster variant-viewer --task "$TASK" --container variant-viewer --interactive --command "/bin/sh" --region eu-west-2

# Run migrations via ECS Exec (inside container)
# Get DATABASE_URL from outside first:
SECRET=$(AWS_PROFILE=vv-dev aws secretsmanager get-secret-value --secret-id variant-viewer/db-credentials --region eu-west-2 --query 'SecretString' --output text)
# Parse with python3, then inside container:
NODE_TLS_REJECT_UNAUTHORIZED=0 DATABASE_URL="postgresql://..." node scripts/migrate.js
```
