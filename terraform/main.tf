terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ==============================================================================
# 1. AMAZON ECR REPOSITORY
# ==============================================================================
resource "aws_ecr_repository" "image_generator_repo" {
  name                 = "${var.project_name}-repo"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Environment = "Production"
    Project     = var.project_name
  }
}

# ==============================================================================
# 2. ECS CLUSTER (FARGATE)
# ==============================================================================
resource "aws_ecs_cluster" "image_generator_cluster" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ==============================================================================
# 3. IAM ROLES FOR ECS
# ==============================================================================
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# ==============================================================================
# 4. CLOUDWATCH LOG GROUP
# ==============================================================================
resource "aws_cloudwatch_log_group" "fargate_logs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 14
}

# ==============================================================================
# 5. SECURITY GROUP FOR FARGATE
# ==============================================================================
resource "aws_security_group" "fargate_sg" {
  name        = "${var.project_name}-fargate-sg"
  description = "Security group for Fargate image generator tasks"
  vpc_id      = data.aws_vpc.default.id

  # Outbound internet access (required for API calls and image downloads)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-fargate-sg"
  }
}

# ==============================================================================
# 6. ECS TASK DEFINITION
# ==============================================================================
resource "aws_ecs_task_definition" "image_generator_task" {
  family                   = "${var.project_name}-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fargate_cpu
  memory                   = var.fargate_memory

  container_definitions = jsonencode([
    {
      name  = "image-generator"
      image = "${aws_ecr_repository.image_generator_repo.repository_url}:latest"
      
      command = ["python3", "-m", "src.app"]
      
      environment = [
        { name = "API_URL", value = var.api_url },
        { name = "IMAGES_QUANTITY", value = tostring(var.images_quantity) },
        { name = "RECIPIENT_EMAILS", value = join(",", var.recipient_emails) },
        { name = "GMAIL_USER", value = var.gmail_user },
        { name = "GMAIL_APP_PASSWORD", value = var.gmail_app_password },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "AWS_DEFAULT_REGION", value = var.aws_region },
        { name = "S3_BUCKET_NAME", value = var.s3_bucket_name },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_user },
        { name = "DB_PASSWORD", value = var.db_password },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "CHROME_BINARY", value = "/usr/bin/google-chrome" },
        { name = "CHROMEDRIVER_BINARY", value = "/usr/bin/chromedriver" }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.fargate_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  execution_role_arn = aws_iam_role.ecs_execution_role.arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn
}

# ==============================================================================
# 7. EVENTBRIDGE SCHEDULER (CRON - 6 AM Colombia = 11 AM UTC)
# ==============================================================================
resource "aws_scheduler_schedule" "image_generator_schedule" {
  name       = "${var.project_name}-schedule"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(0 11 * * ? *)"  # 11:00 UTC = 6:00 AM Colombia

  target {
    arn      = aws_ecs_cluster.image_generator_cluster.arn
    role_arn = aws_iam_role.eventbridge_scheduler_role.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.image_generator_task.arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = data.aws_subnets.public.ids
        assign_public_ip = true
        security_groups  = [aws_security_group.fargate_sg.id]
      }
    }
  }
}

# ==============================================================================
# 8. IAM ROLE FOR EVENTBRIDGE SCHEDULER
# ==============================================================================
resource "aws_iam_role" "eventbridge_scheduler_role" {
  name = "${var.project_name}-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler_policy" {
  name = "ecs-run-task"
  role = aws_iam_role.eventbridge_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:StopTask",
          "ecs:DescribeTasks"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}

# ==============================================================================
# 9. DATA SOURCES FOR VPC
# ==============================================================================
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

# ==============================================================================
# 10. OUTPUTS
# ==============================================================================
output "ecr_repository_url" {
  value = aws_ecr_repository.image_generator_repo.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.image_generator_cluster.name
}

output "ecs_task_definition_arn" {
  value = aws_ecs_task_definition.image_generator_task.arn
}

output "fargate_schedule_name" {
  value = aws_scheduler_schedule.image_generator_schedule.name
}