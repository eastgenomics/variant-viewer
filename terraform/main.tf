terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    bucket         = "genomics-variant-viewer-tfstate"
    key            = "terraform.tfstate"
    region         = "eu-west-2"
    dynamodb_table = "genomics-variant-viewer-tflock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "variant-viewer"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ACM certificate must be in us-east-1 for CloudFront,
# but we're using ALB so same region is fine.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
