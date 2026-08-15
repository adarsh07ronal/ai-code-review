terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — created once outside this config (S3 bucket + DynamoDB
  # lock table), then wired in here. Left commented so `terraform init`
  # works locally without pre-existing infra; uncomment once the backend
  # resources exist.
  # backend "s3" {
  #   bucket         = "ai-code-review-tfstate"
  #   key            = "ai-code-review/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "ai-code-review-tfstate-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}
