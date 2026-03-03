variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-2"
}

variable "environment" {
  description = "Deployment environment (dev | prod)"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod"
  }
}

variable "app_name" {
  description = "Application name prefix for resources"
  type        = string
  default     = "genomics-variant-viewer"
}

variable "domain_name" {
  description = "Domain name for the ALB certificate (e.g. variants.example-lab.org)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "variants"
}

variable "multi_az" {
  description = "Enable RDS Multi-AZ (set false for dev to save cost)"
  type        = bool
  default     = true
}

variable "ecs_cpu" {
  description = "ECS task CPU units"
  type        = number
  default     = 1024
}

variable "ecs_memory" {
  description = "ECS task memory (MB)"
  type        = number
  default     = 2048
}

variable "ecs_desired_count" {
  description = "Desired number of ECS task replicas"
  type        = number
  default     = 2
}

variable "lambda_memory_size" {
  description = "Lambda function memory (MB)"
  type        = number
  default     = 2048
}

variable "vcf_glacier_days" {
  description = "Days before VCF objects transition to Glacier"
  type        = number
  default     = 365
}

variable "dlq_alarm_email" {
  description = "Email for DLQ CloudWatch alarm notifications"
  type        = string
  default     = ""
}

variable "ecr_image_tag" {
  description = "Docker image tag to deploy from ECR"
  type        = string
  default     = "latest"
}
