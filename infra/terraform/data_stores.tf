resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = local.tags
}

resource "aws_db_instance" "postgres" {
  identifier     = "${local.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = "16.3"

  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  storage_type        = "gp3"
  storage_encrypted   = true
  skip_final_snapshot = false

  db_name                 = "argus"
  username                = "argus"
  password                = coalesce(var.db_password, random_password.db.result)
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  multi_az                = false
  backup_retention_period = 7
  publicly_accessible     = false

  tags = merge(local.tags, { Name = "${local.name_prefix}-postgres" })
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]
  port                 = 6379

  tags = local.tags
}

resource "aws_s3_bucket" "snapshots" {
  bucket = var.snapshot_bucket_name != "" ? var.snapshot_bucket_name : "${local.name_prefix}-snapshots"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id

  versioning_configuration {
    status = "Enabled"
  }
}