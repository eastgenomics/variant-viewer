resource "aws_s3_bucket" "vcf" {
  bucket = "${var.app_name}-vcf-${data.aws_caller_identity.current.account_id}"

  tags = { Name = "${var.app_name}-vcf" }
}

data "aws_caller_identity" "current" {}

# Block all public access
resource "aws_s3_bucket_public_access_block" "vcf" {
  bucket = aws_s3_bucket.vcf.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-KMS encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "vcf" {
  bucket = aws_s3_bucket.vcf.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

# Versioning (recovery + NHS data retention audit)
resource "aws_s3_bucket_versioning" "vcf" {
  bucket = aws_s3_bucket.vcf.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Lifecycle: transition to Glacier after var.vcf_glacier_days
resource "aws_s3_bucket_lifecycle_configuration" "vcf" {
  bucket = aws_s3_bucket.vcf.id
  rule {
    id     = "archive-vcf"
    status = "Enabled"
    transition {
      days          = var.vcf_glacier_days
      storage_class = "GLACIER"
    }
    noncurrent_version_transition {
      noncurrent_days = var.vcf_glacier_days
      storage_class   = "GLACIER"
    }
  }
}

# S3 event notification → Lambda on *.vcf.gz and *.vcf object creation
resource "aws_s3_bucket_notification" "vcf_ingest" {
  bucket = aws_s3_bucket.vcf.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".vcf.gz"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".vcf"
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}

resource "aws_lambda_permission" "s3_invoke" {
  statement_id  = "AllowS3InvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.vcf.arn
}
