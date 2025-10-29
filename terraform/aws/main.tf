terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Uncomment for production with remote state
  # backend "s3" {
  #   bucket         = "transcript-terraform-state"
  #   key            = "production/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "transcript-create"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

# VPC and Networking
module "vpc" {
  source = "../modules/aws-vpc"

  project_name = var.project_name
  environment  = var.environment
  vpc_cidr     = var.vpc_cidr
  azs          = slice(data.aws_availability_zones.available.names, 0, 2)
}

# Security Groups
module "security_groups" {
  source = "../modules/aws-security-groups"

  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  vpc_cidr     = var.vpc_cidr
}

# RDS PostgreSQL
module "database" {
  source = "../modules/aws-rds"

  project_name         = var.project_name
  environment          = var.environment
  db_name              = var.db_name
  db_username          = var.db_username
  db_instance_class    = var.db_instance_class
  db_allocated_storage = var.db_allocated_storage
  db_multi_az          = var.db_multi_az
  
  vpc_id               = module.vpc.vpc_id
  subnet_ids           = module.vpc.private_subnet_ids
  security_group_ids   = [module.security_groups.database_sg_id]
}

# ElastiCache Redis
module "redis" {
  source = "../modules/aws-elasticache"

  project_name       = var.project_name
  environment        = var.environment
  redis_node_type    = var.redis_node_type
  redis_num_clusters = var.redis_num_clusters
  
  subnet_ids         = module.vpc.private_subnet_ids
  security_group_ids = [module.security_groups.redis_sg_id]
}

# S3 Storage
module "storage" {
  source = "../modules/aws-s3"

  project_name = var.project_name
  environment  = var.environment
  bucket_name  = "${var.project_name}-media-${var.environment}"
}

# Secrets Manager
resource "random_password" "session_secret" {
  length  = 64
  special = false
}

module "secrets" {
  source = "../modules/aws-secrets"

  project_name = var.project_name
  environment  = var.environment
  
  secrets = {
    database_url   = "postgresql+psycopg://${var.db_username}:${module.database.db_password}@${module.database.db_endpoint}/${var.db_name}"
    session_secret = random_password.session_secret.result
    redis_url      = "redis://${module.redis.redis_endpoint}:6379/0"
  }
}

# Application Load Balancer
module "alb" {
  source = "../modules/aws-alb"

  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.public_subnet_ids
  security_group_ids = [module.security_groups.alb_sg_id]
  certificate_arn    = var.certificate_arn
}

# ECS Fargate for API
module "ecs_api" {
  source = "../modules/aws-ecs"

  project_name = var.project_name
  environment  = var.environment
  
  service_name = "api"
  container_image = "${var.ecr_repository_url}:${var.image_tag}"
  
  cpu    = var.ecs_api_cpu
  memory = var.ecs_api_memory
  
  desired_count = var.ecs_api_count
  min_capacity  = var.ecs_api_min_count
  max_capacity  = var.ecs_api_max_count
  
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnet_ids
  security_group_ids = [module.security_groups.ecs_api_sg_id]
  
  target_group_arn = module.alb.target_group_arn
  
  environment_variables = {
    ENVIRONMENT      = var.environment
    LOG_LEVEL        = "INFO"
    LOG_FORMAT       = "json"
    FRONTEND_ORIGIN  = "https://${var.domain_name}"
  }
  
  secrets = {
    DATABASE_URL   = module.secrets.secret_arns["database_url"]
    SESSION_SECRET = module.secrets.secret_arns["session_secret"]
    REDIS_URL      = module.secrets.secret_arns["redis_url"]
  }
  
  depends_on = [module.alb]
}

# EC2 Auto Scaling Group for Workers (with GPU)
module "ec2_workers" {
  source = "../modules/aws-ec2-asg"
  count  = var.ec2_worker_enabled ? 1 : 0

  project_name  = var.project_name
  environment   = var.environment
  service_name  = "worker"
  
  instance_type = var.ec2_worker_instance_type
  ami_id        = var.ec2_worker_ami_id
  key_name      = var.ec2_key_name
  
  min_size         = var.ec2_worker_min_count
  max_size         = var.ec2_worker_max_count
  desired_capacity = var.ec2_worker_count
  
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnet_ids
  security_group_ids = [module.security_groups.worker_sg_id]
  
  user_data = templatefile("${path.module}/templates/worker-userdata.sh", {
    ecr_repository_url = var.ecr_repository_url
    image_tag          = var.image_tag
    aws_region         = var.aws_region
    database_secret_arn = module.secrets.secret_arns["database_url"]
    redis_url          = "redis://${module.redis.redis_endpoint}:6379/0"
  })
  
  iam_instance_profile = aws_iam_instance_profile.worker_profile.name
}

# IAM Role for Workers
resource "aws_iam_role" "worker_role" {
  name = "${var.project_name}-worker-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "worker_ecr" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "worker_ssm" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "worker_s3" {
  name = "s3-access"
  role = aws_iam_role.worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.storage.bucket_arn,
          "${module.storage.bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_secrets" {
  name = "secrets-access"
  role = aws_iam_role.worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = values(module.secrets.secret_arns)
      }
    ]
  })
}

resource "aws_iam_instance_profile" "worker_profile" {
  name = "${var.project_name}-worker-profile-${var.environment}"
  role = aws_iam_role.worker_role.name
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}-${var.environment}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker" {
  count             = var.ec2_worker_enabled ? 1 : 0
  name              = "/ec2/${var.project_name}-${var.environment}/worker"
  retention_in_days = var.log_retention_days
}

# Route53 (if managing DNS)
resource "aws_route53_record" "api" {
  count   = var.create_dns_record ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.alb.alb_dns_name
    zone_id                = module.alb.alb_zone_id
    evaluate_target_health = true
  }
}
