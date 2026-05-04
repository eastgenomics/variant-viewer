# Deployment Guide

## Contents

- [Local development](#local-development)
- [AWS deployment](#aws-deployment)

---

## Local development

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 22+ | Install via [nvm](https://github.com/nvm-sh/nvm) |
| PostgreSQL | 14+ | Must be running locally |
| Git | any | |

#### Install nvm and Node 22

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc   # or ~/.zshrc
nvm install 22
nvm use 22         # or: cd into the repo — .nvmrc picks it up automatically
```

### 1. Clone and install dependencies

```bash
git clone <repo-url> variant-viewer
cd variant-viewer
npm install
```

### 2. Set up the database

Create a PostgreSQL user and database:

```bash
# Run as a superuser (peer auth — no password needed if your OS user has pg superuser rights)
psql -c "CREATE USER variants_admin WITH PASSWORD 'variants_dev_password';"
psql -c "CREATE DATABASE variants OWNER variants_admin;"
psql -c "GRANT ALL PRIVILEGES ON DATABASE variants TO variants_admin;"
psql -d variants -c "GRANT ALL ON SCHEMA public TO variants_admin;"
```

Run migrations:

```bash
DATABASE_URL=postgresql://variants_admin:variants_dev_password@localhost:5432/variants \
  node scripts/migrate.js
```

### 3. Configure environment

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
DATABASE_URL=postgresql://variants_admin:variants_dev_password@localhost:5432/variants
AWS_REGION=eu-west-2
VCF_BUCKET_NAME=local-dev-placeholder
```

`VCF_BUCKET_NAME` is only needed for the production S3 upload path. Local dev bypasses S3 entirely.

### 4. Start the dev server

```bash
npm run dev
```

App is available at **http://localhost:3000**.

### Uploading VCFs locally

The upload form at `/upload` detects `NODE_ENV=development` and sends the file directly to `/api/ingest-upload` instead of going through S3. Fill in the patient fields, select a VEP-annotated VCF (`.vcf` or `.vcf.gz`), and submit. Variants appear immediately.

### Running migrations again after schema changes

```bash
node scripts/migrate.js
```

The runner skips already-applied migrations and only runs new ones.

---

## AWS deployment

### Architecture overview

```
Internet → ALB (HTTPS) → ECS Fargate (Next.js) → RDS PostgreSQL
                                                 ↗
S3 (VCF uploads) → Lambda (ingest) ────────────┘
```

All infrastructure is managed by Terraform in the `/terraform` directory.

### AWS accounts and profiles

| Profile | Account | Role | Used for |
|---------|---------|------|----------|
| `vv-admin` | 749929395031 | AdministratorAccess | Terraform only |
| `vv-dev` | 749929395031 | variant-viewer-developer | Day-to-day deployments (ECR push, ECS deploy, Lambda update, ECS Exec, logs) |

The Terraform state bucket (`genomics-variant-viewer-tfstate`) and all infrastructure live in account **749929395031**. Note: the state bucket retains its original name — renaming it would require migrating Terraform state.

### Prerequisites

| Tool | Version |
|------|---------|
| Terraform | 1.7+ |
| AWS CLI | 2.x, configured with `vv-admin` profile |
| Docker | 24+ |
| Node.js | 22+ |
| session-manager-plugin | latest | Required for ECS Exec — if not available via package manager, extract to `~/bin`: `curl -sLo /tmp/sm.deb https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb && dpkg -x /tmp/sm.deb /tmp/smp && cp /tmp/smp/usr/local/sessionmanagerplugin/bin/session-manager-plugin ~/bin/` |

### First-time setup

#### 1. Create Terraform state backend

The backend uses S3 + DynamoDB for state locking. Create these once before running `terraform init`:

```bash
aws s3 mb s3://variant-viewer-tfstate --region eu-west-2
aws s3api put-bucket-versioning \
  --bucket variant-viewer-tfstate \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket variant-viewer-tfstate \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws dynamodb create-table \
  --table-name variant-viewer-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-2
```

#### 2. Initialise Terraform

```bash
cd terraform
AWS_PROFILE=vv-admin terraform init
```

#### 3. Create a `terraform.tfvars` file

```hcl
# terraform/terraform.tfvars
aws_region        = "eu-west-2"
environment       = "prod"
domain_name       = "variants.your-domain.org"   # must be in Route 53 or have DNS you control
db_instance_class = "db.t4g.medium"
multi_az          = true
dlq_alarm_email   = "oncall@your-org.org"        # receives alerts on ingest failures
```

For a dev/cost-saving deployment:

```hcl
environment       = "dev"
db_instance_class = "db.t4g.micro"
multi_az          = false
```

#### 4. Plan and apply infrastructure

```bash
AWS_PROFILE=vv-admin terraform plan -var-file=terraform.tfvars
AWS_PROFILE=vv-admin terraform apply -var-file=terraform.tfvars
```

This creates all infrastructure but does not deploy any application code yet. Note the outputs:

```bash
terraform output           # ALB DNS, RDS endpoint, ECR URLs, S3 bucket name
```

#### 5. Configure DNS

Point your domain at the ALB. In Route 53:

```bash
# Get the ALB DNS name
ALB_DNS=$(terraform output -raw alb_dns_name)

# Create an A record alias in Route 53 (or a CNAME at your DNS provider)
# pointing variants.your-domain.org → $ALB_DNS
```

ACM will validate the certificate automatically if the domain is in Route 53. For external DNS, add the CNAME validation record that ACM provides.

#### 6. Build and push the Next.js Docker image

```bash
# Authenticate Docker to ECR
AWS_PROFILE=vv-dev aws ecr get-login-password --region eu-west-2 \
  | docker login --username AWS --password-stdin 749929395031.dkr.ecr.eu-west-2.amazonaws.com

# Build and push
docker build -t variant-viewer .
docker tag variant-viewer:latest 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest
docker push 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest
```

Force a new ECS deployment to pick it up immediately:

```bash
AWS_PROFILE=vv-dev aws ecs update-service \
  --cluster variant-viewer \
  --service variant-viewer \
  --force-new-deployment \
  --region eu-west-2
```

#### 7. Build and push the Lambda Docker image

```bash
# Compile TypeScript for Lambda
./node_modules/.bin/tsc --project tsconfig.lambda.json

# Build and push Lambda image
docker build -f lambda/Dockerfile -t variant-viewer-lambda .
docker tag variant-viewer-lambda:latest 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer-lambda:latest
docker push 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer-lambda:latest

# Update Lambda to use the new image
AWS_PROFILE=vv-dev aws lambda update-function-code \
  --function-name variant-viewer-ingest \
  --image-uri 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer-lambda:latest \
  --region eu-west-2
```

#### 8. Run database migrations

The RDS instance is in a private subnet. Run migrations via ECS Exec:

```bash
# Get a running task
TASK_ARN=$(AWS_PROFILE=vv-dev aws ecs list-tasks \
  --cluster variant-viewer \
  --query 'taskArns[0]' --output text \
  --region eu-west-2)

# Open a shell
AWS_PROFILE=vv-dev aws ecs execute-command \
  --cluster variant-viewer \
  --task $TASK_ARN \
  --container variant-viewer \
  --interactive \
  --command "/bin/sh" \
  --region eu-west-2
```

Inside the container, build `DATABASE_URL` from the secret and run:

```bash
# Get credentials (run outside the container, then paste DATABASE_URL in)
SECRET=$(AWS_PROFILE=vv-dev aws secretsmanager get-secret-value \
  --secret-id variant-viewer/db-credentials \
  --region eu-west-2 --query SecretString --output text)
# Parse with: python3 -c "import sys,json; s=json.loads('$SECRET'); print(f\"postgresql://{s['username']}:{s['password']}@{s['host']}:5432/{s['dbname']}\")"

# Then inside the container:
NODE_TLS_REJECT_UNAUTHORIZED=0 DATABASE_URL="postgresql://..." node scripts/migrate.js
```

The `DB_SECRET_ARN` env var is set on the ECS task — the app resolves credentials from Secrets Manager at runtime.

---

### Subsequent deployments

After the first deploy, updating the app requires no Terraform:

```bash
# 1. ECR login
AWS_PROFILE=vv-dev aws ecr get-login-password --region eu-west-2 \
  | docker login --username AWS --password-stdin 749929395031.dkr.ecr.eu-west-2.amazonaws.com

# 2. Build and push
docker build -t variant-viewer .
docker tag variant-viewer:latest 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest
docker push 749929395031.dkr.ecr.eu-west-2.amazonaws.com/variant-viewer:latest

# 3. Redeploy
AWS_PROFILE=vv-dev aws ecs update-service \
  --cluster variant-viewer \
  --service variant-viewer \
  --force-new-deployment \
  --region eu-west-2
```

If there are new migrations, run them via ECS Exec after deploying.

### DNS gotcha — negative cache TTL

The Route 53 alias record for `devv.genomics-resources.uk` uses `EvaluateTargetHealth = true`. If the ALB is briefly unreachable (e.g. during a rename or replace), Route 53 returns NXDOMAIN and resolvers cache it.

**Current mitigation:** SOA minimum TTL is set to 60 seconds so resolvers retry within a minute.

**Before any Terraform change that destroys/replaces the ALB:**
1. Temporarily set `EvaluateTargetHealth = false` on the Route 53 alias record, or
2. Ensure the new ALB is ready before the old one is destroyed (blue/green approach)

---

### Environment variables reference

| Variable | Where set | Description |
|----------|-----------|-------------|
| `DATABASE_URL` | `.env.local` (dev) | PostgreSQL connection string (dev only) |
| `DB_SECRET_ARN` | ECS task definition / Lambda env | ARN of Secrets Manager secret containing DB credentials |
| `VCF_BUCKET_NAME` | ECS task definition / Lambda env | S3 bucket name for VCF files |
| `AWS_REGION` | ECS task definition / Lambda env | AWS region |
| `NODE_ENV` | Set by Next.js build | `production` in Docker image; `development` in dev server |

---

### Cost notes (eu-west-2, approximate)

| Resource | Spec | Est. monthly |
|----------|------|-------------|
| RDS `db.t4g.medium` Multi-AZ | 100 GB gp3 | ~£90 |
| ECS Fargate | 2× 1vCPU / 2 GB | ~£40 |
| ALB | Low traffic | ~£20 |
| NAT Gateway | Low traffic | ~£35 |
| Lambda | Event-driven, minimal | <£1 |
| S3 + KMS | Low volume | <£5 |
| **Total (prod)** | | **~£190/month** |

For a dev environment with `db.t4g.micro`, single-AZ, and 1 ECS task, expect roughly **£60–80/month**. Costs drop significantly if the dev environment is stopped outside working hours (RDS can be stopped for up to 7 days at a time via the console or CLI).
