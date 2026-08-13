output "alb_url" {
  description = "Public URL of the Argus API (HTTP)"
  value       = "http://${aws_alb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repo to push the image to"
  value       = aws_ecr_repository.argus.repository_url
}

output "database_endpoint" {
  description = "RDS Postgres endpoint"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  sensitive   = true
}

output "snapshot_bucket" {
  description = "S3 bucket for spec snapshots"
  value       = aws_s3_bucket.snapshots.id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ssm_prefix" {
  description = "Prefix where Argus secrets live (put yours here)"
  value       = var.ssm_prefix
}
