resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "redis" {
  name        = "${var.project_name}-redis"
  description = "Allow Redis from the backend ECS service only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from backend tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.backend_service.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-redis-sg" }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project_name}-redis"
  description          = "Redis cache + WebSocket pub/sub backbone for ${var.project_name}"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.redis_node_type

  num_cache_clusters         = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Transit encryption is left off because app/db/redis.py connects with the
  # plain redis:// scheme today. Enabling it means switching the app to
  # rediss:// and an auth token — worth doing before real production traffic.
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false

  tags = { Name = "${var.project_name}-redis" }
}
