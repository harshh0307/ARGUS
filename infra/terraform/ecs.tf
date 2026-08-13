resource "aws_ecs_cluster" "main" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

locals {
  image_url       = "${aws_ecr_repository.argus.repository_url}:${var.image_tag}"
  task_role_arn   = aws_iam_role.ecs_task.arn
  exec_role_arn   = aws_iam_role.ecs_execution.arn
  log_group       = aws_cloudwatch_log_group.main.name
  database_url    = "postgresql+psycopg://argus:${urlencode(coalesce(var.db_password, random_password.db.result))}@${aws_db_instance.postgres.endpoint}/argus"
  redis_url       = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
  snapshot_bucket = aws_s3_bucket.snapshots.id

  common_env = [
    { name = "DATABASE_URL", value = local.database_url },
    { name = "REDIS_URL", value = local.redis_url },
    { name = "API_HOST", value = "0.0.0.0" },
    { name = "API_PORT", value = "8000" },
    { name = "SNAPSHOT_DIR", value = "/tmp/snapshots" },
  ]

  common_secrets = [
    { name = "GITHUB_TOKEN", valueFrom = "${var.ssm_prefix}/GITHUB_TOKEN" },
    { name = "GITHUB_APP_ID", valueFrom = "${var.ssm_prefix}/GITHUB_APP_ID" },
    { name = "GITHUB_APP_PRIVATE_KEY", valueFrom = "${var.ssm_prefix}/GITHUB_APP_PRIVATE_KEY" },
    { name = "GITHUB_INSTALL_ID", valueFrom = "${var.ssm_prefix}/GITHUB_INSTALL_ID" },
    { name = "WEBHOOK_SECRET", valueFrom = "${var.ssm_prefix}/WEBHOOK_SECRET" },
    { name = "OPENAI_API_KEY", valueFrom = "${var.ssm_prefix}/OPENAI_API_KEY" },
    { name = "GEMINI_API_KEY", valueFrom = "${var.ssm_prefix}/GEMINI_API_KEY" },
    { name = "OPENROUTER_API_KEY", valueFrom = "${var.ssm_prefix}/OPENROUTER_API_KEY" },
    { name = "OPENROUTER_MODEL", valueFrom = "${var.ssm_prefix}/OPENROUTER_MODEL" },
    { name = "LLM_MODEL", valueFrom = "${var.ssm_prefix}/LLM_MODEL" },
    { name = "LLM_BASE_URL", valueFrom = "${var.ssm_prefix}/LLM_BASE_URL" },
    { name = "EMBEDDING_API_KEY", valueFrom = "${var.ssm_prefix}/EMBEDDING_API_KEY" },
    { name = "EMBEDDING_BASE_URL", valueFrom = "${var.ssm_prefix}/EMBEDDING_BASE_URL" },
    { name = "EMBEDDING_MODEL", valueFrom = "${var.ssm_prefix}/EMBEDDING_MODEL" },
    { name = "FIX_MAX_ATTEMPTS", valueFrom = "${var.ssm_prefix}/FIX_MAX_ATTEMPTS" },
  ]
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_alb" "main" {
  name            = "${local.name_prefix}-alb"
  internal        = false
  subnets         = aws_subnet.public[*].id
  security_groups = [aws_security_group.alb.id]

  tags = local.tags
}

resource "aws_alb_target_group" "api" {
  name        = "${local.name_prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  tags = local.tags
}

resource "aws_alb_listener" "http" {
  load_balancer_arn = aws_alb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.api.arn
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = local.exec_role_arn
  task_role_arn            = local.task_role_arn

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = local.image_url
      essential    = true
      entryPoint   = ["uvicorn", "app.api.main:app"]
      command      = ["--host", "0.0.0.0", "--port", "8000"]
      environment  = local.common_env
      secrets      = local.common_secrets
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = local.log_group
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = local.exec_role_arn
  task_role_arn            = local.task_role_arn

  container_definitions = jsonencode([
    {
      name        = "worker"
      image       = local.image_url
      essential   = true
      entryPoint  = ["celery", "-A", "app.workers.celery_app"]
      command     = ["worker", "--loglevel=info"]
      environment = local.common_env
      secrets     = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = local.log_group
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_task_definition" "beat" {
  family                   = "${local.name_prefix}-beat"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = local.exec_role_arn
  task_role_arn            = local.task_role_arn

  container_definitions = jsonencode([
    {
      name        = "beat"
      image       = local.image_url
      essential   = true
      entryPoint  = ["celery", "-A", "app.workers.celery_app"]
      command     = ["beat", "--loglevel=info"]
      environment = local.common_env
      secrets     = local.common_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = local.log_group
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "beat"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_alb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_alb_listener.http]

  tags = local.tags
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  tags = local.tags
}

resource "aws_ecs_service" "beat" {
  name            = "${local.name_prefix}-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = var.beat_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  tags = local.tags
}