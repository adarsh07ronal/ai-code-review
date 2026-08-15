locals {
  database_url = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:5432/${var.db_name}"
  redis_url    = "redis://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
}

# Secret values below are placeholders — real GitHub/OpenAI/Stripe keys are
# set post-deploy with `aws secretsmanager put-secret-value`, never checked
# into tfvars. lifecycle.ignore_changes keeps subsequent `apply` runs from
# clobbering whatever was set out-of-band.
resource "aws_secretsmanager_secret" "backend" {
  name = "${var.project_name}/backend"
}

resource "aws_secretsmanager_secret_version" "backend" {
  secret_id = aws_secretsmanager_secret.backend.id
  secret_string = jsonencode({
    DATABASE_URL          = local.database_url
    REDIS_URL             = local.redis_url
    SECRET_KEY            = var.app_secret_key
    GITHUB_CLIENT_SECRET  = ""
    GITHUB_WEBHOOK_SECRET = ""
    OPENAI_API_KEY        = ""
    STRIPE_SECRET_KEY     = ""
    STRIPE_WEBHOOK_SECRET = ""
    STRIPE_PRICE_ID_PRO   = ""
    STRIPE_PRICE_ID_TEAM  = ""
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
