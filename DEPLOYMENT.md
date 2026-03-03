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
git clone <repo-url> genomics-variant-viewer
cd genomics-variant-viewer
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

### Prerequisites

| Tool | Version |
|------|---------|
| Terraform | 1.7+ |
| AWS CLI | 2.x, configured with appropriate credentials |
| Docker | 24+ |
| Node.js | 22+ |

The deploying IAM identity needs permissions to create VPC, RDS, ECS, Lambda, S3, Secrets Manager, KMS, ALB, ECR, IAM, SQS, SNS, and CloudWatch resources.

### First-time setup

#### 1. Create Terraform state backend

The backend uses S3 + DynamoDB for state locking. Create these once before running `terraform init`:

```bash
aws s3 mb s3://genomics-variant-viewer-tfstate --region eu-west-2
aws s3api put-bucket-versioning \
  --bucket genomics-variant-viewer-tfstate \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket genomics-variant-viewer-tfstate \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws dynamodb create-table \
  --table-name genomics-variant-viewer-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-2
```

#### 2. Initialise Terraform

```bash
cd terraform
terraform init
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
terraform plan -out=tfplan
terraform apply tfplan
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
# Get ECR details from Terraform output
ECR_URL=$(cd terraform && terraform output -raw ecr_repository_url)
AWS_REGION=eu-west-2

# Authenticate Docker to ECR
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR_URL

# Build and push
docker build -t $ECR_URL:latest .
docker push $ECR_URL:latest
```

The ECS service will pull this image. Force a new deployment to pick it up immediately:

```bash
CLUSTER=$(cd terraform && terraform output -raw ecs_cluster_name)
aws ecs update-service \
  --cluster $CLUSTER \
  --service genomics-variant-viewer \
  --force-new-deployment \
  --region $AWS_REGION
```

#### 7. Build and push the Lambda Docker image

```bash
LAMBDA_ECR_URL=$(cd terraform && terraform output -raw ecr_repository_url | sed 's/genomics-variant-viewer$/genomics-variant-viewer-lambda/')

# Compile TypeScript for Lambda
npx tsc --project tsconfig.lambda.json

# Build and push Lambda image
docker build -f lambda/Dockerfile -t $LAMBDA_ECR_URL:latest .
docker push $LAMBDA_ECR_URL:latest

# Update Lambda to use the new image
LAMBDA_NAME=$(cd terraform && terraform output -raw lambda_function_name)
aws lambda update-function-code \
  --function-name $LAMBDA_NAME \
  --image-uri $LAMBDA_ECR_URL:latest \
  --region $AWS_REGION
```

#### 8. Run database migrations

The RDS instance is in a private subnet with no public access. Run migrations through a bastion or by using ECS Exec on a running task:

```bash
# Option A: ECS Exec (no bastion needed — requires ECS Exec enabled on the task definition)
TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name genomics-variant-viewer \
  --query 'taskArns[0]' --output text \
  --region $AWS_REGION)

aws ecs execute-command \
  --cluster $CLUSTER \
  --task $TASK_ARN \
  --container genomics-variant-viewer \
  --command "node scripts/migrate.js" \
  --interactive \
  --region $AWS_REGION

# Option B: Run as a one-off ECS task with the same task definition
# (useful for CI/CD pipelines)
```

The `DATABASE_URL` is resolved from Secrets Manager at runtime — the application reads `DB_SECRET_ARN` from its environment and fetches credentials on startup.

---

### Subsequent deployments

After the first deploy, updating the app is:

```bash
# Build and push new image
docker build -t $ECR_URL:$GIT_SHA .
docker push $ECR_URL:$GIT_SHA

# Update the task definition image tag and force redeploy
# (or update ecr_image_tag in tfvars and run terraform apply)
aws ecs update-service \
  --cluster $CLUSTER \
  --service genomics-variant-viewer \
  --force-new-deployment \
  --region $AWS_REGION
```

If there are new migrations, run them via ECS Exec before or immediately after deploying the new image.

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
