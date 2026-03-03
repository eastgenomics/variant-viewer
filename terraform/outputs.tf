output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.app.dns_name
}

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "s3_bucket_name" {
  description = "VCF upload S3 bucket name"
  value       = aws_s3_bucket.vcf.id
}

output "ecr_repository_url" {
  description = "ECR repository URL for the Next.js image"
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.app.name
}

output "lambda_function_name" {
  description = "Lambda ingest function name"
  value       = aws_lambda_function.ingest.function_name
}
