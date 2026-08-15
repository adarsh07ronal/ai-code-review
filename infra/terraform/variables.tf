variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "ai-code-review"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread public/private subnets across"
  type        = number
  default     = 2
}

# ── Container images ──────────────────────────────────────────────────────

variable "backend_image_tag" {
  description = "Tag of the backend image in ECR to deploy (set by CI on each release)"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Tag of the frontend image in ECR to deploy (set by CI on each release)"
  type        = string
  default     = "latest"
}

# ── ECS sizing ────────────────────────────────────────────────────────────

variable "backend_cpu" {
  type    = number
  default = 512
}

variable "backend_memory" {
  type    = number
  default = 1024
}

variable "frontend_cpu" {
  type    = number
  default = 256
}

variable "frontend_memory" {
  type    = number
  default = 512
}

variable "backend_min_capacity" {
  type    = number
  default = 2
}

variable "backend_max_capacity" {
  type    = number
  default = 10
}

variable "frontend_min_capacity" {
  type    = number
  default = 2
}

variable "frontend_max_capacity" {
  type    = number
  default = 6
}

# ── Database / cache ──────────────────────────────────────────────────────

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_name" {
  type    = string
  default = "codereview"
}

variable "db_username" {
  type    = string
  default = "codereview"
}

variable "db_password" {
  description = "RDS master password. Pass via TF_VAR_db_password or a secrets manager data source — never commit a real value."
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

# ── App secrets (pulled into ECS task defs as environment/secrets) ────────

variable "app_secret_key" {
  description = "JWT signing key for the backend. Pass via TF_VAR_app_secret_key."
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Public domain the ALB serves (used for CORS + OAuth redirect URIs). Leave blank to use the ALB's default DNS name."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB's HTTPS listener. Leave blank to serve HTTP only (fine for a first deploy before DNS/ACM is set up)."
  type        = string
  default     = ""
}
